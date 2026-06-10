"""
Job store for managing batch processing jobs.
In-memory implementation - can be swapped for Redis in production.
"""
import logging
import uuid
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("policyguard.services.jobstore")


@dataclass
class Job:
    """Represents a batch processing job."""
    id: str
    status: str  # pending, processing, completed, failed
    total: int
    completed: int = 0
    failed: int = 0
    verdicts: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "job_id": self.id,
            "status": self.status,
            "progress": {
                "completed": self.completed,
                "total": self.total,
                "failed": self.failed,
            },
            "verdicts": self.verdicts,
            "errors": self.errors,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class JobStore:
    """
    Thread-safe in-memory job storage.
    
    For production, replace with Redis-backed implementation.
    """
    
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        logger.info("JobStore initialized (in-memory)")
    
    def create_job(self, total: int) -> str:
        """
        Create a new job and return its ID.
        
        Args:
            total: Total number of posts to process
            
        Returns:
            Job ID (UUID)
        """
        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            status="pending",
            total=total,
        )
        with self._lock:
            self._jobs[job_id] = job
        logger.info(f"[STORE] Created job {job_id[:8]}... (total: {total})")
        return job_id
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """
        Get a job by ID.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job object or None if not found
        """
        with self._lock:
            return self._jobs.get(job_id)
    
    def set_status(self, job_id: str, status: str) -> None:
        """
        Update job status.
        
        Args:
            job_id: Job ID
            status: New status (pending, processing, completed, failed)
        """
        with self._lock:
            if job_id in self._jobs:
                old_status = self._jobs[job_id].status
                self._jobs[job_id].status = status
                if status in ("completed", "failed"):
                    self._jobs[job_id].completed_at = datetime.now(timezone.utc).isoformat()
                logger.info(f"[STORE] Job {job_id[:8]}... status: {old_status} -> {status}")
    
    def add_verdict(self, job_id: str, verdict: dict) -> None:
        """
        Add a verdict to a job's results.
        
        Args:
            job_id: Job ID
            verdict: Verdict dictionary
        """
        with self._lock:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                job.verdicts.append(verdict)
                job.completed += 1
    
    def add_error(self, job_id: str, error: dict) -> None:
        """
        Add an error to a job's error list.
        
        Args:
            job_id: Job ID
            error: Error dictionary with details
        """
        with self._lock:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                job.errors.append(error)
                job.failed += 1
                job.completed += 1
    
    def list_jobs(self) -> list[Job]:
        """Get all jobs."""
        with self._lock:
            return list(self._jobs.values())
    
    def delete_job(self, job_id: str) -> bool:
        """
        Delete a job.
        
        Args:
            job_id: Job ID
            
        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                logger.info(f"[STORE] Deleted job {job_id[:8]}...")
                return True
            return False
    
    def cleanup_old_jobs(self, max_age_hours: int = 24) -> int:
        """
        Remove jobs older than specified hours.
        
        Args:
            max_age_hours: Maximum age in hours
            
        Returns:
            Number of jobs removed
        """
        now = datetime.now(timezone.utc)
        to_delete = []
        
        with self._lock:
            for job_id, job in self._jobs.items():
                created = datetime.fromisoformat(job.created_at.replace('Z', '+00:00'))
                age_hours = (now - created).total_seconds() / 3600
                if age_hours > max_age_hours:
                    to_delete.append(job_id)
            
            for job_id in to_delete:
                del self._jobs[job_id]
        
        if to_delete:
            logger.info(f"[STORE] Cleaned up {len(to_delete)} old job(s)")
        
        return len(to_delete)
