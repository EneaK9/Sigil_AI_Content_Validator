"""Runner: start Apify runs for due campaigns.

Capacity reasoning (target ~40,000 posts/day):
  * 40k/day ~= 1.7k/hour. We deliberately start at most one run per campaign per
    scheduler tick and gate each campaign by ``daily_target`` so volume is spread
    across the day instead of bursting (avoids Apify rate-limit/cost spikes).
  * Prefer FEW LARGE runs over many small ones: a single run carries ALL of a
    campaign's seeds (hashtags/queries/urls); the per-run ``resultsLimit`` is the
    throughput lever. We only conceptually "split" a campaign into multiple runs
    across ticks when its ``daily_target`` exceeds one run's results.
  * ``MAX_CONCURRENT_RUNS``, ``RESULTS_LIMIT_PER_RUN`` and run cadence are all
    config values so throughput can be tuned without code changes.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from uuid import uuid4

from typing import Any

from scraper.apify.client import ApifyService
from scraper.config import get_settings
from scraper.db import repository
from scraper.logging_setup import get_logger
from scraper.models import Campaign, RunStatus
from scraper.platforms.base import PlatformScraper, get_scraper

log = get_logger(__name__)


def _start_of_utc_day() -> datetime:
    now = datetime.now(tz=timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _runs_needed_today(daily_target: int, per_run_limit: int) -> int:
    """How many runs are needed to reach the daily target for a campaign."""
    if daily_target <= 0:
        return 1
    return max(1, math.ceil(daily_target / max(1, per_run_limit)))


async def run_due_campaigns(
    apify: ApifyService, campaigns: list[Campaign]
) -> int:
    """Start runs for every due campaign, honoring concurrency + budget guards.

    Returns the number of runs started this tick.
    """
    settings = get_settings()
    start_of_day = _start_of_utc_day()
    per_run_limit = min(
        settings.results_limit_per_run, settings.actor_max_results_per_run
    )
    if settings.results_limit_per_run > settings.actor_max_results_per_run:
        log.warning(
            "results_limit_capped_to_actor_max",
            requested=settings.results_limit_per_run,
            actor_max=settings.actor_max_results_per_run,
        )

    # Sync YAML campaigns into scrape_campaigns first so the scrape_runs /
    # posts foreign keys are satisfied (campaign ids are deterministic UUID5s).
    await repository.upsert_campaigns(campaigns)

    started = 0
    for campaign in campaigns:
        if not campaign.enabled:
            continue

        try:
            adapter = get_scraper(campaign.platform)
        except KeyError:
            log.warning("no_adapter_for_platform", platform=campaign.platform.value)
            continue
        if not adapter.enabled:
            log.info(
                "platform_disabled_skipped",
                platform=campaign.platform.value,
                campaign_id=str(campaign.id),
            )
            continue

        clog = log.bind(campaign_id=str(campaign.id), platform=campaign.platform.value)

        # Avoid double-starting a campaign that already has a run in flight.
        if await repository.has_running_run_for_campaign(campaign.id):
            clog.debug("campaign_has_running_run_skipped")
            continue

        # Daily target throttle.
        needed = _runs_needed_today(campaign.daily_target, per_run_limit)
        done = await repository.count_runs_today(campaign.id, since=start_of_day)
        if done >= needed:
            clog.debug("campaign_target_met", runs_done=done, runs_needed=needed)
            continue

        # Capped retries: stop re-queuing a campaign once it has burned through
        # its needed runs plus the allowed retry budget for the day.
        attempts = await repository.count_attempts_for_campaign(
            campaign.id, since=start_of_day
        )
        if attempts >= needed + settings.max_run_retries:
            clog.warning(
                "max_attempts_reached",
                attempts=attempts,
                needed=needed,
                max_retries=settings.max_run_retries,
            )
            continue

        # Concurrency guard.
        active = await repository.count_active_runs()
        if active >= settings.max_concurrent_runs:
            clog.info("max_concurrency_reached", active=active)
            break  # nothing else will start this tick either

        # Daily budget guard: spent so far + in-flight estimate + this run.
        spent = await repository.sum_cost_since(start_of_day)
        projected = spent + (active + 1) * settings.est_cost_per_run_usd
        if projected > settings.daily_budget_usd:
            clog.warning(
                "daily_budget_guard_skip",
                spent_usd=round(spent, 4),
                projected_usd=round(projected, 4),
                budget_usd=settings.daily_budget_usd,
            )
            continue

        await _start_one_run(apify, adapter, campaign, clog)
        started += 1

    log.info("runner_tick_complete", runs_started=started)
    return started


async def _start_one_run(
    apify: ApifyService,
    adapter: PlatformScraper,
    campaign: Campaign,
    clog: Any,
) -> None:
    run_id = uuid4()
    run_input = adapter.build_input(campaign)
    try:
        info = await apify.start_run(
            adapter.actor_id,
            run_input,
            timeout_secs=None,
        )
    except Exception as exc:  # transport error survived retries
        # Record the failed attempt so it is visible and counts toward retries.
        await repository.create_run(
            run_id=run_id,
            campaign_id=campaign.id,
            platform=campaign.platform,
            status=RunStatus.failed,
        )
        await repository.finish_run(
            run_id=run_id,
            status=RunStatus.failed,
            error=f"start_run failed: {exc!r}",
        )
        clog.error("apify_start_failed", error=str(exc))
        return

    await repository.create_run(
        run_id=run_id,
        campaign_id=campaign.id,
        platform=campaign.platform,
        apify_run_id=info.run_id,
        apify_dataset_id=info.dataset_id,
        status=RunStatus.running,
    )
    clog.info(
        "run_started",
        run_id=str(run_id),
        apify_run_id=info.run_id,
        dataset_id=info.dataset_id,
        actor_id=adapter.actor_id,
    )
