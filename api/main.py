"""
FastAPI application entry point.
"""
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from config import API_VERSION, API_HOST, API_PORT
from api.routes import api_router
from api.dependencies import init_services, shutdown_services

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("policyguard.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("=" * 60)
    logger.info("PolicyGuard API starting up...")
    logger.info(f"Version: {API_VERSION}")
    logger.info(f"Host: {API_HOST}:{API_PORT}")
    init_services()
    logger.info("Services initialized successfully")
    logger.info("API ready to accept requests")
    logger.info("=" * 60)
    yield
    # Shutdown
    logger.info("PolicyGuard API shutting down...")
    shutdown_services()
    logger.info("Services shut down successfully")


app = FastAPI(
    title="PolicyGuard API",
    description="""
**PolicyGuard** - Social media content policy compliance checker.

Analyze social media posts against platform-specific Community Guidelines 
and Terms of Service using Claude AI.

## Features

- **Single post analysis** - Synchronous analysis (~3-5 seconds)
- **Batch processing** - Async processing for large batches with job tracking
- **Multi-platform support** - Reddit, X/Twitter, TikTok, Facebook, Instagram
- **Image analysis** - Multimodal analysis with Claude's vision
- **Video transcription** - Automatic transcription via Whisper

## Endpoints

- `POST /api/v1/check` - Analyze a single post (sync)
- `POST /api/v1/check/batch` - Submit batch for async processing
- `GET /api/v1/jobs/{job_id}` - Poll for batch job status/results
- `GET /api/v1/health` - Health check
    """,
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware - allow all origins for public API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)


@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint redirects to docs."""
    return {
        "service": "PolicyGuard API",
        "version": API_VERSION,
        "docs": "/docs",
        "health": "/api/v1/health",
    }
