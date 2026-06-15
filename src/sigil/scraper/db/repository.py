"""Async persistence for posts and scrape runs (Supabase Postgres via asyncpg).

All writes are parameterized SQLAlchemy Core statements - no string
interpolation. ``upsert_posts`` is the idempotent ingest path: re-running a
campaign never creates duplicate rows thanks to the ``(platform,
platform_post_id)`` unique constraint.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from sigil.scraper.db.engine import session_scope
from sigil.scraper.db.tables import flagged_posts, posts, scrape_campaigns, scrape_runs
from sigil.logging import get_logger
from sigil.scraper.models import (
    Campaign,
    NormalizedPost,
    Platform,
    RunStatus,
    TranscriptionStatus,
)

log = get_logger(__name__)

UPSERT_CHUNK_SIZE = 500

# Volatile fields refreshed on conflict. NOTE: `transcript` is intentionally
# absent so a re-scrape never clobbers transcription work.
_VOLATILE_UPDATE_COLUMNS = (
    "url",
    "author_handle",
    "author_id",
    "author_url",
    "content_text",
    "lang",
    "posted_at",
    "like_count",
    "comment_count",
    "share_count",
    "view_count",
    "media_type",
    "has_video",
    "video_url",
    "audio_url",
    "thumbnail_url",
    "hashtags",
    "mentions",
    "country",
    "country_confidence",
    "topic",
    "raw",
    "scraped_at",
)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _chunks(items: list[Any], size: int) -> Iterable[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _strip_nul(value: Any) -> Any:
    """Recursively remove NUL bytes (``\\u0000``) from strings.

    Postgres ``text``/``jsonb`` cannot store the NUL character, and scraped
    payloads (especially Apify ``raw`` blobs) occasionally contain one. A single
    such byte would otherwise abort the whole ingest batch.
    """
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [_strip_nul(v) for v in value]
    if isinstance(value, dict):
        return {k: _strip_nul(v) for k, v in value.items()}
    return value


def _post_to_row(post: NormalizedPost) -> dict[str, Any]:
    """Map a NormalizedPost to a ``posts`` row dict."""
    status = (
        TranscriptionStatus.pending
        if post.needs_transcription()
        else TranscriptionStatus.not_required
    )
    row = {
        "platform": post.platform.value,
        "platform_post_id": post.platform_post_id,
        "campaign_id": post.campaign_id,
        "url": post.url,
        "author_handle": post.author_handle,
        "author_id": post.author_id,
        "author_url": post.author_url,
        "content_text": post.content_text,
        "lang": post.lang,
        "posted_at": post.posted_at,
        "like_count": post.like_count,
        "comment_count": post.comment_count,
        "share_count": post.share_count,
        "view_count": post.view_count,
        "media_type": post.media_type,
        "has_video": post.has_video,
        "video_url": post.video_url,
        "audio_url": post.audio_url,
        "thumbnail_url": post.thumbnail_url,
        "hashtags": post.hashtags,
        "mentions": post.mentions,
        "country": post.country,
        "country_confidence": post.country_confidence,
        "topic": post.topic,
        "transcription_status": status.value,
        "raw": post.raw,
        "scraped_at": post.scraped_at,
    }
    return _strip_nul(row)


async def upsert_posts(rows: list[NormalizedPost]) -> int:
    """Bulk upsert posts, returning the number of rows inserted or updated.

    Uses ``INSERT ... ON CONFLICT (platform, platform_post_id) DO UPDATE`` in
    chunks of ``UPSERT_CHUNK_SIZE``. Volatile fields (counts, media, etc.) are
    refreshed; ``transcript`` is never touched. ``transcription_status`` is only
    bumped *up* to ``pending`` when a row is (newly) video/audio - we never
    regress a row that already moved past ``pending``.
    """
    if not rows:
        return 0

    deduped = _dedupe_posts(rows)

    affected = 0
    for chunk in _chunks(deduped, UPSERT_CHUNK_SIZE):
        affected += await _upsert_post_chunk(chunk)

    log.info("posts_upserted", count=affected, received=len(rows))
    return affected


def _dedupe_posts(rows: list[NormalizedPost]) -> list[NormalizedPost]:
    """Collapse duplicate (platform, platform_post_id) rows, keeping the last.

    A single ``INSERT ... ON CONFLICT DO UPDATE`` cannot touch the same row
    twice, and Apify result sets occasionally repeat a post within one batch.
    The last occurrence wins (latest scrape of that post).
    """
    by_key: dict[tuple[str, str], NormalizedPost] = {}
    for post in rows:
        by_key[(post.platform.value, post.platform_post_id)] = post
    if len(by_key) != len(rows):
        log.info("posts_deduped", received=len(rows), unique=len(by_key))
    return list(by_key.values())


def _posts_upsert_stmt(values: list[dict[str, Any]]):
    """Build the ``INSERT ... ON CONFLICT DO UPDATE`` statement for ``posts``."""
    stmt = pg_insert(posts).values(values)
    update_set: dict[str, Any] = {
        col: getattr(stmt.excluded, col) for col in _VOLATILE_UPDATE_COLUMNS
    }
    # Only advance transcription_status toward 'pending'; never downgrade a row
    # the transcriber has already started/finished.
    update_set["transcription_status"] = func.greatest(
        posts.c.transcription_status,
        stmt.excluded.transcription_status,
    )
    return stmt.on_conflict_do_update(
        index_elements=[posts.c.platform, posts.c.platform_post_id],
        set_=update_set,
    )


async def _upsert_post_chunk(chunk: list[NormalizedPost]) -> int:
    """Upsert one chunk; on DB error, retry row-by-row so a single poison row
    cannot abort the whole ingest. Unsalvageable rows are skipped and logged
    with their id and the underlying error."""
    values = [_post_to_row(p) for p in chunk]
    try:
        async with session_scope() as session:
            result = await session.execute(_posts_upsert_stmt(values))
            return result.rowcount or 0
    except SQLAlchemyError as exc:
        if len(chunk) == 1:
            post = chunk[0]
            log.error(
                "post_upsert_skipped",
                platform=post.platform.value,
                platform_post_id=post.platform_post_id,
                error=str(getattr(exc, "orig", exc)),
            )
            return 0
        log.warning(
            "post_upsert_chunk_failed",
            chunk_size=len(chunk),
            error=str(getattr(exc, "orig", exc)),
        )
        affected = 0
        for post in chunk:
            affected += await _upsert_post_chunk([post])
        return affected


async def upsert_campaigns(campaigns: list[Campaign]) -> int:
    """Sync YAML-defined campaigns into ``scrape_campaigns``.

    Campaign ids are deterministic UUID5s, so this is idempotent: existing rows
    are updated in place, satisfying the ``scrape_runs``/``posts`` foreign keys.
    Returns the number of rows inserted or updated.
    """
    if not campaigns:
        return 0

    values = [
        {
            "id": c.id,
            "platform": c.platform.value,
            "topic": c.topic,
            "country": c.country,
            "seeds": c.seeds,
            "daily_target": c.daily_target,
            "enabled": c.enabled,
        }
        for c in campaigns
    ]
    async with session_scope() as session:
        stmt = pg_insert(scrape_campaigns).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[scrape_campaigns.c.id],
            set_={
                "platform": stmt.excluded.platform,
                "topic": stmt.excluded.topic,
                "country": stmt.excluded.country,
                "seeds": stmt.excluded.seeds,
                "daily_target": stmt.excluded.daily_target,
                "enabled": stmt.excluded.enabled,
            },
        )
        result = await session.execute(stmt)
    log.info("campaigns_synced", count=result.rowcount or 0, received=len(campaigns))
    return result.rowcount or 0


# Cells refreshed when a post is re-flagged. `is_reviewed` and `added_at` are
# intentionally absent so a re-validation never resets the review workflow.
_FLAGGED_UPDATE_COLUMNS = (
    "platform",
    "category",
    "warnings_count",
    "warning_categories",
    "warning_affected_groups",
    "platform_post_id",
    "url",
    "author",
    "content_text",
    "posted_at",
    "like_count",
    "comment_count",
    "view_count",
    "hashtags",
    "violation_quotes",
    "violation_policy_refs",
    "tos_cross_reference",
    "violation_explanation",
    "report_text",
)


async def upsert_flagged_post(row: dict[str, Any]) -> None:
    """Insert (or refresh) a flagged-post row for a CLEAR_VIOLATION post.

    Idempotent on ``post_id``: re-validating the same post refreshes the report
    cells without resetting ``is_reviewed`` / ``added_at``.
    """
    async with session_scope() as session:
        stmt = pg_insert(flagged_posts).values(**row)
        update_set = {
            col: getattr(stmt.excluded, col)
            for col in _FLAGGED_UPDATE_COLUMNS
            if col in row
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=[flagged_posts.c.post_id],
            set_=update_set,
        )
        await session.execute(stmt)
    log.info("flagged_post_upserted", post_id=str(row.get("post_id")))


async def create_run(
    *,
    run_id: UUID,
    campaign_id: UUID,
    platform: Platform,
    apify_run_id: str | None = None,
    apify_dataset_id: str | None = None,
    status: RunStatus = RunStatus.running,
) -> None:
    """Insert a ``scrape_runs`` row for a started run."""
    async with session_scope() as session:
        await session.execute(
            pg_insert(scrape_runs).values(
                id=run_id,
                campaign_id=campaign_id,
                platform=platform.value,
                apify_run_id=apify_run_id,
                apify_dataset_id=apify_dataset_id,
                status=status.value,
                requested_at=_utcnow(),
                started_at=_utcnow() if status == RunStatus.running else None,
            )
        )
    log.info(
        "run_created",
        run_id=str(run_id),
        campaign_id=str(campaign_id),
        platform=platform.value,
        apify_run_id=apify_run_id,
    )


async def mark_run_running(
    *,
    run_id: UUID,
    apify_run_id: str,
    apify_dataset_id: str,
) -> None:
    """Mark a run as running and attach its Apify identifiers."""
    async with session_scope() as session:
        await session.execute(
            update(scrape_runs)
            .where(scrape_runs.c.id == run_id)
            .values(
                status=RunStatus.running.value,
                apify_run_id=apify_run_id,
                apify_dataset_id=apify_dataset_id,
                started_at=_utcnow(),
            )
        )
    log.info("run_marked_running", run_id=str(run_id), apify_run_id=apify_run_id)


async def finish_run(
    *,
    run_id: UUID,
    status: RunStatus,
    items_ingested: int = 0,
    items_failed: int = 0,
    cost_usd: float | None = None,
    error: str | None = None,
) -> None:
    """Finalize a run (succeeded/failed/aborted) with outcome metrics."""
    async with session_scope() as session:
        await session.execute(
            update(scrape_runs)
            .where(scrape_runs.c.id == run_id)
            .values(
                status=status.value,
                items_ingested=items_ingested,
                items_failed=items_failed,
                cost_usd=cost_usd,
                error=error,
                finished_at=_utcnow(),
            )
        )
    log.info(
        "run_finished",
        run_id=str(run_id),
        status=status.value,
        items_ingested=items_ingested,
        items_failed=items_failed,
        cost_usd=cost_usd,
    )


async def fetch_running_runs() -> list[dict[str, Any]]:
    """Return all runs currently in the ``running`` state for the collector."""
    async with session_scope() as session:
        result = await session.execute(
            select(
                scrape_runs.c.id,
                scrape_runs.c.campaign_id,
                scrape_runs.c.platform,
                scrape_runs.c.apify_run_id,
                scrape_runs.c.apify_dataset_id,
                scrape_runs.c.status,
            ).where(scrape_runs.c.status == RunStatus.running.value)
        )
        return [dict(row._mapping) for row in result]


async def count_active_runs(session: AsyncSession | None = None) -> int:
    """Count runs in ``running`` state (concurrency guard helper)."""
    async def _run(s: AsyncSession) -> int:
        result = await s.execute(
            select(func.count())
            .select_from(scrape_runs)
            .where(scrape_runs.c.status == RunStatus.running.value)
        )
        return int(result.scalar_one())

    if session is not None:
        return await _run(session)
    async with session_scope() as s:
        return await _run(s)


async def sum_cost_since(since: datetime) -> float:
    """Sum ``cost_usd`` of runs requested since ``since`` (daily budget guard)."""
    async with session_scope() as session:
        result = await session.execute(
            select(func.coalesce(func.sum(scrape_runs.c.cost_usd), 0)).where(
                scrape_runs.c.requested_at >= since
            )
        )
        return float(result.scalar_one())


async def has_running_run_for_campaign(campaign_id: UUID) -> bool:
    """Whether a campaign already has a run in flight (avoid double-starting)."""
    async with session_scope() as session:
        result = await session.execute(
            select(func.count())
            .select_from(scrape_runs)
            .where(
                scrape_runs.c.campaign_id == campaign_id,
                scrape_runs.c.status == RunStatus.running.value,
            )
        )
        return int(result.scalar_one()) > 0


async def count_runs_today(campaign_id: UUID, *, since: datetime) -> int:
    """Count runs for a campaign since ``since`` that succeeded or are running.

    Used to throttle a campaign toward its ``daily_target`` across scheduling
    windows (so we don't burst the whole day's volume at once).
    """
    async with session_scope() as session:
        result = await session.execute(
            select(func.count())
            .select_from(scrape_runs)
            .where(
                scrape_runs.c.campaign_id == campaign_id,
                scrape_runs.c.requested_at >= since,
                scrape_runs.c.status.in_(
                    [RunStatus.running.value, RunStatus.succeeded.value]
                ),
            )
        )
        return int(result.scalar_one())


async def status_summary(recent_limit: int = 20) -> dict[str, Any]:
    """Read-only summary for the status endpoint (counts + recent runs)."""
    async with session_scope() as session:
        posts_total = (
            await session.execute(select(func.count()).select_from(posts))
        ).scalar_one()
        pending_transcription = (
            await session.execute(
                select(func.count())
                .select_from(posts)
                .where(posts.c.transcription_status == TranscriptionStatus.pending.value)
            )
        ).scalar_one()
        # "pending" mirrors pipeline.ValidationStatus.PENDING; kept as a literal so
        # the DB layer stays free of a pipeline import.
        pending_validation = (
            await session.execute(
                select(func.count())
                .select_from(posts)
                .where(posts.c.validation_status == "pending")
            )
        ).scalar_one()

        status_rows = await session.execute(
            select(scrape_runs.c.status, func.count())
            .group_by(scrape_runs.c.status)
        )
        runs_by_status = {row[0]: int(row[1]) for row in status_rows}

        recent = await session.execute(
            select(
                scrape_runs.c.id,
                scrape_runs.c.campaign_id,
                scrape_runs.c.platform,
                scrape_runs.c.status,
                scrape_runs.c.items_ingested,
                scrape_runs.c.items_failed,
                scrape_runs.c.cost_usd,
                scrape_runs.c.requested_at,
                scrape_runs.c.finished_at,
            )
            .order_by(scrape_runs.c.requested_at.desc())
            .limit(recent_limit)
        )
        recent_runs = [
            {
                "id": str(r.id),
                "campaign_id": str(r.campaign_id) if r.campaign_id else None,
                "platform": r.platform,
                "status": r.status,
                "items_ingested": r.items_ingested,
                "items_failed": r.items_failed,
                "cost_usd": float(r.cost_usd) if r.cost_usd is not None else None,
                "requested_at": r.requested_at.isoformat() if r.requested_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            }
            for r in recent
        ]

    return {
        "posts_total": int(posts_total),
        "posts_pending_transcription": int(pending_transcription),
        "posts_pending_validation": int(pending_validation),
        "runs_by_status": runs_by_status,
        "recent_runs": recent_runs,
    }


async def flagged_counts() -> tuple[int, int]:
    """Return ``(total_flagged, unreviewed_flagged)`` from ``flagged_posts``."""
    async with session_scope() as session:
        total = (
            await session.execute(select(func.count()).select_from(flagged_posts))
        ).scalar_one()
        unreviewed = (
            await session.execute(
                select(func.count())
                .select_from(flagged_posts)
                .where(flagged_posts.c.is_reviewed.is_(False))
            )
        ).scalar_one()
    return int(total), int(unreviewed)


async def count_attempts_for_campaign(campaign_id: UUID, *, since: datetime) -> int:
    """Count ALL runs (incl. failed) for a campaign since ``since``.

    Used by the retry policy to cap re-queues per day.
    """
    async with session_scope() as session:
        result = await session.execute(
            select(func.count())
            .select_from(scrape_runs)
            .where(
                scrape_runs.c.campaign_id == campaign_id,
                scrape_runs.c.requested_at >= since,
            )
        )
        return int(result.scalar_one())
