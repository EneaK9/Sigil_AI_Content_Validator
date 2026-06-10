"""
Pydantic models for bot detection API endpoints.
"""
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, HttpUrl


class BotCheckRequest(BaseModel):
    """Request model for single account bot check (JSON data)."""
    platform: Literal["x", "twitter", "reddit", "tiktok", "instagram", "facebook"] = Field(
        ..., description="Social media platform"
    )
    username: Optional[str] = Field(None, description="Account username")
    account_data: Dict[str, Any] = Field(
        ..., description="Account data including metrics and activity"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "platform": "x",
                "username": "suspicious_user",
                "account_data": {
                    "created_at": "2024-01-01T00:00:00Z",
                    "followers_count": 50,
                    "following_count": 4950,
                    "tweet_count": 3,
                    "description": "DM for crypto tips!",
                    "default_profile_image": True
                }
            }
        }
    }


class BotCheckUrlRequest(BaseModel):
    """Request model for URL-based bot check (scrapes profile)."""
    url: str = Field(
        ..., description="Profile URL to scrape and analyze"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "url": "https://www.tiktok.com/@suspicious_user"
            },
            "examples": [
                {"url": "https://www.tiktok.com/@username"},
                {"url": "https://x.com/username"},
                {"url": "https://www.reddit.com/user/username"},
                {"url": "https://www.instagram.com/username"},
                {"url": "https://www.facebook.com/username"},
            ]
        }
    }


class BotCheckUrlBatchRequest(BaseModel):
    """Request model for batch URL-based bot check."""
    urls: List[str] = Field(
        ..., description="List of profile URLs to analyze", min_length=1
    )


class BotBatchRequest(BaseModel):
    """Request model for batch bot check."""
    accounts: List[BotCheckRequest] = Field(
        ..., description="List of accounts to check", min_length=1
    )


class BotSignalResponse(BaseModel):
    """Response model for a single bot signal."""
    name: str = Field(..., description="Signal identifier")
    triggered: bool = Field(..., description="Whether signal was triggered")
    weight: int = Field(..., description="Signal weight (1-5)")
    evidence: str = Field(..., description="Human-readable explanation")


class BotCheckResponse(BaseModel):
    """Response model for bot check result."""
    verdict: Literal["HUMAN", "SUSPICIOUS", "BOT", "UNKNOWN"] = Field(
        ..., description="Bot detection verdict"
    )
    score: int = Field(..., description="Total accumulated score")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level")
    platform: str = Field(..., description="Platform analyzed")
    username: str = Field(..., description="Account username")
    signals: List[BotSignalResponse] = Field(
        default_factory=list, description="All evaluated signals"
    )
    triggered_count: int = Field(..., description="Number of triggered signals")
    checked_at: str = Field(..., description="ISO 8601 timestamp")
    account_data: Optional[Dict[str, Any]] = Field(
        None, description="Scraped account data (only present for URL-based checks)"
    )


class BotBatchJobResponse(BaseModel):
    """Response when batch job is created."""
    job_id: str = Field(..., description="Unique job identifier")
    total: int = Field(..., description="Total accounts to check")
    status: Literal["pending"] = Field("pending", description="Initial status")


class BotBatchResultResponse(BaseModel):
    """Response for completed batch job."""
    job_id: str = Field(..., description="Job identifier")
    status: Literal["pending", "processing", "completed", "failed"] = Field(
        ..., description="Current status"
    )
    progress: Dict[str, int] = Field(..., description="Progress info")
    results: List[BotCheckResponse] = Field(
        default_factory=list, description="Bot check results"
    )
    errors: List[Dict[str, Any]] = Field(
        default_factory=list, description="Any errors"
    )
    created_at: str = Field(..., description="Job creation time")
    completed_at: Optional[str] = Field(None, description="Completion time")


class BotArbitrateRequest(BaseModel):
    """Request for Claude to arbitrate a SUSPICIOUS account."""
    platform: Literal["x", "twitter", "reddit", "tiktok", "instagram", "facebook"] = Field(
        ..., description="Social media platform"
    )
    username: str = Field(..., description="Account username")
    account_data: Dict[str, Any] = Field(
        ..., description="Account data"
    )
    triggered_signals: List[BotSignalResponse] = Field(
        ..., description="Signals that were triggered"
    )


class BotArbitrateResponse(BaseModel):
    """Response from Claude arbitration."""
    verdict: Literal["BOT", "HUMAN", "UNCERTAIN"] = Field(
        ..., description="Claude's verdict"
    )
    reasoning: str = Field(..., description="Explanation for the verdict")
    platform: str = Field(..., description="Platform analyzed")
    username: str = Field(..., description="Account username")
