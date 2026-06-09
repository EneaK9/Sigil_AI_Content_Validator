"""Collector: poll running runs, ingest finished ones.

For each run currently in ``running``:
  * SUCCEEDED  -> stream the dataset, normalize, bulk-upsert, finish succeeded.
  * FAILED / TIMED-OUT / ABORTED -> record the error and finish failed/aborted.
    The campaign is naturally re-queued by the runner on its next tick (the
    runner interval provides backoff), capped by ``MAX_RUN_RETRIES``.
  * still READY/RUNNING -> leave it for the next poll.

Normalization failures on individual items are counted (``items_failed``) and
skipped - one bad item never aborts a whole ingest.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from scraper.apify.client import ApifyRunStatus, ApifyService
from scraper.db import repository
from scraper.db.repository import UPSERT_CHUNK_SIZE
from scraper.logging_setup import get_logger
from scraper.models import Campaign, NormalizedPost, Platform, RunStatus
from scraper.platforms.base import get_scraper

log = get_logger(__name__)


async def collect_finished_runs(
    apify: ApifyService, campaigns: list[Campaign]
) -> int:
    """Poll all running runs and ingest finished ones. Returns runs finalized."""
    campaign_by_id: dict[UUID, Campaign] = {c.id: c for c in campaigns}
    running = await repository.fetch_running_runs()
    finalized = 0

    for row in running:
        run_id: UUID = row["id"]
        apify_run_id: str | None = row["apify_run_id"]
        dataset_id: str | None = row["apify_dataset_id"]
        platform = Platform(row["platform"])
        campaign_id: UUID = row["campaign_id"]
        rlog = log.bind(
            run_id=str(run_id),
            apify_run_id=apify_run_id,
            campaign_id=str(campaign_id),
            platform=platform.value,
        )

        if not apify_run_id:
            await repository.finish_run(
                run_id=run_id,
                status=RunStatus.failed,
                error="missing apify_run_id",
            )
            rlog.error("run_missing_apify_id")
            finalized += 1
            continue

        try:
            info = await apify.get_run(apify_run_id)
        except Exception as exc:
            rlog.warning("get_run_failed_will_retry", error=str(exc))
            continue  # transient; try again next poll

        if not info.status.is_terminal:
            rlog.debug("run_still_running", status=info.status.value)
            continue

        if info.status.is_success:
            campaign = campaign_by_id.get(campaign_id)
            if campaign is None:
                # Campaign no longer in config; we can't normalize without it.
                await repository.finish_run(
                    run_id=run_id,
                    status=RunStatus.failed,
                    cost_usd=info.cost_usd,
                    error="campaign not found in current config",
                )
                rlog.error("campaign_not_in_config")
                finalized += 1
                continue
            await _ingest_dataset(
                apify, info.dataset_id, run_id, campaign, platform, info.cost_usd, rlog
            )
            finalized += 1
        else:
            status = (
                RunStatus.aborted
                if info.status is ApifyRunStatus.ABORTED
                else RunStatus.failed
            )
            await repository.finish_run(
                run_id=run_id,
                status=status,
                cost_usd=info.cost_usd,
                error=f"apify status {info.status.value}",
            )
            rlog.warning("run_failed", apify_status=info.status.value)
            finalized += 1

    log.info("collector_tick_complete", runs_finalized=finalized, polled=len(running))
    return finalized


async def _ingest_dataset(
    apify: ApifyService,
    dataset_id: str | None,
    run_id: UUID,
    campaign: Campaign,
    platform: Platform,
    cost_usd: float | None,
    rlog: Any,
) -> None:
    if not dataset_id:
        await repository.finish_run(
            run_id=run_id,
            status=RunStatus.failed,
            cost_usd=cost_usd,
            error="succeeded run had no dataset_id",
        )
        rlog.error("succeeded_run_no_dataset")
        return

    adapter = get_scraper(platform)
    ingested = 0
    failed = 0
    batch: list[NormalizedPost] = []

    try:
        async for raw_item in apify.iter_dataset_items(dataset_id):
            try:
                post = adapter.normalize(raw_item, campaign)
            except Exception as exc:  # never let one item kill the ingest
                failed += 1
                rlog.warning("normalize_error", error=str(exc))
                continue
            if post is None:
                continue
            batch.append(post)
            if len(batch) >= UPSERT_CHUNK_SIZE:
                ingested += await repository.upsert_posts(batch)
                batch = []
        if batch:
            ingested += await repository.upsert_posts(batch)
    except Exception as exc:
        # Dataset streaming / DB error after partial ingest: record what we got.
        await repository.finish_run(
            run_id=run_id,
            status=RunStatus.failed,
            items_ingested=ingested,
            items_failed=failed,
            cost_usd=cost_usd,
            error=f"ingest error: {exc!r}",
        )
        rlog.error("ingest_failed", error=str(exc), items_ingested=ingested)
        return

    await repository.finish_run(
        run_id=run_id,
        status=RunStatus.succeeded,
        items_ingested=ingested,
        items_failed=failed,
        cost_usd=cost_usd,
    )
    rlog.info(
        "run_ingested",
        items_ingested=ingested,
        items_failed=failed,
        cost_usd=cost_usd,
    )
