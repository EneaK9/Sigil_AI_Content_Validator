"""
Edge case tests - unusual inputs and boundary conditions.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.models import PostData, Violation, Verdict
from core.detector import detect_platform


class TestURLEdgeCases:
    """Edge cases for URL handling."""

    def test_url_with_unicode(self):
        """Should handle URLs with unicode characters."""
        # Reddit allows unicode in subreddit names
        url = "https://reddit.com/r/日本語/comments/abc123/title"
        platform = detect_platform(url)
        assert platform == "reddit"

    def test_url_with_query_params(self):
        """Should handle URLs with query parameters."""
        url = "https://reddit.com/r/test/comments/abc123/title?utm_source=share&utm_medium=web2x"
        platform = detect_platform(url)
        assert platform == "reddit"

    def test_url_with_fragments(self):
        """Should handle URLs with fragments."""
        url = "https://reddit.com/r/test/comments/abc123/title#t=10"
        platform = detect_platform(url)
        assert platform == "reddit"

    def test_url_mixed_case(self):
        """Should handle mixed case URLs."""
        url = "HTTPS://WWW.REDDIT.COM/R/TEST/comments/ABC123/TITLE"
        platform = detect_platform(url)
        assert platform == "reddit"

    def test_very_long_url(self):
        """Should handle very long URLs."""
        url = "https://reddit.com/r/test/comments/" + "a" * 500 + "/title"
        platform = detect_platform(url)
        assert platform == "reddit"


class TestPostDataEdgeCases:
    """Edge cases for PostData."""

    def test_empty_text(self):
        """Should allow empty text (caller handles validation)."""
        post = PostData(
            url="http://test.com",
            platform="reddit",
            text="",  # Empty
            author="",
            title=""
        )
        assert post.text == ""

    def test_very_long_text(self):
        """Should handle very long text."""
        long_text = "a" * 100000  # 100K characters
        post = PostData(
            url="http://test.com",
            platform="reddit",
            text=long_text
        )
        assert len(post.text) == 100000

    def test_text_with_special_characters(self):
        """Should handle special characters."""
        special_text = "Test with émojis 🎉 and spëcial châràctérs αβγδ 日本語 🔥"
        post = PostData(
            url="http://test.com",
            platform="reddit",
            text=special_text
        )
        assert "🎉" in post.text
        assert "日本語" in post.text

    def test_text_with_newlines(self):
        """Should handle newlines and formatting."""
        text = "Line 1\n\nLine 2\n\n\n\nLine 3\r\nLine 4"
        post = PostData(
            url="http://test.com",
            platform="reddit",
            text=text
        )
        assert "\n" in post.text

    def test_text_with_html_entities(self):
        """Should handle HTML entities in text."""
        text = "Test &amp; more &lt;script&gt; stuff"
        post = PostData(
            url="http://test.com",
            platform="reddit",
            text=text
        )
        assert "&amp;" in post.text


class TestViolationEdgeCases:
    """Edge cases for Violation."""

    def test_empty_quote(self):
        """Should allow empty quote (edge case)."""
        violation = Violation(
            rule="Test",
            severity="LOW",
            explanation="Test explanation",
            policy_reference="Test ref",
            quote=""  # Empty quote
        )
        assert violation.quote == ""

    def test_very_long_explanation(self):
        """Should handle very long explanation."""
        violation = Violation(
            rule="Test",
            severity="HIGH",
            explanation="This is an explanation. " * 100,
            policy_reference="Test",
            quote="test"
        )
        assert len(violation.explanation) > 1000


class TestVerdictEdgeCases:
    """Edge cases for Verdict."""

    def test_empty_violations_list(self):
        """Should handle empty violations list."""
        verdict = Verdict(
            verdict="PASS",
            platform="reddit",
            post_url="http://test.com",
            post_text="test",
            violations=[],
            passed_checks=["All"],
            confidence=0.99,
            recommendation=""
        )
        assert len(verdict.violations) == 0

    def test_empty_passed_checks(self):
        """Should handle empty passed_checks list."""
        verdict = Verdict(
            verdict="FAIL",
            platform="reddit",
            post_url="http://test.com",
            post_text="test",
            violations=[Violation("R", "HIGH", "E", "P", "Q")],
            passed_checks=[],  # Empty
            confidence=0.8,
            recommendation="Fix it"
        )
        assert len(verdict.passed_checks) == 0

    def test_many_violations(self):
        """Should handle many violations."""
        violations = [
            Violation(f"Rule {i}", "LOW", f"Explanation {i}", f"Ref {i}", f"Quote {i}")
            for i in range(20)
        ]
        verdict = Verdict(
            verdict="FAIL",
            platform="reddit",
            post_url="http://test.com",
            post_text="test",
            violations=violations,
            passed_checks=[],
            confidence=0.5,
            recommendation="Major issues"
        )
        assert len(verdict.violations) == 20

    def test_confidence_boundary_zero(self):
        """Should accept confidence of exactly 0.0."""
        verdict = Verdict(
            verdict="FAIL",
            platform="reddit",
            post_url="http://test.com",
            post_text="test",
            violations=[],
            passed_checks=[],
            confidence=0.0,
            recommendation=""
        )
        assert verdict.confidence == 0.0

    def test_confidence_boundary_one(self):
        """Should accept confidence of exactly 1.0."""
        verdict = Verdict(
            verdict="PASS",
            platform="reddit",
            post_url="http://test.com",
            post_text="test",
            violations=[],
            passed_checks=[],
            confidence=1.0,
            recommendation=""
        )
        assert verdict.confidence == 1.0

    def test_to_json_special_characters(self):
        """JSON output should handle special characters."""
        verdict = Verdict(
            verdict="PASS",
            platform="reddit",
            post_url="http://test.com",
            post_text='Test with "quotes" and <brackets> and emoji 🔥',
            violations=[],
            passed_checks=["Test & More"],
            confidence=0.9,
            recommendation=""
        )
        json_str = verdict.to_json()
        # JSON may encode emoji as unicode escape (\ud83d\udd25) or literal - both valid
        assert "🔥" in json_str or "\\ud83d\\udd25" in json_str
        # Quotes should be escaped in JSON
        assert '\\"quotes\\"' in json_str


class TestInputSanitization:
    """Tests for handling potentially malicious input."""

    def test_text_with_json_injection(self):
        """Should handle text that looks like JSON."""
        text = '{"verdict": "PASS", "hacked": true}'
        post = PostData(
            url="http://test.com",
            platform="reddit",
            text=text
        )
        # Should store literally, not interpret
        assert '{"verdict"' in post.text

    def test_text_with_null_bytes(self):
        """Should handle text with null bytes."""
        text = "Test\x00null\x00bytes"
        post = PostData(
            url="http://test.com",
            platform="reddit",
            text=text
        )
        assert "\x00" in post.text

    def test_url_with_javascript(self):
        """Should reject URLs that don't match known patterns."""
        with pytest.raises(ValueError):
            detect_platform("javascript:alert('xss')")

    def test_url_with_data_scheme(self):
        """Should reject data: URLs."""
        with pytest.raises(ValueError):
            detect_platform("data:text/html,<script>alert(1)</script>")
