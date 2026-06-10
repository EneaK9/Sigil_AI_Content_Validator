"""
API route handlers.
"""
from fastapi import APIRouter

from api.routes.check import router as check_router
from api.routes.jobs import router as jobs_router
from api.routes.health import router as health_router
from api.routes.topics import router as topics_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(check_router, tags=["Check"])
api_router.include_router(jobs_router, tags=["Jobs"])
api_router.include_router(health_router, tags=["Health"])
api_router.include_router(topics_router, tags=["Topics"])

__all__ = ["api_router"]
