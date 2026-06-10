"""
Check endpoints for single and batch post analysis.
"""
import asyncio
import logging
import time
from typing import Optional, Tuple
from fastapi import APIRouter, HTTPException, BackgroundTasks

from api.schemas.requests import PostInput, BatchInput
from api.schemas.responses import VerdictResponse, JobCreatedResponse, ErrorResponse
from api.dependencies import get_checker, get_job_store, get_batch_processor
from core.models import PostData, PolicyNotFoundError, JudgmentError
from core.detector import detect_platform

logger = logging.getLogger("policyguard.api.check")

router = APIRouter()


def convert_post_input_to_data(post_input: PostInput) -> Tuple[PostData, Optional[str]]:
    """Convert Pydantic model to PostData and extract transcript."""
    url = post_input.url
    
    try:
        platform = detect_platform(url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    image_urls = []
    if post_input.image_uri:
        image_urls.append(post_input.image_uri)
    
    video_urls = []
    if post_input.video:
        video_urls.append(post_input.video)
    
    post = PostData(
        url=url,
        platform=platform,
        text=post_input.message,
        author=post_input.author_name or "",
        title="",
        image_urls=image_urls,
        video_urls=video_urls,
    )
    
    transcript = post_input.video_transcript
    if transcript and not transcript.strip():
        transcript = None
    
    return post, transcript


@router.post(
    "/check",
    response_model=VerdictResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input"},
        500: {"model": ErrorResponse, "description": "Processing error"},
    },
    summary="Analyze a single post",
    description="Analyze a single social media post against platform policies. Returns verdict synchronously (~3-5 seconds).",
)
async def check_single_post(post_input: PostInput) -> VerdictResponse:
    """
    Analyze a single post for policy violations.
    
    - **url**: Post URL (used for platform detection)
    - **message**: Post text content
    - **image.uri**: Optional image URL
    - **video**: Optional video URL
    - **video_transcript**: Optional pre-transcribed audio
    """
    start_time = time.time()
    logger.info(f"[CHECK] Received single post check request")
    logger.info(f"[CHECK] URL: {post_input.url}")
    logger.info(f"[CHECK] Message length: {len(post_input.message)} chars")
    
    if post_input.image_uri:
        logger.info(f"[CHECK] Image attached: {post_input.image_uri[:50]}...")
    if post_input.video:
        logger.info(f"[CHECK] Video attached: {post_input.video[:50]}...")
    if post_input.video_transcript:
        logger.info(f"[CHECK] Video transcript provided: {len(post_input.video_transcript)} chars")
    
    try:
        post, transcript = convert_post_input_to_data(post_input)
        logger.info(f"[CHECK] Platform detected: {post.platform}")
    except HTTPException:
        logger.warning(f"[CHECK] Invalid input - platform detection failed")
        raise
    except ValueError as e:
        logger.warning(f"[CHECK] Invalid input: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    checker = get_checker()
    
    try:
        logger.info(f"[CHECK] Starting Claude analysis for {post.platform}...")
        # Run synchronous judge in thread pool to not block
        loop = asyncio.get_event_loop()
        verdict = await loop.run_in_executor(
            None, 
            checker.check_post, 
            post, 
            transcript
        )
        
        elapsed = time.time() - start_time
        logger.info(f"[CHECK] Analysis complete: {verdict['verdict']} (confidence: {verdict['confidence']:.2f})")
        if verdict['violations']:
            logger.info(f"[CHECK] Violations found: {len(verdict['violations'])}")
            for v in verdict['violations']:
                logger.info(f"[CHECK]   - {v['rule']} ({v['severity']})")
        else:
            logger.info(f"[CHECK] No violations found")
        logger.info(f"[CHECK] Request completed in {elapsed:.2f}s")
        
        return VerdictResponse(**verdict)
    except PolicyNotFoundError as e:
        logger.error(f"[CHECK] Policy not found: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Policy not found: {e}. Run 'python policyguard.py refresh' to initialize policies."
        )
    except JudgmentError as e:
        logger.error(f"[CHECK] Analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")
    except Exception as e:
        logger.error(f"[CHECK] Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@router.post(
    "/check/batch",
    response_model=JobCreatedResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input"},
    },
    summary="Analyze multiple posts (async)",
    description="Submit a batch of posts for analysis. Returns immediately with a job ID. Poll /jobs/{job_id} for results.",
)
async def check_batch(
    batch_input: BatchInput,
    background_tasks: BackgroundTasks,
) -> JobCreatedResponse:
    """
    Submit a batch of posts for asynchronous processing.
    
    - **posts**: Array of post objects to analyze
    
    Returns a job ID immediately. Poll GET /api/v1/jobs/{job_id} for status and results.
    """
    posts = batch_input.posts
    
    if not posts:
        logger.warning("[BATCH] Empty batch request received")
        raise HTTPException(status_code=400, detail="No posts provided")
    
    logger.info(f"[BATCH] Received batch request with {len(posts)} posts")
    
    # Convert Pydantic models to dicts for batch processor
    posts_dicts = []
    platforms_detected = {}
    for i, post in enumerate(posts):
        post_dict = {
            "url": post.url,
            "message": post.message,
            "author_name": post.author_name,
            "image_uri": post.image_uri,
            "video": post.video,
            "video_transcript": post.video_transcript,
        }
        posts_dicts.append(post_dict)
        
        # Track platforms for logging
        try:
            platform = detect_platform(post.url)
            platforms_detected[platform] = platforms_detected.get(platform, 0) + 1
        except ValueError:
            platforms_detected["unknown"] = platforms_detected.get("unknown", 0) + 1
    
    # Log platform distribution
    logger.info(f"[BATCH] Platform distribution:")
    for platform, count in sorted(platforms_detected.items()):
        logger.info(f"[BATCH]   - {platform}: {count} posts")
    
    job_store = get_job_store()
    batch_processor = get_batch_processor()
    
    # Create job
    job_id = job_store.create_job(total=len(posts_dicts))
    logger.info(f"[BATCH] Created job: {job_id}")
    logger.info(f"[BATCH] Starting background processing...")
    
    # Schedule background processing
    background_tasks.add_task(
        batch_processor.process_batch,
        posts_dicts,
        job_id,
    )
    
    logger.info(f"[BATCH] Job {job_id[:8]}... queued for processing")
    
    return JobCreatedResponse(
        job_id=job_id,
        total=len(posts_dicts),
        status="pending",
    )
