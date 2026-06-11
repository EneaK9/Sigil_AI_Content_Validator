"""
Pydantic models for API response serialization.
"""
from typing import Optional, List, Literal
from datetime import datetime
from pydantic import BaseModel, Field


class ViolationResponse(BaseModel):
    """A single policy violation found in a post."""
    rule: str = Field(..., description="Exact rule name from the platform's policies")
    severity: Literal["HIGH", "MEDIUM", "LOW"] = Field(..., description="Severity level")
    explanation: str = Field(..., description="Why this violates the policy")
    policy_reference: str = Field(..., description="Specific policy section reference")
    quote: str = Field(..., description="Text/description that triggered the violation")


class WarningResponse(BaseModel):
    """A possible violation or risk flag found in a post."""
    category: str = Field(..., description="Type of issue (racism, sexism, antisemitism, microaggression, etc.)")
    risk_level: Literal["OBVIOUS", "INTERPRETIVE", "DEEP_READ"] = Field(..., description="How obvious the issue is")
    explanation: str = Field(..., description="What's wrong with this — detailed explanation")
    problematic_element: str = Field(..., description="Exact phrase or element that's problematic")
    affected_groups: List[str] = Field(default_factory=list, description="Who could be harmed or offended")
    why_it_matters: str = Field("", description="Educational context — why this matters even if subtle")


class VerdictResponse(BaseModel):
    """Complete judgment result for a post."""
    verdict: Literal["PASS", "POSSIBLE_VIOLATION", "CLEAR_VIOLATION"] = Field(..., description="PASS if clean, POSSIBLE_VIOLATION if flagged, CLEAR_VIOLATION if violated")
    platform: str = Field(..., description="Platform the post was analyzed against")
    post_url: str = Field(..., description="Original URL or 'manual-input'")
    post_text: str = Field(..., description="Full text that was analyzed")
    violations: List[ViolationResponse] = Field(default_factory=list, description="List of clear violations")
    warnings: List[WarningResponse] = Field(default_factory=list, description="List of possible violations/flags")
    passed_checks: List[str] = Field(default_factory=list, description="Policy categories that passed")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0.0-1.0")
    recommendation: str = Field("", description="Suggested fix (empty if PASS)")
    checked_at: str = Field(..., description="ISO 8601 timestamp of analysis")
    report_message: str = Field("", description="Pre-formatted message for reporting to platform (empty if PASS)")


class JobProgress(BaseModel):
    """Progress information for a batch job."""
    completed: int = Field(..., description="Number of posts processed")
    total: int = Field(..., description="Total number of posts")
    failed: int = Field(0, description="Number of posts that failed")


class JobCreatedResponse(BaseModel):
    """Response when a batch job is created."""
    job_id: str = Field(..., description="Unique job identifier")
    total: int = Field(..., description="Total number of posts to process")
    status: Literal["pending"] = Field("pending", description="Initial job status")


class JobResponse(BaseModel):
    """Full job status and results."""
    job_id: str = Field(..., description="Unique job identifier")
    status: Literal["pending", "processing", "completed", "failed"] = Field(..., description="Current status")
    progress: JobProgress = Field(..., description="Processing progress")
    verdicts: List[VerdictResponse] = Field(default_factory=list, description="Results (populated when completed)")
    errors: List[dict] = Field(default_factory=list, description="Any errors that occurred")
    created_at: str = Field(..., description="ISO 8601 timestamp of job creation")
    completed_at: Optional[str] = Field(None, description="ISO 8601 timestamp of completion")


class HealthResponse(BaseModel):
    """Health check response."""
    status: Literal["healthy", "unhealthy"] = Field(..., description="Service health status")
    version: str = Field(..., description="API version")
    timestamp: str = Field(..., description="Current server time")


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[dict] = Field(None, description="Additional error details")
