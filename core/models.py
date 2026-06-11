"""
Data models and custom exceptions for PolicyGuard.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
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
class Warning:
    """Represents a possible violation or risk flag found in a post."""
    category: str              # Type of issue: racism, sexism, antisemitism, microaggression, etc.
    risk_level: str            # How obvious: "OBVIOUS" | "INTERPRETIVE" | "DEEP_READ"
    explanation: str           # What's wrong with this — be detailed
    problematic_element: str   # Exact phrase, image description, or element flagged
    affected_groups: list[str] = field(default_factory=list)  # Who could be harmed or offended
    why_it_matters: str = ""   # Educational context — why this matters even if subtle

    def __post_init__(self) -> None:
        """Validate risk level."""
        valid_risk_levels = ["OBVIOUS", "INTERPRETIVE", "DEEP_READ"]
        if self.risk_level not in valid_risk_levels:
            raise ValueError(
                f"Invalid risk_level '{self.risk_level}'. "
                f"Must be one of: {', '.join(valid_risk_levels)}"
            )


@dataclass
class Verdict:
    """Represents the complete judgment result for a post."""
    verdict: str
    platform: str
    post_url: str
    post_text: str
    violations: list[Violation]
    warnings: list[Warning]
    passed_checks: list[str]
    confidence: float
    recommendation: str
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        """Validate verdict value and confidence range."""
        valid_verdicts = ["PASS", "POSSIBLE_VIOLATION", "CLEAR_VIOLATION"]
        if self.verdict not in valid_verdicts:
            raise ValueError(
                f"Invalid verdict '{self.verdict}'. Must be one of: {', '.join(valid_verdicts)}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"Confidence must be between 0.0 and 1.0, got {self.confidence}"
            )

    def to_dict(self) -> dict:
        """Returns a fully serializable dict for JSON output."""
        result = asdict(self)
        result["violations"] = [asdict(v) for v in self.violations]
        result["warnings"] = [asdict(w) for w in self.warnings]
        result["report_message"] = self.generate_report_message()
        return result

    def to_json(self) -> str:
        """Returns pretty-printed JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    def _get_platform_display_name(self) -> str:
        """Get display name for platform."""
        names = {
            "reddit": "Reddit",
            "x": "X (Twitter)",
            "tiktok": "TikTok",
            "facebook": "Facebook",
            "instagram": "Instagram"
        }
        return names.get(self.platform, self.platform.title())

    def generate_report_message(self) -> str:
        """
        Generate a formal report message for submission to the platform.
        
        Returns:
            Formatted report message string ready to send to platform moderation.
        """
        platform_name = self._get_platform_display_name()
        confidence_pct = int(self.confidence * 100)
        
        if self.verdict == "PASS":
            return ""
        
        if self.verdict == "CLEAR_VIOLATION":
            return self._generate_violation_report(platform_name, confidence_pct)
        else:  # POSSIBLE_VIOLATION
            return self._generate_warning_report(platform_name, confidence_pct)

    def _generate_violation_report(self, platform_name: str, confidence_pct: int) -> str:
        """Generate report for clear violations."""
        lines = [
            f"Subject: Content Violation Report - {platform_name} Community Guidelines",
            "",
            f"To: {platform_name} Trust & Safety Team",
            "",
            f"I am reporting a violation of {platform_name}'s Community Guidelines.",
            "",
            "POST DETAILS:",
            f"- URL: {self.post_url}",
            f"- Date Analyzed: {self.checked_at}",
            "",
            "VIOLATION SUMMARY:",
            f"This content violates your platform's policies with {confidence_pct}% confidence.",
            "",
            "SPECIFIC VIOLATIONS:",
            ""
        ]
        
        for i, v in enumerate(self.violations, 1):
            lines.extend([
                f"{i}. {v.rule} (Severity: {v.severity})",
                f"   Policy Reference: {v.policy_reference}",
                "",
                f'   Problematic Content: "{v.quote}"',
                "",
                f"   Explanation: {v.explanation}",
                ""
            ])
        
        if self.warnings:
            lines.extend([
                "ADDITIONAL CONCERNS:",
                ""
            ])
            for w in self.warnings:
                affected = ", ".join(w.affected_groups) if w.affected_groups else "various communities"
                lines.extend([
                    f"- {w.category} ({w.risk_level})",
                    f'  Element: "{w.problematic_element}"',
                    f"  Impact: {w.explanation}",
                    f"  Affected Communities: {affected}",
                    ""
                ])
        
        if self.recommendation:
            lines.extend([
                "RECOMMENDATION:",
                self.recommendation,
                ""
            ])
        
        lines.extend([
            "This report was generated by automated content analysis. Please review and take appropriate action under your platform's enforcement policies.",
            "",
            "Regards,",
            "Sigil AI Content Validator"
        ])
        
        return "\n".join(lines)

    def _generate_warning_report(self, platform_name: str, confidence_pct: int) -> str:
        """Generate report for possible violations (warnings only)."""
        lines = [
            f"Subject: Content Review Request - Potential Policy Concern on {platform_name}",
            "",
            f"To: {platform_name} Trust & Safety Team",
            "",
            "I am flagging content for your review that may approach your Community Guidelines thresholds.",
            "",
            "POST DETAILS:",
            f"- URL: {self.post_url}",
            f"- Date Analyzed: {self.checked_at}",
            "",
            "ASSESSMENT:",
            f"This content does not clearly violate your stated policies, but contains elements that warrant review. Confidence: {confidence_pct}%.",
            "",
            "IDENTIFIED CONCERNS:",
            ""
        ]
        
        for i, w in enumerate(self.warnings, 1):
            affected = ", ".join(w.affected_groups) if w.affected_groups else "various communities"
            lines.extend([
                f"{i}. {w.category}",
                f"   Risk Level: {w.risk_level}",
                "",
                f'   Problematic Element: "{w.problematic_element}"',
                "",
                f"   Analysis: {w.explanation}",
                "",
                f"   Potentially Affected Groups: {affected}",
                ""
            ])
            if w.why_it_matters:
                lines.extend([
                    f"   Why This Matters: {w.why_it_matters}",
                    ""
                ])
        
        lines.extend([
            "---",
            "",
            "CONTEXT:",
            "While this content may not meet the threshold for removal under current policies, we believe it contributes to a hostile environment for the communities identified above. We request your team review whether:",
            "",
            "1. The content crosses policy lines under closer examination",
            "2. The account shows a pattern of similar borderline content",
            "3. Updated policy guidance should address this type of content",
            "",
            "This report is submitted in good faith to support platform safety.",
            "",
            "Regards,",
            "Sigil AI Content Validator"
        ])
        
        return "\n".join(lines)
