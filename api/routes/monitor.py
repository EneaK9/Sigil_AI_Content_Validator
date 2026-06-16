"""
Report-result monitoring endpoints.

Re-check whether previously-flagged posts are still live. This is the seam the
dashboard's re-crawl monitor calls to learn what happened to a reported post,
without needing access to any platform's internal moderation decisions.
"""
import asyncio
import logging

from fastapi import APIRouter

from api.schemas.requests import RecheckInput
from api.schemas.responses import AvailabilityResponse, RecheckResponse
from core.availability import check_availability

logger = logging.getLogger("policyguard.api.monitor")

router = APIRouter()


@router.post(
    "/recheck",
    response_model=RecheckResponse,
    summary="Re-check availability of previously-seen posts",
    description=(
        "Re-visit each URL and report whether it is still live, removed, or "
        "restricted. Used by report-result monitoring as a proxy for the action "
        "a platform took on a reported post."
    ),
)
async def recheck(recheck_input: RecheckInput) -> RecheckResponse:
    """Re-check a batch of post URLs concurrently."""
    urls = recheck_input.urls
    logger.info(f"[RECHECK] Re-checking availability of {len(urls)} post(s)")

    loop = asyncio.get_event_loop()
    # check_availability is blocking (requests); fan out across the thread pool.
    results = await asyncio.gather(
        *(loop.run_in_executor(None, check_availability, url) for url in urls)
    )

    for r in results:
        logger.info(f"[RECHECK] {r.platform} {r.status.value} <- {r.url}")

    return RecheckResponse(
        results=[AvailabilityResponse(**r.to_dict()) for r in results]
    )
