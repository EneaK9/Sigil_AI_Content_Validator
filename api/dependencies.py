"""
Shared dependencies and application state.
Provides singleton instances of services for dependency injection.
"""
from typing import Optional

from services.checker import CheckerService
from services.job_store import JobStore
from services.batch_processor import BatchProcessor
from config import MAX_CONCURRENT_CHECKS


# Singleton instances (initialized on startup)
_checker: Optional[CheckerService] = None
_job_store: Optional[JobStore] = None
_batch_processor: Optional[BatchProcessor] = None


def init_services() -> None:
    """Initialize all service instances. Called on app startup."""
    global _checker, _job_store, _batch_processor
    
    _checker = CheckerService()
    _job_store = JobStore()
    _batch_processor = BatchProcessor(
        checker=_checker,
        job_store=_job_store,
        max_concurrent=MAX_CONCURRENT_CHECKS,
    )


def shutdown_services() -> None:
    """Cleanup services. Called on app shutdown."""
    global _batch_processor
    
    if _batch_processor:
        _batch_processor.shutdown()


def get_checker() -> CheckerService:
    """Get the checker service instance."""
    if _checker is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _checker


def get_job_store() -> JobStore:
    """Get the job store instance."""
    if _job_store is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _job_store


def get_batch_processor() -> BatchProcessor:
    """Get the batch processor instance."""
    if _batch_processor is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _batch_processor
