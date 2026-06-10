"""
Job status and results endpoints.
"""
import logging
from fastapi import APIRouter, HTTPException

from api.schemas.responses import JobResponse, JobProgress, VerdictResponse, ErrorResponse
from api.dependencies import get_job_store

logger = logging.getLogger("policyguard.api.jobs")

router = APIRouter()


@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
    summary="Get job status and results",
    description="Poll this endpoint to check batch job status and retrieve results when completed.",
)
async def get_job(job_id: str) -> JobResponse:
    """
    Get the status and results of a batch processing job.
    
    - **job_id**: The job ID returned from POST /check/batch
    
    Returns current status, progress, and verdicts (when completed).
    """
    logger.info(f"[JOB] Status request for job: {job_id[:8]}...")
    
    job_store = get_job_store()
    job = job_store.get_job(job_id)
    
    if not job:
        logger.warning(f"[JOB] Job not found: {job_id}")
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    
    logger.info(f"[JOB] Job {job_id[:8]}... status: {job.status} ({job.completed}/{job.total}, {job.failed} failed)")
    
    # Convert verdicts to response models
    verdicts = [VerdictResponse(**v) for v in job.verdicts]
    
    return JobResponse(
        job_id=job.id,
        status=job.status,
        progress=JobProgress(
            completed=job.completed,
            total=job.total,
            failed=job.failed,
        ),
        verdicts=verdicts,
        errors=job.errors,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.delete(
    "/jobs/{job_id}",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
    summary="Delete a job",
    description="Delete a completed or failed job and its results.",
)
async def delete_job(job_id: str) -> dict:
    """
    Delete a job and its results.
    
    - **job_id**: The job ID to delete
    """
    logger.info(f"[JOB] Delete request for job: {job_id[:8]}...")
    
    job_store = get_job_store()
    
    if not job_store.delete_job(job_id):
        logger.warning(f"[JOB] Cannot delete - job not found: {job_id}")
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    
    logger.info(f"[JOB] Job {job_id[:8]}... deleted")
    
    return {"message": f"Job '{job_id}' deleted"}
