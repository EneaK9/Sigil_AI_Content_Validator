"""Unit tests for sigil.validation.models - data models and exceptions."""
import json

import pytest

from sigil.validation.models import (
    JudgmentError,
    NotSupportedError,
    PolicyNotFoundError,
    PostData,
    ScrapingError,
    Verdict,
    Violation,
    Warning,
)


def _verdict(**overrides):
    base = dict(
        verdict="PASS",
        platform="reddit",
        post_url="http://test.com",
        post_text="text",
        violations=[],
        warnings=[],
        passed_checks=[],
        confidence=0.9,
        recommendation="",
    )
    base.update(overrides)
    return Verdict(**base)


class TestPostData:
    def test_create_valid(self):
        post = PostData(
            url="https://reddit.com/r/test/comments/123/title",
            platform="reddit",
            text="Test post content",
            author="u/testuser",
            title="Test Title",
        )
        assert post.platform == "reddit"
        assert post.scraped_at is not None

    @pytest.mark.parametrize(
        "platform", ["reddit", "x", "tiktok", "facebook", "instagram", "linkedin"]
    )
    def test_valid_platforms(self, platform):
        post = PostData(url="http://test.com", platform=platform, text="t")
        assert post.platform == platform

    @pytest.mark.parametrize("platform", ["youtube", "twitter", "invalid", "", "Reddit"])
    def test_invalid_platforms(self, platform):
        with pytest.raises(ValueError, match="Invalid platform"):
            PostData(url="http://test.com", platform=platform, text="t")


class TestViolation:
    @pytest.mark.parametrize("severity", ["HIGH", "MEDIUM", "LOW"])
    def test_valid_severities(self, severity):
        v = Violation("r", severity, "e", "p", "q")
        assert v.severity == severity

    @pytest.mark.parametrize("severity", ["high", "CRITICAL", ""])
    def test_invalid_severities(self, severity):
        with pytest.raises(ValueError, match="Invalid severity"):
            Violation("r", severity, "e", "p", "q")


class TestWarning:
    def test_valid(self):
        w = Warning(
            category="racism",
            risk_level="OBVIOUS",
            explanation="e",
            problematic_element="x",
        )
        assert w.risk_level == "OBVIOUS"
        assert w.severity == "LOW"

    @pytest.mark.parametrize("risk", ["obvious", "MAYBE", ""])
    def test_invalid_risk_level(self, risk):
        with pytest.raises(ValueError, match="Invalid risk_level"):
            Warning(category="c", risk_level=risk, explanation="e", problematic_element="x")


class TestVerdict:
    @pytest.mark.parametrize(
        "value", ["PASS", "POSSIBLE_VIOLATION", "CLEAR_VIOLATION"]
    )
    def test_valid_verdicts(self, value):
        assert _verdict(verdict=value).verdict == value

    @pytest.mark.parametrize("value", ["pass", "FAIL", "UNKNOWN", ""])
    def test_invalid_verdicts(self, value):
        with pytest.raises(ValueError, match="Invalid verdict"):
            _verdict(verdict=value)

    @pytest.mark.parametrize("confidence", [-0.1, 1.1, 2.0])
    def test_invalid_confidence(self, confidence):
        with pytest.raises(ValueError, match="Confidence must be between"):
            _verdict(confidence=confidence)

    @pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
    def test_valid_confidence(self, confidence):
        assert _verdict(confidence=confidence).confidence == confidence

    def test_to_dict_includes_report_message(self):
        v = _verdict(
            verdict="CLEAR_VIOLATION",
            violations=[Violation("Violence", "HIGH", "threat", "Rule 1", "kill")],
        )
        result = v.to_dict()
        assert result["verdict"] == "CLEAR_VIOLATION"
        assert result["violations"][0]["rule"] == "Violence"
        assert "report_message" in result

    def test_to_json_roundtrip(self):
        parsed = json.loads(_verdict(platform="x").to_json())
        assert parsed["platform"] == "x"

    def test_pass_has_empty_report_message(self):
        assert _verdict(verdict="PASS").generate_report_message() == ""


class TestCustomExceptions:
    @pytest.mark.parametrize(
        "exc", [NotSupportedError, PolicyNotFoundError, ScrapingError, JudgmentError]
    )
    def test_exceptions_carry_message(self, exc):
        with pytest.raises(exc, match="boom"):
            raise exc("boom")
