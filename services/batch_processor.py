"""
Batch processor for efficient parallel post analysis.
Uses asyncio semaphore to limit concurrent Claude API calls.
"""
import asyncio
import logging
import time
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from core.models import PostData
from core.detector import detect_platform
from services.checker import CheckerService
from services.job_store import JobStore

logger = logging.getLogger("policyguard.services.batch")


class BatchProcessor:
    """
    Processes batches of posts in parallel with rate limiting.
    """
    
    def __init__(
        self, 
        checker: CheckerService, 
        job_store: JobStore,
        max_concurrent: int = 10
    ):
        """
        Initialize batch processor.
        
        Args:
            checker: CheckerService instance for post analysis
            job_store: JobStore instance for job state management
            max_concurrent: Maximum concurrent Claude API calls
        """
        self.checker = checker
        self.job_store = job_store
        self.max_concurrent = max_concurrent
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent)
        logger.info(f"BatchProcessor initialized with max_concurrent={max_concurrent}")
    
    def _convert_input_to_post_data(self, post_input: dict) -> tuple[PostData, Optional[str]]:
        """
        Convert API input dict to PostData and extract transcript.
        
        Args:
            post_input: Dictionary with post data
            
        Returns:
            Tuple of (PostData, video_transcript)
        """
        url = post_input["url"]
        platform = detect_platform(url)
        
        image_urls = []
        if post_input.get("image_uri"):
            image_urls.append(post_input["image_uri"])
        
        video_urls = []
        if post_input.get("video"):
            video_urls.append(post_input["video"])
        
        post = PostData(
            url=url,
            platform=platform,
            text=post_input["message"],
            author=post_input.get("author_name") or "",
            title="",
            image_urls=image_urls,
            video_urls=video_urls,
        )
        
        video_transcript = post_input.get("video_transcript")
        if video_transcript and not video_transcript.strip():
            video_transcript = None
        
        return post, video_transcript
    
    def _process_single(
        self, 
        post_input: dict, 
        index: int
    ) -> tuple[int, Optional[dict], Optional[dict]]:
        """
        Process a single post synchronously.
        
        Args:
            post_input: Post input dictionary
            index: Post index in batch
            
        Returns:
            Tuple of (index, verdict_or_none, error_or_none)
        """
        try:
            post, transcript = self._convert_input_to_post_data(post_input)
            verdict = self.checker.check_post(post, transcript)
            return (index, verdict, None)
        except Exception as e:
            error = {
                "index": index,
                "url": post_input.get("url", "unknown"),
                "error": str(e),
            }
            return (index, None, error)
    
    async def process_batch(
        self, 
        posts: list[dict], 
        job_id: str
    ) -> None:
        """
        Process a batch of posts asynchronously with parallel execution.
        
        Args:
            posts: List of post input dictionaries
            job_id: Job ID for progress tracking
        """
        start_time = time.time()
        short_id = job_id[:8]
        total_posts = len(posts)
        
        logger.info(f"[JOB {short_id}] ========== BATCH PROCESSING STARTED ==========")
        logger.info(f"[JOB {short_id}] Total posts: {total_posts}")
        logger.info(f"[JOB {short_id}] Max concurrent workers: {self.max_concurrent}")
        
        self.job_store.set_status(job_id, "processing")
        
        # Pre-warm policy cache by detecting all platforms
        platforms = set()
        for post in posts:
            try:
                platform = detect_platform(post["url"])
                platforms.add(platform)
            except ValueError:
                pass
        
        logger.info(f"[JOB {short_id}] Detected platforms: {', '.join(sorted(platforms))}")
        logger.info(f"[JOB {short_id}] Pre-loading policies for {len(platforms)} platform(s)...")
        
        cache_start = time.time()
        self.checker.warm_cache(platforms)
        cache_elapsed = time.time() - cache_start
        logger.info(f"[JOB {short_id}] Policy cache warmed in {cache_elapsed:.2f}s")
        
        # Process posts in parallel with semaphore
        semaphore = asyncio.Semaphore(self.max_concurrent)
        loop = asyncio.get_event_loop()
        
        completed_count = 0
        passed_count = 0
        failed_count = 0
        error_count = 0
        last_log_time = time.time()
        log_interval = 5  # Log progress every 5 seconds
        
        async def process_with_semaphore(post_input: dict, index: int):
            async with semaphore:
                result = await loop.run_in_executor(
                    self._executor,
                    self._process_single,
                    post_input,
                    index
                )
                return result
        
        # Create all tasks
        logger.info(f"[JOB {short_id}] Starting parallel processing...")
        tasks = [
            process_with_semaphore(post, i) 
            for i, post in enumerate(posts)
        ]
        
        # Process and update progress as results come in
        for coro in asyncio.as_completed(tasks):
            index, verdict, error = await coro
            completed_count += 1
            
            if verdict:
                self.job_store.add_verdict(job_id, verdict)
                if verdict.get("verdict") == "PASS":
                    passed_count += 1
                else:
                    failed_count += 1
            elif error:
                self.job_store.add_error(job_id, error)
                error_count += 1
                logger.warning(f"[JOB {short_id}] Post {index} failed: {error.get('error', 'unknown')[:50]}...")
            
            # Log progress periodically
            current_time = time.time()
            if current_time - last_log_time >= log_interval or completed_count == total_posts:
                progress_pct = (completed_count / total_posts) * 100
                elapsed = current_time - start_time
                rate = completed_count / elapsed if elapsed > 0 else 0
                eta = (total_posts - completed_count) / rate if rate > 0 else 0
                
                logger.info(
                    f"[JOB {short_id}] Progress: {completed_count}/{total_posts} ({progress_pct:.1f}%) | "
                    f"PASS: {passed_count} | FAIL: {failed_count} | ERROR: {error_count} | "
                    f"Rate: {rate:.1f}/s | ETA: {eta:.0f}s"
                )
                last_log_time = current_time
        
        # Mark job as completed
        job = self.job_store.get_job(job_id)
        total_elapsed = time.time() - start_time
        
        if job and job.failed == job.total:
            self.job_store.set_status(job_id, "failed")
            logger.error(f"[JOB {short_id}] ========== BATCH FAILED ==========")
            logger.error(f"[JOB {short_id}] All {total_posts} posts failed")
        else:
            self.job_store.set_status(job_id, "completed")
            logger.info(f"[JOB {short_id}] ========== BATCH COMPLETED ==========")
        
        logger.info(f"[JOB {short_id}] Final results:")
        logger.info(f"[JOB {short_id}]   - Total processed: {completed_count}")
        logger.info(f"[JOB {short_id}]   - PASS verdicts: {passed_count}")
        logger.info(f"[JOB {short_id}]   - FAIL verdicts: {failed_count}")
        logger.info(f"[JOB {short_id}]   - Errors: {error_count}")
        logger.info(f"[JOB {short_id}]   - Total time: {total_elapsed:.2f}s")
        logger.info(f"[JOB {short_id}]   - Avg time/post: {total_elapsed/total_posts:.2f}s")
    
    def shutdown(self) -> None:
        """Shutdown the thread pool executor."""
        self._executor.shutdown(wait=True)
