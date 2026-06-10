"""
Bot detection API endpoints.
"""
import logging
import time
import os
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks

from api.schemas.bot import (
    BotCheckRequest,
    BotCheckUrlRequest,
    BotCheckUrlBatchRequest,
    BotBatchRequest,
    BotCheckResponse,
    BotSignalResponse,
    BotBatchJobResponse,
    BotBatchResultResponse,
    BotArbitrateRequest,
    BotArbitrateResponse,
)
from api.schemas.responses import ErrorResponse
from api.dependencies import get_job_store
from core.bot_detector import detect_bot, BotVerdict
from core.profile_scraper import scrape_profile, detect_platform_from_url
from core.models import ScrapingError

logger = logging.getLogger("policyguard.api.bot")

router = APIRouter(prefix="/bot", tags=["Bot Detection"])


@router.post(
    "/check",
    response_model=BotCheckResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input"},
        500: {"model": ErrorResponse, "description": "Processing error"},
    },
    summary="Check single account for bot signals",
    description="Analyze a single social media account for bot behavior using signal stacking.",
)
async def check_single_account(request: BotCheckRequest) -> BotCheckResponse:
    """
    Analyze a single account for bot signals.
    
    - **platform**: Social media platform (x, reddit, tiktok, instagram, facebook)
    - **username**: Account username (optional, can be in account_data)
    - **account_data**: Dictionary of account metrics and activity data
    """
    start_time = time.time()
    platform = request.platform.lower()
    username = request.username or request.account_data.get("username", "unknown")
    
    logger.info(f"[BOT] Checking account: {username} on {platform}")
    
    try:
        # Inject username into account_data if not present
        account_data = request.account_data.copy()
        if "username" not in account_data:
            account_data["username"] = username
        
        # Run bot detection
        result = detect_bot(platform, account_data)
        
        elapsed = time.time() - start_time
        logger.info(f"[BOT] Result for {username}: {result.verdict.value} (score={result.score}, conf={result.confidence:.2f}) in {elapsed:.2f}s")
        
        # Convert to response model
        signals = [
            BotSignalResponse(
                name=s.name,
                triggered=s.triggered,
                weight=s.weight,
                evidence=s.evidence
            )
            for s in result.signals
        ]
        
        return BotCheckResponse(
            verdict=result.verdict.value,
            score=result.score,
            confidence=result.confidence,
            platform=result.platform,
            username=result.username,
            signals=signals,
            triggered_count=len([s for s in result.signals if s.triggered]),
            checked_at=result.checked_at,
        )
        
    except Exception as e:
        logger.error(f"[BOT] Error checking {username}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Bot detection failed: {e}")


@router.post(
    "/check/url",
    response_model=BotCheckResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid URL or unsupported platform"},
        500: {"model": ErrorResponse, "description": "Scraping or processing error"},
    },
    summary="Check account by profile URL",
    description="Scrape profile data from URL and analyze for bot signals.",
)
async def check_account_by_url(request: BotCheckUrlRequest) -> BotCheckResponse:
    """
    Scrape profile from URL and analyze for bot signals.
    
    Supported URL formats:
    - TikTok: https://www.tiktok.com/@username
    - X/Twitter: https://x.com/username or https://twitter.com/username
    - Reddit: https://www.reddit.com/user/username
    - Instagram: https://www.instagram.com/username
    - Facebook: https://www.facebook.com/username
    """
    start_time = time.time()
    url = request.url
    
    logger.info(f"[BOT URL] Checking profile: {url}")
    
    try:
        # Detect platform and scrape profile
        platform = detect_platform_from_url(url)
        account_data = scrape_profile(url)
        username = account_data.get("username", "unknown")
        
        logger.info(f"[BOT URL] Scraped {platform} profile: @{username}")
        
        # Run bot detection
        result = detect_bot(platform, account_data)
        
        elapsed = time.time() - start_time
        logger.info(f"[BOT URL] Result for {username}: {result.verdict.value} (score={result.score}) in {elapsed:.2f}s")
        
        # Convert to response model
        signals = [
            BotSignalResponse(
                name=s.name,
                triggered=s.triggered,
                weight=s.weight,
                evidence=s.evidence
            )
            for s in result.signals
        ]
        
        return BotCheckResponse(
            verdict=result.verdict.value,
            score=result.score,
            confidence=result.confidence,
            platform=result.platform,
            username=result.username,
            signals=signals,
            triggered_count=len([s for s in result.signals if s.triggered]),
            checked_at=result.checked_at,
            account_data=account_data,  # Include scraped data in response
        )
        
    except ScrapingError as e:
        logger.error(f"[BOT URL] Scraping error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[BOT URL] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Bot detection failed: {e}")


@router.post(
    "/check/url/batch",
    response_model=BotBatchJobResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input"},
    },
    summary="Check multiple profiles by URL (async)",
    description="Submit a batch of profile URLs for bot analysis. Returns job ID for polling.",
)
async def check_batch_urls(
    request: BotCheckUrlBatchRequest,
    background_tasks: BackgroundTasks,
) -> BotBatchJobResponse:
    """
    Submit a batch of profile URLs for asynchronous bot detection.
    
    - **urls**: Array of profile URLs to scrape and analyze
    
    Returns a job ID. Poll GET /api/v1/bot/jobs/{job_id} for results.
    """
    urls = request.urls
    
    if not urls:
        raise HTTPException(status_code=400, detail="No URLs provided")
    
    logger.info(f"[BOT URL BATCH] Received {len(urls)} URLs for batch checking")
    
    job_store = get_job_store()
    job_id = job_store.create_job(total=len(urls))
    
    logger.info(f"[BOT URL BATCH] Created job {job_id[:8]}...")
    
    # Schedule background processing
    background_tasks.add_task(
        _process_url_batch,
        urls,
        job_id,
    )
    
    return BotBatchJobResponse(
        job_id=job_id,
        total=len(urls),
        status="pending",
    )


async def _process_url_batch(urls: list, job_id: str) -> None:
    """Process a batch of URL bot checks in the background."""
    from api.dependencies import get_job_store
    
    job_store = get_job_store()
    job_store.set_status(job_id, "processing")
    short_id = job_id[:8]
    
    logger.info(f"[BOT URL JOB {short_id}] Starting batch processing of {len(urls)} URLs")
    
    for i, url in enumerate(urls):
        try:
            platform = detect_platform_from_url(url)
            account_data = scrape_profile(url)
            username = account_data.get("username", f"profile_{i}")
            
            result = detect_bot(platform, account_data)
            
            # Convert to dict for storage, include scraped data
            result_dict = result.to_dict()
            result_dict["account_data"] = account_data
            job_store.add_verdict(job_id, result_dict)
            
            if (i + 1) % 5 == 0:
                logger.info(f"[BOT URL JOB {short_id}] Progress: {i+1}/{len(urls)}")
                
        except Exception as e:
            logger.error(f"[BOT URL JOB {short_id}] Error on URL {i} ({url}): {e}")
            job_store.add_error(job_id, {
                "index": i,
                "url": url,
                "error": str(e),
            })
    
    job_store.set_status(job_id, "completed")
    logger.info(f"[BOT URL JOB {short_id}] Batch completed")


@router.post(
    "/check/batch",
    response_model=BotBatchJobResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input"},
    },
    summary="Check multiple accounts (async)",
    description="Submit a batch of accounts for bot analysis. Returns job ID for polling.",
)
async def check_batch_accounts(
    request: BotBatchRequest,
    background_tasks: BackgroundTasks,
) -> BotBatchJobResponse:
    """
    Submit a batch of accounts for asynchronous bot detection.
    
    - **accounts**: Array of account check requests
    
    Returns a job ID. Poll GET /api/v1/bot/jobs/{job_id} for results.
    """
    accounts = request.accounts
    
    if not accounts:
        raise HTTPException(status_code=400, detail="No accounts provided")
    
    logger.info(f"[BOT BATCH] Received {len(accounts)} accounts for batch checking")
    
    # Log platform distribution
    platforms = {}
    for acc in accounts:
        p = acc.platform.lower()
        platforms[p] = platforms.get(p, 0) + 1
    logger.info(f"[BOT BATCH] Platform distribution: {platforms}")
    
    job_store = get_job_store()
    job_id = job_store.create_job(total=len(accounts))
    
    logger.info(f"[BOT BATCH] Created job {job_id[:8]}...")
    
    # Schedule background processing
    background_tasks.add_task(
        _process_bot_batch,
        accounts,
        job_id,
    )
    
    return BotBatchJobResponse(
        job_id=job_id,
        total=len(accounts),
        status="pending",
    )


async def _process_bot_batch(accounts: list, job_id: str) -> None:
    """Process a batch of bot checks in the background."""
    from api.dependencies import get_job_store
    
    job_store = get_job_store()
    job_store.set_status(job_id, "processing")
    short_id = job_id[:8]
    
    logger.info(f"[BOT JOB {short_id}] Starting batch processing of {len(accounts)} accounts")
    
    for i, acc in enumerate(accounts):
        try:
            platform = acc.platform.lower()
            account_data = acc.account_data.copy()
            username = acc.username or account_data.get("username", f"account_{i}")
            account_data["username"] = username
            
            result = detect_bot(platform, account_data)
            
            # Convert to dict for storage
            result_dict = result.to_dict()
            job_store.add_verdict(job_id, result_dict)
            
            if (i + 1) % 10 == 0:
                logger.info(f"[BOT JOB {short_id}] Progress: {i+1}/{len(accounts)}")
                
        except Exception as e:
            logger.error(f"[BOT JOB {short_id}] Error on account {i}: {e}")
            job_store.add_error(job_id, {
                "index": i,
                "platform": acc.platform,
                "error": str(e),
            })
    
    job_store.set_status(job_id, "completed")
    logger.info(f"[BOT JOB {short_id}] Batch completed")


@router.get(
    "/jobs/{job_id}",
    response_model=BotBatchResultResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
    summary="Get bot batch job status",
    description="Poll this endpoint for batch bot check status and results.",
)
async def get_bot_job(job_id: str) -> BotBatchResultResponse:
    """Get status and results of a bot batch job."""
    logger.info(f"[BOT] Status request for job: {job_id[:8]}...")
    
    job_store = get_job_store()
    job = job_store.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    
    # Convert verdicts to response models
    results = []
    for v in job.verdicts:
        signals = [
            BotSignalResponse(**s) for s in v.get("signals", [])
        ]
        results.append(BotCheckResponse(
            verdict=v["verdict"],
            score=v["score"],
            confidence=v["confidence"],
            platform=v["platform"],
            username=v["username"],
            signals=signals,
            triggered_count=v["triggered_count"],
            checked_at=v["checked_at"],
        ))
    
    return BotBatchResultResponse(
        job_id=job.id,
        status=job.status,
        progress={
            "completed": job.completed,
            "total": job.total,
            "failed": job.failed,
        },
        results=results,
        errors=job.errors,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.post(
    "/arbitrate",
    response_model=BotArbitrateResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input"},
        500: {"model": ErrorResponse, "description": "API error"},
    },
    summary="Claude arbitration for SUSPICIOUS accounts",
    description="Use Claude AI to make a final verdict on ambiguous SUSPICIOUS accounts.",
)
async def arbitrate_account(request: BotArbitrateRequest) -> BotArbitrateResponse:
    """
    Use Claude to make a final call on a SUSPICIOUS account.
    
    Only use this for accounts that scored SUSPICIOUS - it adds API latency and cost.
    """
    platform = request.platform
    username = request.username
    
    logger.info(f"[BOT ARBITRATE] Requesting Claude verdict for {username} on {platform}")
    
    # Build the prompt
    signal_text = "\n".join(
        f"- {s.name}: {s.evidence}" 
        for s in request.triggered_signals
    )
    
    prompt = f"""You are analyzing a {platform} account for bot behavior.

Account data:
- Username: {username}
- Followers: {request.account_data.get('followers_count', 'unknown')}
- Following: {request.account_data.get('following_count', 'unknown')}
- Posts/Tweets: {request.account_data.get('tweet_count') or request.account_data.get('media_count') or request.account_data.get('video_count', 'unknown')}
- Account age: {request.account_data.get('age_days', 'unknown')} days
- Bio: {request.account_data.get('description') or request.account_data.get('bio', 'empty')}

Triggered bot signals:
{signal_text}

Based on these signals, is this account more likely to be:
1. A BOT or automated account
2. A real HUMAN account
3. UNCERTAIN — not enough information

Respond with exactly one word on the first line: BOT, HUMAN, or UNCERTAIN.
Then on the next line, explain your reasoning in one sentence."""

    try:
        import anthropic
        
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")
        
        client = anthropic.Anthropic(api_key=api_key)
        
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = response.content[0].text.strip()
        lines = response_text.split('\n', 1)
        
        verdict_word = lines[0].strip().upper()
        if verdict_word not in ["BOT", "HUMAN", "UNCERTAIN"]:
            verdict_word = "UNCERTAIN"
        
        reasoning = lines[1].strip() if len(lines) > 1 else "No explanation provided."
        
        logger.info(f"[BOT ARBITRATE] Claude verdict for {username}: {verdict_word}")
        
        return BotArbitrateResponse(
            verdict=verdict_word,
            reasoning=reasoning,
            platform=platform,
            username=username,
        )
        
    except anthropic.APIError as e:
        logger.error(f"[BOT ARBITRATE] Anthropic API error: {e}")
        raise HTTPException(status_code=500, detail=f"Claude API error: {e}")
    except Exception as e:
        logger.error(f"[BOT ARBITRATE] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Arbitration failed: {e}")
