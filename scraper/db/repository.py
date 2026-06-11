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
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.db.engine import session_scope
from scraper.db.tables import posts, scrape_campaigns, scrape_runs
from scraper.logging_setup import get_logger
from scraper.models import (
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


def _post_to_row(post: NormalizedPost) -> dict[str, Any]:
    """Map a NormalizedPost to a ``posts`` row dict."""
    status = (
        TranscriptionStatus.pending
        if post.needs_transcription()
        else TranscriptionStatus.not_required
    )
    return {
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

    affected = 0
    async with session_scope() as session:
        for chunk in _chunks(rows, UPSERT_CHUNK_SIZE):
            values = [_post_to_row(p) for p in chunk]
            stmt = pg_insert(posts).values(values)

            update_set: dict[str, Any] = {
                col: getattr(stmt.excluded, col) for col in _VOLATILE_UPDATE_COLUMNS
            }
            # Only advance transcription_status toward 'pending'; never downgrade
            # a row the transcriber has already started/finished.
            update_set["transcription_status"] = func.greatest(
                posts.c.transcription_status,
                stmt.excluded.transcription_status,
            )

            stmt = stmt.on_conflict_do_update(
                index_elements=[posts.c.platform, posts.c.platform_post_id],
                set_=update_set,
            )
            result = await session.execute(stmt)
            affected += result.rowcount or 0

    log.info("posts_upserted", count=affected, received=len(rows))
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
        "runs_by_status": runs_by_status,
        "recent_runs": recent_runs,
    }


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
