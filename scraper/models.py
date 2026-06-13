"""Pydantic domain models shared across the scraper.

These are the in-process representations. The persisted shapes live in
``db/migrations/0001_init.sql``; ``NormalizedPost`` maps 1:1 onto the ``posts``
table and ``ScrapeRun`` onto ``scrape_runs``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Platform(str, Enum):
    """Supported platforms. Mirrors the ``platform_t`` Postgres enum."""

    tiktok = "tiktok"
    instagram = "instagram"
    facebook = "facebook"
    linkedin = "linkedin"
    reddit = "reddit"
    twitter = "twitter"


class RunStatus(str, Enum):
    """Lifecycle of a scrape run. Mirrors the ``run_status_t`` Postgres enum."""

    requested = "requested"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    aborted = "aborted"


class TranscriptionStatus(str, Enum):
    """Transcription seam. Mirrors the ``transcription_t`` Postgres enum.

    The scraper only ever writes ``not_required`` or ``pending``; the future
    transcriber owns the rest of the lifecycle.
    """

    not_required = "not_required"
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"


class Campaign(BaseModel):
    """A unit of scraping work: ``(platform, topic, country, seeds)``.

    ``seeds`` is a flat list of strings whose meaning is platform-specific and
    is interpreted by each adapter's ``build_input`` (hashtags / search queries
    for TikTok & Instagram, page URLs for Facebook).
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    platform: Platform
    topic: str
    country: str | None = None
    seeds: list[str] = Field(default_factory=list)
    daily_target: int = 0
    enabled: bool = True


class NormalizedPost(BaseModel):
    """One post, normalized across platforms. Maps 1:1 onto the ``posts`` table.

    Adapters MUST set ``has_video`` / ``video_url`` (and ``audio_url`` when
    available) so the future transcriber knows what to process.
    """

    platform: Platform
    platform_post_id: str  # native id; the dedup key together with platform
    url: str | None = None

    author_handle: str | None = None
    author_id: str | None = None
    author_url: str | None = None

    content_text: str | None = None
    lang: str | None = None
    posted_at: datetime | None = None

    like_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    view_count: int | None = None

    media_type: str | None = None  # "video" | "image" | "carousel" | "text"
    has_video: bool = False
    video_url: str | None = None
    audio_url: str | None = None
    thumbnail_url: str | None = None

    hashtags: list[str] = Field(default_factory=list)
    mentions: list[str] = Field(default_factory=list)

    country: str | None = None  # campaign label, NOT ground truth
    country_confidence: float | None = None
    topic: str | None = None

    campaign_id: UUID
    scraped_at: datetime = Field(default_factory=_utcnow)

    raw: dict[str, Any] = Field(default_factory=dict)  # FULL Apify item, verbatim

    def needs_transcription(self) -> bool:
        """Whether this post should be queued for transcription on ingest."""
        return bool(self.has_video or self.video_url or self.audio_url)


class ScrapeRun(BaseModel):
    """A single Apify actor run tracked in ``scrape_runs``."""

    id: UUID
    campaign_id: UUID
    platform: Platform
    apify_run_id: str | None = None
    apify_dataset_id: str | None = None
    status: RunStatus = RunStatus.requested
    items_ingested: int = 0
    items_failed: int = 0
    cost_usd: float | None = None
    error: str | None = None
    requested_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
