"""Validation pipeline: fetch scraped posts, validate against policies, store results.

This is the core integration between the scraper and validator systems.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update, func

from sigil.validation.judge import judge
from sigil.validation.models import JudgmentError, PolicyNotFoundError, PostData, Verdict
from sigil.validation.policy_loader import load_policies
from sigil.validation.report_generator import ViolationReport, generate_violation_report
from sigil.scraper.db import repository
from sigil.scraper.db.engine import session_scope
from sigil.scraper.db.tables import flagged_posts, posts
from sigil.pipeline.converter import db_row_to_post_data, validator_platform
from sigil.logging import get_logger

log = get_logger(__name__)


class ValidationStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


async def fetch_pending_posts(
    *,
    campaign_id: UUID | None = None,
    platform: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Fetch posts pending validation from the database.
    
    Args:
        campaign_id: Optional filter by campaign
        platform: Optional filter by platform (tiktok, instagram, facebook, twitter)
        limit: Maximum number of posts to fetch
        
    Returns:
        List of post rows as dicts
    """
    async with session_scope() as session:
        query = select(
            posts.c.id,
            posts.c.platform,
            posts.c.platform_post_id,
            posts.c.url,
            posts.c.author_handle,
            posts.c.content_text,
            posts.c.video_url,
            posts.c.thumbnail_url,
            posts.c.campaign_id,
            posts.c.topic,
            posts.c.transcript,
            posts.c.posted_at,
            posts.c.like_count,
            posts.c.comment_count,
            posts.c.view_count,
            posts.c.hashtags,
        ).where(
            posts.c.validation_status == ValidationStatus.PENDING
        ).limit(limit)
        
        if campaign_id:
            query = query.where(posts.c.campaign_id == campaign_id)
        if platform:
            query = query.where(posts.c.platform == platform)
        
        result = await session.execute(query)
        return [dict(row._mapping) for row in result]


async def update_post_validation(
    *,
    post_id: UUID,
    status: str,
    error: str | None = None,
) -> None:
    """Update a post's validation status (queue control only).

    The verdict detail is intentionally NOT stored on the post row: clear
    violations are persisted as flattened, report-ready rows in ``flagged_posts``
    instead. ``posts`` only tracks ``validation_status`` so the queue is not
    re-processed.

    Args:
        post_id: The post's UUID
        status: Validation status (pending, processing, pass, fail, error)
        error: Optional error message if validation failed
    """
    values: dict[str, Any] = {
        "validation_status": status,
        "validated_at": _utcnow(),
    }

    if error:
        values["validation_recommendation"] = error

    async with session_scope() as session:
        await session.execute(
            update(posts)
            .where(posts.c.id == post_id)
            .values(**values)
        )


async def mark_post_processing(post_id: UUID) -> None:
    """Mark a post as currently being processed."""
    async with session_scope() as session:
        await session.execute(
            update(posts)
            .where(posts.c.id == post_id)
            .values(validation_status=ValidationStatus.PROCESSING)
        )


def _build_flagged_row(
    row: dict[str, Any],
    post_data: PostData,
    verdict: Verdict,
    report: "ViolationReport",
) -> dict[str, Any]:
    """Assemble a ``flagged_posts`` row from a CLEAR_VIOLATION result."""
    warning_affected_groups = "; ".join(
        ", ".join(w.affected_groups) if w.affected_groups else "N/A"
        for w in verdict.warnings
    )
    hashtags = row.get("hashtags") or []

    return {
        "post_id": row["id"],
        "platform": row["platform"],
        "category": report.category,
        "warnings_count": len(verdict.warnings),
        "warning_categories": "; ".join(w.category for w in verdict.warnings),
        "warning_affected_groups": warning_affected_groups,
        "platform_post_id": row.get("platform_post_id"),
        "url": row.get("url") or post_data.url,
        "author": row.get("author_handle"),
        "content_text": row.get("content_text"),
        "posted_at": row.get("posted_at"),
        "like_count": row.get("like_count"),
        "comment_count": row.get("comment_count"),
        "view_count": row.get("view_count"),
        "hashtags": ", ".join(hashtags),
        "violation_quotes": "; ".join(v.quote for v in verdict.violations),
        "violation_policy_refs": "; ".join(
            v.policy_reference for v in verdict.violations
        ),
        "tos_cross_reference": report.tos_cross_reference,
        "violation_explanation": report.violation_explanation,
        "report_text": report.report_text,
    }


async def validate_single_post(row: dict[str, Any]) -> dict[str, Any]:
    """Validate a single post and update its status in the database.

    On a CLEAR_VIOLATION, a second-pass report is generated and the post is
    persisted as a flattened row in ``flagged_posts`` (the raw verdict is never
    stored).

    Args:
        row: Post row dict from the database
        
    Returns:
        Result dict with post info and validation outcome
    """
    post_id = row["id"]
    platform = row["platform"]
    
    result = {
        "post_id": str(post_id),
        "platform": platform,
        "url": row.get("url"),
        "author": row.get("author_handle"),
    }
    
    try:
        await mark_post_processing(post_id)
        
        post_data = db_row_to_post_data(row)
        policies_text = load_policies(validator_platform(platform))

        provided_transcript = row.get("transcript")
        # The judge / report generator are synchronous and network-bound (LLM
        # calls). Offload them to a worker thread so concurrent validations do
        # not block the event loop (and its async DB work).
        loop = asyncio.get_running_loop()
        verdict = await loop.run_in_executor(
            None, judge, post_data, policies_text, provided_transcript
        )

        is_clear_violation = verdict.verdict == "CLEAR_VIOLATION"
        status = ValidationStatus.FAIL if is_clear_violation else ValidationStatus.PASS

        if is_clear_violation:
            # Re-load policies WITH line numbers so the prosecutor can cite exact
            # lines, and pass post reach metadata for a richer formal report.
            report_policies = load_policies(
                validator_platform(platform), numbered=True
            )
            report_metadata = {
                "posted_at": row.get("posted_at"),
                "view_count": row.get("view_count"),
                "like_count": row.get("like_count"),
                "comment_count": row.get("comment_count"),
                "share_count": row.get("share_count"),
                "hashtags": row.get("hashtags") or [],
            }
            report = await loop.run_in_executor(
                None,
                generate_violation_report,
                post_data,
                report_policies,
                verdict,
                report_metadata,
            )
            flagged_row = _build_flagged_row(row, post_data, verdict, report)
            await repository.upsert_flagged_post(flagged_row)
            result["category"] = report.category

        await update_post_validation(post_id=post_id, status=status)
        
        result["status"] = status
        result["verdict"] = verdict.verdict
        result["confidence"] = verdict.confidence
        result["violations"] = [
            {
                "rule": v.rule,
                "severity": v.severity,
                "explanation": v.explanation,
                "quote": v.quote,
            }
            for v in verdict.violations
        ]
        
        log.info(
            "post_validated",
            post_id=str(post_id),
            platform=platform,
            verdict=verdict.verdict,
            flagged=is_clear_violation,
            violations_count=len(verdict.violations),
        )
        
    except PolicyNotFoundError as e:
        await update_post_validation(
            post_id=post_id,
            status=ValidationStatus.ERROR,
            error=f"Policy not found: {e}",
        )
        result["status"] = ValidationStatus.ERROR
        result["error"] = str(e)
        log.error("validation_policy_error", post_id=str(post_id), error=str(e))
        
    except JudgmentError as e:
        await update_post_validation(
            post_id=post_id,
            status=ValidationStatus.ERROR,
            error=f"Judgment error: {e}",
        )
        result["status"] = ValidationStatus.ERROR
        result["error"] = str(e)
        log.error("validation_judgment_error", post_id=str(post_id), error=str(e))
        
    except Exception as e:
        await update_post_validation(
            post_id=post_id,
            status=ValidationStatus.ERROR,
            error=f"Unexpected error: {e}",
        )
        result["status"] = ValidationStatus.ERROR
        result["error"] = str(e)
        log.error("validation_unexpected_error", post_id=str(post_id), error=str(e), exc_info=True)
    
    return result


async def validate_scraped_posts(
    *,
    campaign_id: UUID | None = None,
    platform: str | None = None,
    limit: int = 100,
    concurrency: int = 5,
) -> list[dict[str, Any]]:
    """Fetch and validate scraped posts, storing results in the database.
    
    Args:
        campaign_id: Optional filter by campaign UUID
        platform: Optional filter by platform name
        limit: Maximum number of posts to validate
        concurrency: Number of concurrent validations (Claude API calls)
        
    Returns:
        List of validation results for each post
    """
    log.info(
        "validation_batch_starting",
        campaign_id=str(campaign_id) if campaign_id else None,
        platform=platform,
        limit=limit,
        concurrency=concurrency,
    )
    
    pending_posts = await fetch_pending_posts(
        campaign_id=campaign_id,
        platform=platform,
        limit=limit,
    )
    
    if not pending_posts:
        log.info("validation_no_pending_posts")
        return []
    
    log.info("validation_posts_fetched", count=len(pending_posts))
    
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def validate_with_semaphore(row: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await validate_single_post(row)

    results = await asyncio.gather(
        *(validate_with_semaphore(row) for row in pending_posts)
    )

    passed = sum(1 for r in results if r.get("status") == ValidationStatus.PASS)
    failed = sum(1 for r in results if r.get("status") == ValidationStatus.FAIL)
    errors = sum(1 for r in results if r.get("status") == ValidationStatus.ERROR)
    
    log.info(
        "validation_batch_complete",
        total=len(results),
        passed=passed,
        failed=failed,
        errors=errors,
    )
    
    return results


async def fetch_violations(
    *,
    platform: str | None = None,
    severity: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Fetch flagged (CLEAR_VIOLATION) posts from ``flagged_posts``.

    Verdict detail is no longer stored on the ``posts`` row, so this reads the
    flattened report cells from ``flagged_posts`` and reshapes them into the
    legacy ``violations`` list structure the existing endpoint / CLI expect.

    Args:
        platform: Optional filter by platform
        severity: Accepted for backwards compatibility but ignored - per-violation
            severity is not retained in the flattened flagged rows.
        limit: Maximum number of posts to return

    Returns:
        List of flagged posts with a synthesized ``violations`` list.
    """
    async with session_scope() as session:
        query = (
            select(
                flagged_posts.c.id,
                flagged_posts.c.platform,
                flagged_posts.c.category,
                flagged_posts.c.url,
                flagged_posts.c.author,
                flagged_posts.c.content_text,
                flagged_posts.c.violation_quotes,
                flagged_posts.c.violation_policy_refs,
                flagged_posts.c.violation_explanation,
                flagged_posts.c.added_at,
                flagged_posts.c.is_reviewed,
            )
            .order_by(flagged_posts.c.added_at.desc())
            .limit(limit)
        )

        if platform:
            query = query.where(flagged_posts.c.platform == platform)

        result = await session.execute(query)
        flagged_rows = [dict(row._mapping) for row in result]

    rows: list[dict[str, Any]] = []
    for fr in flagged_rows:
        rows.append(
            {
                "id": fr["id"],
                "platform": fr["platform"],
                "url": fr["url"],
                "author_handle": fr["author"],
                "content_text": fr["content_text"],
                "topic": fr["category"],
                "validation_confidence": None,
                "validated_at": fr["added_at"],
                "is_reviewed": fr["is_reviewed"],
                "violations": [
                    {
                        "rule": fr["category"] or "Policy violation",
                        "severity": "",
                        "explanation": fr["violation_explanation"] or "",
                        "quote": fr["violation_quotes"] or "",
                        "policy_reference": fr["violation_policy_refs"] or "",
                    }
                ],
            }
        )

    return rows


async def get_validation_stats() -> dict[str, Any]:
    """Get validation statistics summary."""
    async with session_scope() as session:
        total = (
            await session.execute(select(func.count()).select_from(posts))
        ).scalar_one()
        
        pending = (
            await session.execute(
                select(func.count())
                .select_from(posts)
                .where(posts.c.validation_status == ValidationStatus.PENDING)
            )
        ).scalar_one()
        
        passed = (
            await session.execute(
                select(func.count())
                .select_from(posts)
                .where(posts.c.validation_status == ValidationStatus.PASS)
            )
        ).scalar_one()

        # Failures are the flagged (CLEAR_VIOLATION) posts.
        failed = (
            await session.execute(select(func.count()).select_from(flagged_posts))
        ).scalar_one()

        flagged_unreviewed = (
            await session.execute(
                select(func.count())
                .select_from(flagged_posts)
                .where(flagged_posts.c.is_reviewed.is_(False))
            )
        ).scalar_one()

        errors = (
            await session.execute(
                select(func.count())
                .select_from(posts)
                .where(posts.c.validation_status == ValidationStatus.ERROR)
            )
        ).scalar_one()

        by_platform = await session.execute(
            select(posts.c.platform, posts.c.validation_status, func.count())
            .where(
                posts.c.validation_status.in_(
                    [ValidationStatus.PASS, ValidationStatus.FAIL]
                )
            )
            .group_by(posts.c.platform, posts.c.validation_status)
        )
        platform_stats: dict[str, dict[str, int]] = {}
        for row in by_platform:
            plat, vstatus, count = row
            if plat not in platform_stats:
                platform_stats[plat] = {"PASS": 0, "FAIL": 0}
            key = "PASS" if vstatus == ValidationStatus.PASS else "FAIL"
            platform_stats[plat][key] = int(count)
    
    return {
        "total_posts": int(total),
        "pending_validation": int(pending),
        "passed": int(passed),
        "failed": int(failed),
        "flagged_unreviewed": int(flagged_unreviewed),
        "errors": int(errors),
        "by_platform": platform_stats,
    }
