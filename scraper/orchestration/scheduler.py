"""Standalone scheduler - the "cron" process.

This is its OWN entrypoint/container. It must never import or run the FastAPI
app. Run it as a separate systemd service / container / cron-managed process
(see README). It runs two independent loops:

  * runner loop    - every ``RUNNER_INTERVAL_SECS``: start runs for due campaigns.
  * collector loop - every ``COLLECTOR_INTERVAL_SECS`` (more frequent): poll and
    ingest finished runs.

Campaigns are reloaded from ``campaigns.yaml`` each tick so edits are picked up
without a restart. Shuts down gracefully on SIGINT/SIGTERM.
"""

from __future__ import annotations

import asyncio
import signal

from scraper.apify.client import ApifyService
from scraper.config import get_settings, load_campaigns
from scraper.db.engine import dispose_engine
from scraper.logging_setup import configure_logging, get_logger
from scraper.orchestration import collector, runner

# Importing the platforms package populates the adapter registry via decorators.
import scraper.platforms  # noqa: F401

log = get_logger(__name__)


async def _runner_loop(apify: ApifyService, stop: asyncio.Event) -> None:
    settings = get_settings()
    while not stop.is_set():
        try:
            campaigns = load_campaigns()
            await runner.run_due_campaigns(apify, campaigns)
        except Exception as exc:  # keep the loop alive; surface the error
            log.error("runner_loop_error", error=str(exc), exc_info=True)
        await _sleep_or_stop(stop, settings.runner_interval_secs)


async def _collector_loop(apify: ApifyService, stop: asyncio.Event) -> None:
    settings = get_settings()
    while not stop.is_set():
        try:
            campaigns = load_campaigns()
            await collector.collect_finished_runs(apify, campaigns)
        except Exception as exc:
            log.error("collector_loop_error", error=str(exc), exc_info=True)
        await _sleep_or_stop(stop, settings.collector_interval_secs)


async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    """Sleep up to ``seconds`` but wake immediately if shutdown is requested."""
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


def _install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # e.g. Windows
            signal.signal(sig, lambda *_: stop.set())


async def run() -> None:
    """Run both loops until a shutdown signal is received."""
    settings = get_settings()
    configure_logging(settings.log_level)
    log.info(
        "scheduler_starting",
        runner_interval_secs=settings.runner_interval_secs,
        collector_interval_secs=settings.collector_interval_secs,
        max_concurrent_runs=settings.max_concurrent_runs,
        daily_budget_usd=settings.daily_budget_usd,
    )

    apify = ApifyService(token=settings.apify_token)
    stop = asyncio.Event()
    _install_signal_handlers(stop)

    tasks = [
        asyncio.create_task(_runner_loop(apify, stop), name="runner-loop"),
        asyncio.create_task(_collector_loop(apify, stop), name="collector-loop"),
    ]
    try:
        await stop.wait()
        log.info("scheduler_shutdown_requested")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await dispose_engine()
        log.info("scheduler_stopped")


def main() -> None:
    """Console-script entrypoint (``sigil-scheduler``)."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
