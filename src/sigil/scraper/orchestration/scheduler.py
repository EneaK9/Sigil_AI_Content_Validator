"""Standalone scheduler - the "cron" process.

This is its OWN entrypoint/container. It must never import or run the FastAPI
app. Run it as a separate systemd service / container / cron-managed process
(see README). It runs two independent loops:

  * runner loop     - every ``RUNNER_INTERVAL_SECS``: start runs for due campaigns.
  * collector loop  - every ``COLLECTOR_INTERVAL_SECS`` (more frequent): poll and
    ingest finished runs.
  * validation loop - every ``VALIDATION_INTERVAL_SECS``: drain the pending-post
    queue through the LLM judge into ``flagged_posts``.

Campaigns are reloaded from ``campaigns.yaml`` each tick so edits are picked up
without a restart. Shuts down gracefully on SIGINT/SIGTERM.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
from collections.abc import Iterable

from sigil.scraper.apify.client import ApifyService
from sigil.config import get_settings, load_campaigns
from sigil.scraper.db.engine import dispose_engine
from sigil.logging import configure_logging, get_logger
from sigil.pipeline.pipeline import validate_scraped_posts
from sigil.scraper.orchestration import collector, runner
from sigil.scraper.orchestration.status_server import serve_status

# Importing the platforms package populates the adapter registry via decorators.
import sigil.scraper.platforms  # noqa: F401

log = get_logger(__name__)

# Selectable loops. ``runner``/``collector``/``status`` need Apify; ``validator``
# only needs the LLM + Supabase, so it can run completely on its own.
COMPONENTS = ("runner", "collector", "validator", "status")
_APIFY_COMPONENTS = frozenset({"runner", "collector", "status"})


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


async def _validation_loop(stop: asyncio.Event) -> None:
    settings = get_settings()
    if not settings.validation_enabled:
        log.info("validation_loop_disabled")
        return
    while not stop.is_set():
        try:
            await _drain_pending_validation(settings, stop)
        except Exception as exc:  # keep the loop alive; surface the error
            log.error("validation_loop_error", error=str(exc), exc_info=True)
        await _sleep_or_stop(stop, settings.validation_interval_secs)


async def _drain_pending_validation(settings, stop: asyncio.Event) -> int:
    """Validate pending posts in batches until the queue is empty (or we stop).

    A single tick keeps pulling ``validation_batch_limit``-sized batches while
    they come back full, so a large backlog is cleared without waiting a full
    interval between batches.
    """
    total = 0
    while not stop.is_set():
        results = await validate_scraped_posts(
            limit=settings.validation_batch_limit,
            concurrency=settings.validation_concurrency,
        )
        total += len(results)
        if len(results) < settings.validation_batch_limit:
            break  # queue drained for now
    if total:
        log.info("validation_drain_complete", validated=total)
    return total


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


async def run(components: Iterable[str] = COMPONENTS) -> None:
    """Run the selected loops until a shutdown signal is received.

    ``components`` selects which loops start (defaults to all). Apify is only
    constructed when a loop that needs it is enabled, so a validator-only run
    never touches Apify.
    """
    enabled = list(dict.fromkeys(components))  # de-dupe, preserve order
    unknown = [c for c in enabled if c not in COMPONENTS]
    if unknown:
        raise ValueError(
            f"Unknown component(s): {', '.join(unknown)}. "
            f"Valid components: {', '.join(COMPONENTS)}"
        )
    if not enabled:
        raise ValueError(f"No components selected. Choose from: {', '.join(COMPONENTS)}")

    settings = get_settings()
    configure_logging(settings.log_level)
    log.info(
        "scheduler_starting",
        components=enabled,
        runner_interval_secs=settings.runner_interval_secs,
        collector_interval_secs=settings.collector_interval_secs,
        validation_enabled=settings.validation_enabled,
        validation_interval_secs=settings.validation_interval_secs,
        max_concurrent_runs=settings.max_concurrent_runs,
        daily_budget_usd=settings.daily_budget_usd,
        status_host=settings.status_host,
        status_port=settings.status_port,
    )

    stop = asyncio.Event()
    _install_signal_handlers(stop)

    apify = (
        ApifyService(token=settings.apify_token)
        if _APIFY_COMPONENTS.intersection(enabled)
        else None
    )

    loop_factories = {
        "runner": lambda: _runner_loop(apify, stop),
        "collector": lambda: _collector_loop(apify, stop),
        "validator": lambda: _validation_loop(stop),
        "status": lambda: serve_status(apify, stop),
    }
    task_names = {
        "runner": "runner-loop",
        "collector": "collector-loop",
        "validator": "validation-loop",
        "status": "status-server",
    }
    tasks = [
        asyncio.create_task(loop_factories[c](), name=task_names[c]) for c in enabled
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
    parser = argparse.ArgumentParser(
        prog="sigil-scheduler",
        description="Run the Sigil orchestration loops (runner, collector, "
        "validator, status). Defaults to all.",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        choices=COMPONENTS,
        metavar="COMPONENT",
        help="Run only the selected loop(s), e.g. --only validator. "
        f"Choices: {', '.join(COMPONENTS)}. Default: all.",
    )
    args = parser.parse_args()
    asyncio.run(run(args.only or COMPONENTS))


def validator_main() -> None:
    """Console-script entrypoint (``sigil-validator``): run only the validator."""
    asyncio.run(run(["validator"]))


if __name__ == "__main__":
    main()
