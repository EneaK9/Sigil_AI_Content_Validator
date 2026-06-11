"""Sigil Social Scraper API - Status + Validation.

This app provides:
  - Health/status endpoints for the scraper pipeline
  - Validation endpoints to run policy compliance checks on scraped posts
  - Violations reporting endpoints

The scraping/cron work lives in ``scraper.orchestration.scheduler`` as a
separate process. This API can trigger validation but not scraping.

Run::

    uvicorn scraper.api.main:app --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Optional
from uuid import UUID

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from pydantic import BaseModel

from scraper.config import get_settings
from scraper.db import repository
from scraper.db.engine import dispose_engine
from scraper.integration.pipeline import (
    fetch_violations,
    get_validation_stats,
    validate_scraped_posts,
)
from scraper.logging_setup import configure_logging


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(get_settings().log_level)
    yield
    await dispose_engine()


app = FastAPI(
    title="Sigil Social Scraper API",
    version="0.2.0",
    description="Scraper pipeline status, validation, and violations reporting.",
    lifespan=_lifespan,
)


class ValidateRequest(BaseModel):
    """Request body for the validate endpoint."""
    campaign_id: Optional[str] = None
    platform: Optional[str] = None
    limit: int = 100


class ValidateResponse(BaseModel):
    """Response from the validate endpoint."""
    message: str
    total_processed: int
    passed: int
    failed: int
    errors: int
    violations: list[dict[str, Any]]


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe. Does not touch the database."""
    return {"status": "ok"}


@app.get("/status")
async def status() -> dict[str, Any]:
    """Pipeline status: post counts, run counts by status, recent runs."""
    return await repository.status_summary()


@app.post("/validate", response_model=ValidateResponse)
async def validate_posts(request: ValidateRequest) -> ValidateResponse:
    """Validate pending scraped posts against platform policies.
    
    This endpoint fetches posts that haven't been validated yet, runs them
    through the Claude-based policy compliance judge, and stores the results.
    
    - **campaign_id**: Optional UUID to filter by campaign
    - **platform**: Optional platform filter (tiktok, instagram, facebook)
    - **limit**: Maximum number of posts to validate (default: 100)
    """
    campaign_id = UUID(request.campaign_id) if request.campaign_id else None
    
    if request.platform and request.platform not in ["tiktok", "instagram", "facebook"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform: {request.platform}. Must be tiktok, instagram, or facebook."
        )
    
    results = await validate_scraped_posts(
        campaign_id=campaign_id,
        platform=request.platform,
        limit=request.limit,
    )
    
    passed = [r for r in results if r.get("status") == "pass"]
    failed = [r for r in results if r.get("status") == "fail"]
    errors = [r for r in results if r.get("status") == "error"]
    
    return ValidateResponse(
        message=f"Validated {len(results)} posts",
        total_processed=len(results),
        passed=len(passed),
        failed=len(failed),
        errors=len(errors),
        violations=failed,
    )


@app.get("/violations")
async def get_violations(
    platform: Optional[str] = Query(None, description="Filter by platform"),
    severity: Optional[str] = Query(None, description="Filter by severity (HIGH, MEDIUM, LOW)"),
    limit: int = Query(100, description="Maximum number of results"),
) -> dict[str, Any]:
    """Get posts that failed policy validation (have violations).
    
    Returns posts grouped with their violation details.
    
    - **platform**: Optional filter (tiktok, instagram, facebook)
    - **severity**: Optional severity filter (HIGH, MEDIUM, LOW)
    - **limit**: Maximum results to return (default: 100)
    """
    if platform and platform not in ["tiktok", "instagram", "facebook"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform: {platform}. Must be tiktok, instagram, or facebook."
        )
    
    if severity and severity not in ["HIGH", "MEDIUM", "LOW"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid severity: {severity}. Must be HIGH, MEDIUM, or LOW."
        )
    
    violations = await fetch_violations(
        platform=platform,
        severity=severity,
        limit=limit,
    )
    
    by_platform: dict[str, list[dict[str, Any]]] = {}
    for row in violations:
        plat = row.get("platform", "unknown")
        if plat not in by_platform:
            by_platform[plat] = []
        by_platform[plat].append({
            "post_id": str(row.get("id")),
            "url": row.get("url"),
            "author": row.get("author_handle"),
            "content_preview": (row.get("content_text") or "")[:200],
            "violations": row.get("violations", []),
            "confidence": float(row.get("validation_confidence") or 0),
            "validated_at": row.get("validated_at").isoformat() if row.get("validated_at") else None,
        })
    
    total_violations = sum(
        len(row.get("violations", [])) for row in violations
    )
    
    return {
        "total_posts": len(violations),
        "total_violations": total_violations,
        "by_platform": by_platform,
    }


@app.get("/validation/stats")
async def validation_stats() -> dict[str, Any]:
    """Get validation statistics summary.
    
    Returns counts of validated posts by status and platform.
    """
    return await get_validation_stats()
