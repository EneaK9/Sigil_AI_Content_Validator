"""
Unit tests for core/models.py - Data models and exceptions.
"""
import json
import pytest
from datetime import datetime, timezone

from core.models import (
    PostData, Violation, Verdict,
    NotSupportedError, PolicyNotFoundError, ScrapingError, JudgmentError
)


class TestPostData:
    """Tests for PostData dataclass."""

    def test_create_valid_post_data(self):
        """Should create PostData with valid inputs."""
        post = PostData(
            url="https://reddit.com/r/test/comments/123/title",
            platform="reddit",
            text="Test post content",
            author="u/testuser",
            title="Test Title"
        )
        assert post.url == "https://reddit.com/r/test/comments/123/title"
        assert post.platform == "reddit"
        assert post.text == "Test post content"
        assert post.author == "u/testuser"
        assert post.title == "Test Title"
        assert post.scraped_at is not None

    def test_create_minimal_post_data(self):
        """Should create PostData with minimal required fields."""
        post = PostData(
            url="https://x.com/user/status/123",
            platform="x",
            text="Tweet content"
        )
        assert post.author == ""
        assert post.title == ""

    @pytest.mark.parametrize("platform", ["reddit", "x", "tiktok", "facebook", "instagram"])
    def test_valid_platforms(self, platform):
        """Should accept all valid platforms."""
        post = PostData(url="http://test.com", platform=platform, text="test")
        assert post.platform == platform

    @pytest.mark.parametrize("platform", ["youtube", "linkedin", "invalid", "", "Reddit"])
    def test_invalid_platforms(self, platform):
        """Should reject invalid platforms."""
        with pytest.raises(ValueError) as exc_info:
            PostData(url="http://test.com", platform=platform, text="test")
        assert "Invalid platform" in str(exc_info.value)

    def test_scraped_at_auto_generated(self):
        """Should auto-generate scraped_at timestamp."""
        post = PostData(url="http://test.com", platform="reddit", text="test")
        # Should be a valid ISO timestamp
        parsed = datetime.fromisoformat(post.scraped_at.replace("Z", "+00:00"))
        assert parsed is not None


class TestViolation:
    """Tests for Violation dataclass."""

    def test_create_valid_violation(self):
        """Should create Violation with valid inputs."""
        violation = Violation(
            rule="Hate Speech",
            severity="HIGH",
            explanation="Contains hateful content targeting a group.",
            policy_reference="Community Guidelines - Section 3",
            quote="the offensive phrase"
        )
        assert violation.rule == "Hate Speech"
        assert violation.severity == "HIGH"
        assert violation.explanation == "Contains hateful content targeting a group."

    @pytest.mark.parametrize("severity", ["HIGH", "MEDIUM", "LOW"])
    def test_valid_severities(self, severity):
        """Should accept valid severity levels."""
        violation = Violation(
            rule="Test",
            severity=severity,
            explanation="Test",
            policy_reference="Test",
            quote="test"
        )
        assert violation.severity == severity

    @pytest.mark.parametrize("severity", ["high", "CRITICAL", "WARNING", "", "1"])
    def test_invalid_severities(self, severity):
        """Should reject invalid severity levels."""
        with pytest.raises(ValueError) as exc_info:
            Violation(
                rule="Test",
                severity=severity,
                explanation="Test",
                policy_reference="Test",
                quote="test"
            )
        assert "Invalid severity" in str(exc_info.value)


class TestVerdict:
    """Tests for Verdict dataclass."""

    def test_create_pass_verdict(self):
        """Should create a PASS verdict."""
        verdict = Verdict(
            verdict="PASS",
            platform="reddit",
            post_url="http://test.com",
            post_text="Safe content",
            violations=[],
            passed_checks=["Violence", "Hate Speech", "Spam"],
            confidence=0.95,
            recommendation=""
        )
        assert verdict.verdict == "PASS"
        assert len(verdict.violations) == 0
        assert verdict.confidence == 0.95

    def test_create_fail_verdict(self):
        """Should create a FAIL verdict with violations."""
        violation = Violation(
            rule="Violence",
            severity="HIGH",
            explanation="Threatens harm",
            policy_reference="Rule 1",
            quote="violent phrase"
        )
        verdict = Verdict(
            verdict="FAIL",
            platform="reddit",
            post_url="http://test.com",
            post_text="Violent content",
            violations=[violation],
            passed_checks=["Spam"],
            confidence=0.92,
            recommendation="Remove violent content"
        )
        assert verdict.verdict == "FAIL"
        assert len(verdict.violations) == 1
        assert verdict.violations[0].severity == "HIGH"

    @pytest.mark.parametrize("verdict_value", ["pass", "fail", "UNKNOWN", "", "YES"])
    def test_invalid_verdict_values(self, verdict_value):
        """Should reject invalid verdict values."""
        with pytest.raises(ValueError) as exc_info:
            Verdict(
                verdict=verdict_value,
                platform="reddit",
                post_url="http://test.com",
                post_text="test",
                violations=[],
                passed_checks=[],
                confidence=0.5,
                recommendation=""
            )
        assert "Invalid verdict" in str(exc_info.value)

    @pytest.mark.parametrize("confidence", [-0.1, 1.1, 2.0, -1])
    def test_invalid_confidence_values(self, confidence):
        """Should reject confidence outside 0-1 range."""
        with pytest.raises(ValueError) as exc_info:
            Verdict(
                verdict="PASS",
                platform="reddit",
                post_url="http://test.com",
                post_text="test",
                violations=[],
                passed_checks=[],
                confidence=confidence,
                recommendation=""
            )
        assert "Confidence must be between" in str(exc_info.value)

    @pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0, 0.95, 0.01])
    def test_valid_confidence_values(self, confidence):
        """Should accept confidence in 0-1 range."""
        verdict = Verdict(
            verdict="PASS",
            platform="reddit",
            post_url="http://test.com",
            post_text="test",
            violations=[],
            passed_checks=[],
            confidence=confidence,
            recommendation=""
        )
        assert verdict.confidence == confidence

    def test_to_dict(self):
        """Should convert to dictionary correctly."""
        violation = Violation(
            rule="Test",
            severity="LOW",
            explanation="Test explanation",
            policy_reference="Rule 1",
            quote="test"
        )
        verdict = Verdict(
            verdict="FAIL",
            platform="reddit",
            post_url="http://test.com",
            post_text="test text",
            violations=[violation],
            passed_checks=["Spam"],
            confidence=0.8,
            recommendation="Fix it"
        )
        
        result = verdict.to_dict()
        
        assert isinstance(result, dict)
        assert result["verdict"] == "FAIL"
        assert result["platform"] == "reddit"
        assert len(result["violations"]) == 1
        assert result["violations"][0]["rule"] == "Test"
        assert result["confidence"] == 0.8

    def test_to_json(self):
        """Should convert to JSON string correctly."""
        verdict = Verdict(
            verdict="PASS",
            platform="x",
            post_url="http://test.com",
            post_text="test",
            violations=[],
            passed_checks=["All"],
            confidence=0.99,
            recommendation=""
        )
        
        json_str = verdict.to_json()
        
        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["verdict"] == "PASS"
        assert parsed["platform"] == "x"


class TestCustomExceptions:
    """Tests for custom exception classes."""

    def test_not_supported_error(self):
        """NotSupportedError should work as expected."""
        with pytest.raises(NotSupportedError) as exc_info:
            raise NotSupportedError("Facebook not supported")
        assert "Facebook not supported" in str(exc_info.value)

    def test_policy_not_found_error(self):
        """PolicyNotFoundError should work as expected."""
        with pytest.raises(PolicyNotFoundError) as exc_info:
            raise PolicyNotFoundError("Policy file missing")
        assert "Policy file missing" in str(exc_info.value)

    def test_scraping_error(self):
        """ScrapingError should work as expected."""
        with pytest.raises(ScrapingError) as exc_info:
            raise ScrapingError("HTTP 404 - Not Found")
        assert "404" in str(exc_info.value)

    def test_judgment_error(self):
        """JudgmentError should work as expected."""
        with pytest.raises(JudgmentError) as exc_info:
            raise JudgmentError("Claude returned invalid JSON")
        assert "invalid JSON" in str(exc_info.value)
