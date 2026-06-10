"""
Pydantic schemas for API request/response validation.
"""
from api.schemas.requests import PostInput, BatchInput
from api.schemas.responses import (
    VerdictResponse,
    ViolationResponse,
    JobResponse,
    JobProgress,
    HealthResponse,
    ErrorResponse,
)
from api.schemas.bot import (
    BotCheckRequest,
    BotCheckUrlRequest,
    BotCheckUrlBatchRequest,
    BotBatchRequest,
    BotSignalResponse,
    BotCheckResponse,
    BotBatchJobResponse,
    BotBatchResultResponse,
    BotArbitrateRequest,
    BotArbitrateResponse,
)

__all__ = [
    # Content check schemas
    "PostInput",
    "BatchInput",
    "VerdictResponse",
    "ViolationResponse",
    "JobResponse",
    "JobProgress",
    "HealthResponse",
    "ErrorResponse",
    # Bot detection schemas
    "BotCheckRequest",
    "BotCheckUrlRequest",
    "BotCheckUrlBatchRequest",
    "BotBatchRequest",
    "BotSignalResponse",
    "BotCheckResponse",
    "BotBatchJobResponse",
    "BotBatchResultResponse",
    "BotArbitrateRequest",
    "BotArbitrateResponse",
]
