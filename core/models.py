"""
Data models and custom exceptions for PolicyGuard.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, TYPE_CHECKING
import json

if TYPE_CHECKING:
    from core.bot_detector import BotScore


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
    image_urls: list[str] = field(default_factory=list)
    video_urls: list[str] = field(default_factory=list)
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    bot_score: Optional["BotScore"] = None  # Bot detection result for the author

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


# Report-result monitoring
#
# Detection tells us a post violates policy. Monitoring tells us what happened to
# it afterwards. We can't read a platform's internal moderation decision, but we
# CAN re-visit the post and observe whether it's still reachable — which is the
# best available proxy for "the action taken on a reported post."

class AvailabilityStatus(str, Enum):
    """Observed reachability of a previously-seen post on re-crawl."""
    LIVE = "live"                      # still reachable (HTTP 200) -> no action taken (yet)
    REMOVED = "removed"                # 404/410 -> deleted or taken down
    ACCOUNT_BANNED = "account_banned"  # author's account suspended/banned -> taken down
    RESTRICTED = "restricted"          # 403 -> private, withheld, or quarantined
    UNKNOWN = "unknown"                # couldn't determine (network error, no API token, unsupported)


@dataclass
class AvailabilityResult:
    """Result of re-checking whether a post is still live.

    This is the raw signal the dashboard maps onto an evidence item's report
    status (removed / restricted / still_live). It does NOT re-run policy
    judgment — it only answers "is this post still up?".
    """
    url: str
    platform: str
    status: AvailabilityStatus
    http_status: Optional[int] = None   # the HTTP code we observed, when there was one
    detail: str = ""                    # human-readable note (e.g. "Tweet not found (404)")
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        """Returns a fully serializable dict for JSON output."""
        result = asdict(self)
        result["status"] = self.status.value
        return result
