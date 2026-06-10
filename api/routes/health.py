"""
Health check endpoint.
"""
from datetime import datetime, timezone
from fastapi import APIRouter

from api.schemas.responses import HealthResponse
from config import API_VERSION

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns service health status. Use for load balancer health checks and Kubernetes probes.",
)
async def health_check() -> HealthResponse:
    """
    Check service health.
    
    Returns:
        Health status with version and timestamp.
    """
    return HealthResponse(
        status="healthy",
        version=API_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
