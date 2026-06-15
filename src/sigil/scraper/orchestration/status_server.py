"""Live status HTTP server hosted inside the scheduler process.

Whenever the scheduler (the process that actually runs the scrapers) is up, it
exposes a lightweight HTTP endpoint so operators / the dashboard can see what
each scraper is doing right now: which runs are in flight, how many items each
has fetched so far (queried live from Apify), and pipeline totals.

This runs as a third asyncio task alongside the runner and collector loops in
``scraper.orchestration.scheduler``. It never imports the validation FastAPI app.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import uvicorn
from fastapi import FastAPI

from sigil.scraper.apify.client import ApifyService
from sigil.config import get_settings, load_campaigns
from sigil.scraper.db import repository
from sigil.logging import get_logger

log = get_logger(__name__)


def _start_of_utc_day() -> datetime:
    now = datetime.now(tz=timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def _build_status(apify: ApifyService) -> dict[str, Any]:
    """Assemble the live status payload (DB counts + live Apify run stats)."""
    settings = get_settings()

    summary = await repository.status_summary()
    flagged_total, flagged_unreviewed = await repository.flagged_counts()
    spent_today = await repository.sum_cost_since(_start_of_utc_day())

    # Map campaign_id -> topic for friendlier output (best-effort).
    try:
        campaigns_by_id = {str(c.id): c for c in load_campaigns()}
    except Exception as exc:  # never let config issues break the status endpoint
        log.warning("status_load_campaigns_failed", error=str(exc))
        campaigns_by_id = {}

    running = await repository.fetch_running_runs()
    current_runs: list[dict[str, Any]] = []
    for run in running:
        apify_run_id = run.get("apify_run_id")
        run_status = run.get("status")
        items_fetched: int | None = None

        if apify_run_id:
            try:
                info = await apify.get_run(apify_run_id)
                run_status = info.status.value
                items_fetched = info.stats.get("itemCount")
                if items_fetched is None:
                    items_fetched = info.stats.get("readItemCount")
            except Exception as exc:  # transient Apify error; report what we have
                log.warning(
                    "status_apify_get_run_failed",
                    apify_run_id=apify_run_id,
                    error=str(exc),
                )

        campaign = campaigns_by_id.get(str(run.get("campaign_id")))
        current_runs.append(
            {
                "run_id": str(run["id"]),
                "platform": run.get("platform"),
                "campaign_id": str(run["campaign_id"]) if run.get("campaign_id") else None,
                "topic": campaign.topic if campaign else None,
                "apify_run_id": apify_run_id,
                "status": run_status,
                "items_fetched": items_fetched,
            }
        )

    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "posts_total": summary["posts_total"],
        "posts_pending_transcription": summary["posts_pending_transcription"],
        "flagged_total": flagged_total,
        "flagged_unreviewed": flagged_unreviewed,
        "runs_by_status": summary["runs_by_status"],
        "active_runs": len(current_runs),
        "daily_cost_usd": round(spent_today, 4),
        "daily_budget_usd": settings.daily_budget_usd,
        "current_runs": current_runs,
        "recent_runs": summary["recent_runs"],
    }


def create_status_app(apify: ApifyService) -> FastAPI:
    """Build the FastAPI app exposing scraper status routes."""
    app = FastAPI(
        title="Sigil Scraper Status",
        version="0.1.0",
        description="Live status of the scraper scheduler: in-flight runs, "
        "items fetched, and pipeline totals.",
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Liveness probe (does not touch the database)."""
        return {"status": "ok"}

    @app.get("/status")
    async def status() -> dict[str, Any]:
        """Live scraper status: current runs, items fetched, totals."""
        return await _build_status(apify)

    return app


async def serve_status(apify: ApifyService, stop: asyncio.Event) -> None:
    """Run the status HTTP server until ``stop`` is set (cancel-safe)."""
    settings = get_settings()
    config = uvicorn.Config(
        create_status_app(apify),
        host=settings.status_host,
        port=settings.status_port,
        log_level=settings.log_level.lower(),
        lifespan="off",
    )
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve(), name="status-server-uvicorn")
    log.info(
        "status_server_starting",
        host=settings.status_host,
        port=settings.status_port,
    )
    try:
        await stop.wait()
    finally:
        server.should_exit = True
        await serve_task
        log.info("status_server_stopped")
