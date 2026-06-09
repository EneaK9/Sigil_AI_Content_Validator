"""Optional FastAPI app - health/status ONLY.

This app NEVER starts scrapes or runs the scheduler. It is a read-only window
into the pipeline's state (counts + recent runs). The scraping/cron work lives
entirely in ``scraper.orchestration.scheduler`` as a separate process.

Run (optional)::

    uvicorn scraper.api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from scraper.config import get_settings
from scraper.db import repository
from scraper.db.engine import dispose_engine
from scraper.logging_setup import configure_logging


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(get_settings().log_level)
    yield
    await dispose_engine()


app = FastAPI(
    title="Sigil Social Scraper - Status API",
    version="0.1.0",
    description="Read-only health/status for the scraper pipeline. Does not run scrapes.",
    lifespan=_lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe. Does not touch the database."""
    return {"status": "ok"}


@app.get("/status")
async def status() -> dict[str, Any]:
    """Pipeline status: post counts, run counts by status, recent runs."""
    return await repository.status_summary()
