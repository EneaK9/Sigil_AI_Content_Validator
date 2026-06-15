"""SQLAlchemy Core table definitions mirroring 0001_init.sql.

Core (not ORM) is used deliberately: it gives clean access to the PostgreSQL
``INSERT ... ON CONFLICT`` construct for bulk idempotent upserts. The enum types
are referenced with ``create_type=False`` because the SQL migration owns them.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, BIGINT, ENUM, JSONB, TIMESTAMP, UUID

metadata = MetaData()

platform_enum = ENUM(
    "tiktok", "instagram", "facebook", "linkedin", "twitter",
    name="platform_t",
    create_type=False,
)
run_status_enum = ENUM(
    "requested", "running", "succeeded", "failed", "aborted",
    name="run_status_t",
    create_type=False,
)
transcription_enum = ENUM(
    "not_required", "pending", "processing", "done", "failed",
    name="transcription_t",
    create_type=False,
)
validation_status_enum = ENUM(
    "pending", "processing", "pass", "fail", "error",
    name="validation_status_t",
    create_type=False,
)

scrape_campaigns = Table(
    "scrape_campaigns",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("platform", platform_enum, nullable=False),
    Column("topic", Text, nullable=False),
    Column("country", Text),
    Column("seeds", JSONB, nullable=False, server_default=text("'[]'")),
    Column("daily_target", Integer, nullable=False, server_default=text("0")),
    Column("enabled", Boolean, nullable=False, server_default=text("true")),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
)

scrape_runs = Table(
    "scrape_runs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("campaign_id", UUID(as_uuid=True), ForeignKey("scrape_campaigns.id")),
    Column("platform", platform_enum, nullable=False),
    Column("apify_run_id", Text),
    Column("apify_dataset_id", Text),
    Column("status", run_status_enum, nullable=False, server_default=text("'requested'")),
    Column("items_ingested", Integer, nullable=False, server_default=text("0")),
    Column("items_failed", Integer, nullable=False, server_default=text("0")),
    Column("cost_usd", Numeric(10, 4)),
    Column("error", Text),
    Column("requested_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("started_at", TIMESTAMP(timezone=True)),
    Column("finished_at", TIMESTAMP(timezone=True)),
)

posts = Table(
    "posts",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("platform", platform_enum, nullable=False),
    Column("platform_post_id", Text, nullable=False),
    Column("campaign_id", UUID(as_uuid=True), ForeignKey("scrape_campaigns.id")),
    Column("url", Text),
    Column("author_handle", Text),
    Column("author_id", Text),
    Column("author_url", Text),
    Column("content_text", Text),
    Column("lang", Text),
    Column("posted_at", TIMESTAMP(timezone=True)),
    Column("like_count", BIGINT),
    Column("comment_count", BIGINT),
    Column("share_count", BIGINT),
    Column("view_count", BIGINT),
    Column("media_type", Text),
    Column("has_video", Boolean, nullable=False, server_default=text("false")),
    Column("video_url", Text),
    Column("audio_url", Text),
    Column("thumbnail_url", Text),
    Column("hashtags", ARRAY(Text), server_default=text("'{}'")),
    Column("mentions", ARRAY(Text), server_default=text("'{}'")),
    Column("country", Text),
    Column("country_confidence", Numeric(4, 3)),
    Column("topic", Text),
    Column("transcription_status", transcription_enum, nullable=False, server_default=text("'not_required'")),
    Column("transcript", Text),
    Column("raw", JSONB, nullable=False),
    Column("scraped_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    # Validation columns (added by 0002_validation.sql)
    Column("validation_status", validation_status_enum, server_default=text("'pending'")),
    Column("verdict", Text),
    Column("violations", JSONB, server_default=text("'[]'")),
    Column("validation_confidence", Numeric(4, 3)),
    Column("validation_recommendation", Text),
    Column("validated_at", TIMESTAMP(timezone=True)),
)

# Flagged posts (added by 0003_flagged_posts.sql). Stores report-ready, flattened
# cells for posts judged CLEAR_VIOLATION - never the raw verdict object.
flagged_posts = Table(
    "flagged_posts",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("post_id", UUID(as_uuid=True), ForeignKey("posts.id")),
    Column("platform", platform_enum, nullable=False),
    Column("category", Text),
    Column("warnings_count", Integer, nullable=False, server_default=text("0")),
    Column("warning_categories", Text),
    Column("warning_affected_groups", Text),
    Column("platform_post_id", Text),
    Column("url", Text),
    Column("author", Text),
    Column("content_text", Text),
    Column("posted_at", TIMESTAMP(timezone=True)),
    Column("like_count", BIGINT),
    Column("comment_count", BIGINT),
    Column("view_count", BIGINT),
    Column("hashtags", Text),
    Column("violation_quotes", Text),
    Column("violation_policy_refs", Text),
    Column("tos_cross_reference", Text),
    Column("violation_explanation", Text),
    Column("report_text", Text),
    Column("added_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("is_reviewed", Boolean, nullable=False, server_default=text("false")),
)
