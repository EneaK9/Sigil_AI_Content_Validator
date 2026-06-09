"""Repository upsert/dedup test against a real local Postgres.

Skipped unless ``TEST_DATABASE_URL`` is set (SQLAlchemy asyncpg URL form,
e.g. ``postgresql+asyncpg://postgres:postgres@localhost:5432/scraper_test``).
This points the engine module at the test DB, applies the migration, and
verifies that re-ingesting the same post does not create duplicate rows.
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.conftest import TEST_CAMPAIGN_ID

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DB_URL, reason="TEST_DATABASE_URL not set; skipping live DB test"
)

MIGRATION = (
    Path(__file__).parents[1]
    / "scraper"
    / "db"
    / "migrations"
    / "0001_init.sql"
)


@pytest.fixture
async def wired_db(monkeypatch):
    """Point scraper.db.engine at the test database and apply the schema."""
    from scraper.db import engine as engine_mod
    from scraper.db.tables import scrape_campaigns

    test_engine = create_async_engine(TEST_DB_URL, connect_args={"statement_cache_size": 0})

    # Apply migration via the raw asyncpg connection (handles the DO $$ block).
    sql = MIGRATION.read_text(encoding="utf-8")
    async with test_engine.begin() as conn:
        raw = await conn.get_raw_connection()
        await raw.driver_connection.execute(sql)

    sm = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    monkeypatch.setattr(engine_mod, "_engine", test_engine)
    monkeypatch.setattr(engine_mod, "_sessionmaker", sm)

    # Seed a campaign row so the FK on posts.campaign_id is satisfiable.
    async with sm() as session:
        await session.execute(
            scrape_campaigns.insert().values(
                id=TEST_CAMPAIGN_ID,
                platform="tiktok",
                topic="t",
                seeds=[],
            )
        )
        await session.commit()

    yield sm

    # Clean up created rows (FK order: posts/runs before campaigns) and dispose.
    from sqlalchemy import delete

    from scraper.db.tables import posts, scrape_campaigns, scrape_runs

    async with sm() as session:
        await session.execute(delete(posts))
        await session.execute(delete(scrape_runs))
        await session.execute(delete(scrape_campaigns))
        await session.commit()
    await test_engine.dispose()


def _make_post(like_count: int):
    from scraper.models import NormalizedPost, Platform

    return NormalizedPost(
        platform=Platform.tiktok,
        platform_post_id="dedup-1",
        url="https://example.com/v/1",
        author_handle="a",
        content_text="hi #x",
        like_count=like_count,
        has_video=True,
        video_url="https://example.com/v/1.mp4",
        hashtags=["x"],
        country="US",
        topic="t",
        campaign_id=TEST_CAMPAIGN_ID,
    )


@pytest.mark.asyncio
async def test_upsert_is_idempotent_and_updates_volatile(wired_db) -> None:
    from scraper.db import repository
    from scraper.db.tables import posts

    sm = wired_db

    # First ingest.
    await repository.upsert_posts([_make_post(like_count=10)])
    # Re-ingest same post id with updated counts.
    await repository.upsert_posts([_make_post(like_count=99)])

    async with sm() as session:
        total = (
            await session.execute(select(func.count()).select_from(posts))
        ).scalar_one()
        like = (
            await session.execute(
                select(posts.c.like_count).where(posts.c.platform_post_id == "dedup-1")
            )
        ).scalar_one()
        status = (
            await session.execute(
                select(posts.c.transcription_status).where(
                    posts.c.platform_post_id == "dedup-1"
                )
            )
        ).scalar_one()

    assert total == 1  # no duplicate row
    assert like == 99  # volatile field refreshed
    assert status == "pending"  # video -> queued for transcription


@pytest.mark.asyncio
async def test_run_lifecycle(wired_db) -> None:
    from scraper.db import repository
    from scraper.models import Platform, RunStatus

    run_id = uuid4()
    await repository.create_run(
        run_id=run_id,
        campaign_id=TEST_CAMPAIGN_ID,
        platform=Platform.tiktok,
        apify_run_id="ar1",
        apify_dataset_id="ds1",
        status=RunStatus.running,
    )
    running = await repository.fetch_running_runs()
    assert any(r["id"] == run_id for r in running)

    await repository.finish_run(
        run_id=run_id,
        status=RunStatus.succeeded,
        items_ingested=5,
        cost_usd=0.25,
    )
    running_after = await repository.fetch_running_runs()
    assert all(r["id"] != run_id for r in running_after)
