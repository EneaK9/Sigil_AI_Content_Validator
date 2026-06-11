"""Validation pipeline: fetch scraped posts, validate against policies, store results.

This is the core integration between the scraper and validator systems.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update, func

from core.judge import judge
from core.models import JudgmentError, PolicyNotFoundError, Verdict
from core.policy_loader import load_policies
from scraper.db.engine import session_scope
from scraper.db.tables import posts
from scraper.integration.converter import db_row_to_post_data
from scraper.logging_setup import get_logger
from scraper.models import Platform

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
        platform: Optional filter by platform (tiktok, instagram, facebook)
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
    verdict: Verdict | None = None,
    error: str | None = None,
) -> None:
    """Update a post's validation status and results.
    
    Args:
        post_id: The post's UUID
        status: Validation status (pending, processing, pass, fail, error)
        verdict: Optional Verdict object from the judge
        error: Optional error message if validation failed
    """
    values: dict[str, Any] = {
        "validation_status": status,
        "validated_at": _utcnow(),
    }
    
    if verdict:
        values["verdict"] = verdict.verdict
        values["violations"] = [asdict(v) for v in verdict.violations]
        values["validation_confidence"] = verdict.confidence
        values["validation_recommendation"] = verdict.recommendation
    
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


async def validate_single_post(row: dict[str, Any]) -> dict[str, Any]:
    """Validate a single post and update its status in the database.
    
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
        policies_text = load_policies(platform)
        
        provided_transcript = row.get("transcript")
        verdict = judge(post_data, policies_text, provided_transcript)
        
        status = ValidationStatus.PASS if verdict.verdict == "PASS" else ValidationStatus.FAIL
        await update_post_validation(post_id=post_id, status=status, verdict=verdict)
        
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
    
    semaphore = asyncio.Semaphore(concurrency)
    
    async def validate_with_semaphore(row: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: asyncio.run(validate_single_post(row)))
    
    results = []
    for row in pending_posts:
        result = await validate_single_post(row)
        results.append(result)
    
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
    """Fetch posts that failed validation (have violations).
    
    Args:
        platform: Optional filter by platform
        severity: Optional filter by violation severity (HIGH, MEDIUM, LOW)
        limit: Maximum number of posts to return
        
    Returns:
        List of violating posts with their violation details
    """
    async with session_scope() as session:
        query = select(
            posts.c.id,
            posts.c.platform,
            posts.c.url,
            posts.c.author_handle,
            posts.c.content_text,
            posts.c.violations,
            posts.c.validation_confidence,
            posts.c.validated_at,
            posts.c.topic,
        ).where(
            posts.c.verdict == "FAIL"
        ).order_by(
            posts.c.validated_at.desc()
        ).limit(limit)
        
        if platform:
            query = query.where(posts.c.platform == platform)
        
        result = await session.execute(query)
        rows = [dict(row._mapping) for row in result]
    
    if severity:
        filtered = []
        for row in rows:
            violations = row.get("violations") or []
            matching = [v for v in violations if v.get("severity") == severity]
            if matching:
                row["violations"] = matching
                filtered.append(row)
        return filtered
    
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
                .where(posts.c.verdict == "PASS")
            )
        ).scalar_one()
        
        failed = (
            await session.execute(
                select(func.count())
                .select_from(posts)
                .where(posts.c.verdict == "FAIL")
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
            select(posts.c.platform, posts.c.verdict, func.count())
            .where(posts.c.verdict.isnot(None))
            .group_by(posts.c.platform, posts.c.verdict)
        )
        platform_stats: dict[str, dict[str, int]] = {}
        for row in by_platform:
            plat, verdict, count = row
            if plat not in platform_stats:
                platform_stats[plat] = {"PASS": 0, "FAIL": 0}
            platform_stats[plat][verdict] = int(count)
    
    return {
        "total_posts": int(total),
        "pending_validation": int(pending),
        "passed": int(passed),
        "failed": int(failed),
        "errors": int(errors),
        "by_platform": platform_stats,
    }
