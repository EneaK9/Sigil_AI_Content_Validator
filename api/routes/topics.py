"""
Topic intelligence endpoint for the Sondë frontend.
"""
import asyncio
import logging
import time

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_checker
from services.topic_report import build_topic_report

logger = logging.getLogger("policyguard.api.topics")

router = APIRouter()


@router.get(
    "/topics",
    summary="Build a topic intelligence report",
    description=(
        "Search platforms for posts about a topic, run policy checks on the "
        "top posts, and return one assembled TopicReport (posts, flags, "
        "sentiment, influencers, volume, top accounts). Reddit is the live "
        "source; other platforms are reported as not live until search "
        "adapters exist for them."
    ),
)
async def get_topic_report(
    q: str = Query(..., min_length=2, description="Topic to probe"),
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
    max_checks: int = Query(5, ge=0, le=20, description="Max posts to policy-check with Claude"),
) -> dict:
    """
    Assemble a TopicReport for the given topic.

    Policy flags and sentiment require ANTHROPIC_API_KEY; without it the
    report still returns with live posts but no flags and a neutral
    sentiment estimate.
    """
    start = time.time()
    logger.info(f"[TOPICS] Probing topic: '{q}' (days={days}, max_checks={max_checks})")

    checker = get_checker()
    loop = asyncio.get_event_loop()

    try:
        # The build is blocking (HTTP search + Claude calls) - run off the event loop.
        report = await loop.run_in_executor(
            None, build_topic_report, q, days, checker, max_checks
        )
    except Exception as e:
        logger.error(f"[TOPICS] Report build failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Topic report failed: {e}")

    elapsed = time.time() - start
    logger.info(
        f"[TOPICS] Report ready: {report['metrics']['postsFound']} posts, "
        f"{report['metrics']['flaggedForReview']} flagged ({elapsed:.1f}s)"
    )
    return report
