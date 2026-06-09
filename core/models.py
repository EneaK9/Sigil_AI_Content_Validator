"""
Data models and custom exceptions for PolicyGuard.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json


# Custom Exceptions

class NotSupportedError(Exception):
    """Raised when a platform cannot be auto-scraped (e.g., Facebook, Instagram)."""
    pass


class PolicyNotFoundError(Exception):
    """Raised when policy cache files are missing."""
    pass


class ScrapingError(Exception):
    """Raised when HTTP errors occur during post fetching."""
    pass


class JudgmentError(Exception):
    """Raised when Claude API call or JSON parsing fails."""
    pass


# Data Models

@dataclass
class PostData:
    """Represents scraped content from a social media post."""
    url: str
    platform: str
    text: str
    author: str = ""
    title: str = ""
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        """Validate that platform is supported."""
        valid_platforms = ["reddit", "x", "tiktok", "facebook", "instagram"]
        if self.platform not in valid_platforms:
            raise ValueError(
                f"Invalid platform '{self.platform}'. "
                f"Supported platforms: {', '.join(valid_platforms)}"
            )


@dataclass
class Violation:
    """Represents a single policy violation found in a post."""
    rule: str
    severity: str
    explanation: str
    policy_reference: str
    quote: str

    def __post_init__(self) -> None:
        """Validate severity level."""
        valid_severities = ["HIGH", "MEDIUM", "LOW"]
        if self.severity not in valid_severities:
            raise ValueError(
                f"Invalid severity '{self.severity}'. "
                f"Must be one of: {', '.join(valid_severities)}"
            )


@dataclass
class Verdict:
    """Represents the complete judgment result for a post."""
    verdict: str
    platform: str
    post_url: str
    post_text: str
    violations: list[Violation]
    passed_checks: list[str]
    confidence: float
    recommendation: str
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        """Validate verdict value and confidence range."""
        if self.verdict not in ["PASS", "FAIL"]:
            raise ValueError(
                f"Invalid verdict '{self.verdict}'. Must be 'PASS' or 'FAIL'."
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"Confidence must be between 0.0 and 1.0, got {self.confidence}"
            )

    def to_dict(self) -> dict:
        """Returns a fully serializable dict for JSON output."""
        result = asdict(self)
        result["violations"] = [asdict(v) for v in self.violations]
        return result

    def to_json(self) -> str:
        """Returns pretty-printed JSON string."""
        return json.dumps(self.to_dict(), indent=2)
