"""
Integration tests for full end-to-end flow with mocked external calls.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.models import PostData, Verdict
from core.detector import detect_platform
from core.judge import judge, build_user_prompt, build_verdict
from tests.conftest import create_mock_anthropic_response


class TestFullFlowMocked:
    """End-to-end tests with mocked external services."""

    @patch("core.judge.anthropic.Anthropic")
    def test_full_flow_pass_verdict(self, mock_anthropic_class, sample_policy_text, mock_env):
        """Full flow should work for a passing post."""
        # Setup mock
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        
        mock_response = create_mock_anthropic_response({
            "verdict": "PASS",
            "violations": [],
            "passed_checks": ["Violence", "Hate Speech", "Spam"],
            "confidence": 0.95,
            "recommendation": ""
        })
        mock_client.messages.create.return_value = mock_response
        
        # Create post
        post = PostData(
            url="https://reddit.com/r/test/comments/abc/title",
            platform="reddit",
            text="I love programming in Python!",
            author="u/coder",
            title="Python is great"
        )
        
        # Run judge
        verdict = judge(post, sample_policy_text)
        
        # Verify
        assert verdict.verdict == "PASS"
        assert len(verdict.violations) == 0
        assert verdict.confidence == 0.95

    @patch("core.judge.anthropic.Anthropic")
    def test_full_flow_fail_verdict(self, mock_anthropic_class, sample_policy_text, mock_env):
        """Full flow should work for a failing post."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        
        mock_response = create_mock_anthropic_response({
            "verdict": "FAIL",
            "violations": [
                {
                    "rule": "Violence",
                    "severity": "HIGH",
                    "explanation": "Contains threat",
                    "policy_reference": "Rule 1",
                    "quote": "threatening phrase"
                }
            ],
            "passed_checks": ["Spam"],
            "confidence": 0.92,
            "recommendation": "Remove threat"
        })
        mock_client.messages.create.return_value = mock_response
        
        post = PostData(
            url="https://reddit.com/r/test/comments/abc/title",
            platform="reddit",
            text="I will hurt you",
            author="u/baduser",
            title="Warning"
        )
        
        verdict = judge(post, sample_policy_text)
        
        assert verdict.verdict == "FAIL"
        assert len(verdict.violations) == 1
        assert verdict.violations[0].severity == "HIGH"
        assert verdict.recommendation == "Remove threat"

    @patch("core.judge.anthropic.Anthropic")
    def test_full_flow_multiple_violations(self, mock_anthropic_class, sample_policy_text, mock_env):
        """Should handle posts with multiple violations."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        
        mock_response = create_mock_anthropic_response({
            "verdict": "FAIL",
            "violations": [
                {
                    "rule": "Violence",
                    "severity": "HIGH",
                    "explanation": "Threat of violence",
                    "policy_reference": "Rule 1",
                    "quote": "threat"
                },
                {
                    "rule": "Hate Speech",
                    "severity": "MEDIUM",
                    "explanation": "Discriminatory language",
                    "policy_reference": "Rule 2",
                    "quote": "slur"
                }
            ],
            "passed_checks": ["Spam"],
            "confidence": 0.88,
            "recommendation": "Remove all violating content"
        })
        mock_client.messages.create.return_value = mock_response
        
        post = PostData(
            url="https://reddit.com/r/test/comments/abc/title",
            platform="reddit",
            text="Multiple violations here",
            author="u/baduser",
            title="Bad post"
        )
        
        verdict = judge(post, sample_policy_text)
        
        assert verdict.verdict == "FAIL"
        assert len(verdict.violations) == 2
        assert verdict.violations[0].severity == "HIGH"
        assert verdict.violations[1].severity == "MEDIUM"


class TestBuildUserPrompt:
    """Tests for prompt building."""

    def test_prompt_contains_post_data(self, sample_post_data, sample_policy_text):
        """Prompt should include all post information."""
        prompt = build_user_prompt(sample_post_data, sample_policy_text)
        
        assert sample_post_data.platform.upper() in prompt or sample_post_data.platform in prompt
        assert sample_post_data.url in prompt
        assert sample_post_data.text in prompt
        assert sample_post_data.author in prompt

    def test_prompt_contains_policies(self, sample_post_data, sample_policy_text):
        """Prompt should include policy text."""
        prompt = build_user_prompt(sample_post_data, sample_policy_text)
        
        assert "PLATFORM POLICIES" in prompt
        assert "Reddit" in prompt or "reddit" in prompt.lower()

    def test_prompt_requests_json_structure(self, sample_post_data, sample_policy_text):
        """Prompt should specify expected JSON structure."""
        prompt = build_user_prompt(sample_post_data, sample_policy_text)
        
        assert "verdict" in prompt
        assert "violations" in prompt
        assert "confidence" in prompt


class TestBuildVerdict:
    """Tests for verdict building from Claude response."""

    def test_build_verdict_pass(self, sample_post_data):
        """Should build PASS verdict correctly."""
        data = {
            "verdict": "PASS",
            "violations": [],
            "passed_checks": ["All checks"],
            "confidence": 0.99,
            "recommendation": ""
        }
        
        verdict = build_verdict(sample_post_data, data)
        
        assert verdict.verdict == "PASS"
        assert verdict.platform == "reddit"
        assert len(verdict.violations) == 0

    def test_build_verdict_fail(self, sample_post_data):
        """Should build FAIL verdict correctly."""
        data = {
            "verdict": "FAIL",
            "violations": [
                {
                    "rule": "Test Rule",
                    "severity": "LOW",
                    "explanation": "Test",
                    "policy_reference": "Ref",
                    "quote": "quote"
                }
            ],
            "passed_checks": [],
            "confidence": 0.7,
            "recommendation": "Fix it"
        }
        
        verdict = build_verdict(sample_post_data, data)
        
        assert verdict.verdict == "FAIL"
        assert len(verdict.violations) == 1
        assert verdict.violations[0].rule == "Test Rule"

    def test_build_verdict_missing_fields_raises(self, sample_post_data):
        """Should raise error for missing required fields."""
        from core.models import JudgmentError
        
        data = {"verdict": "PASS"}  # Missing other fields
        
        with pytest.raises(JudgmentError) as exc_info:
            build_verdict(sample_post_data, data)
        
        assert "missing required fields" in str(exc_info.value).lower()


class TestDetectorIntegration:
    """Integration tests for platform detection."""

    @pytest.mark.parametrize("url,expected_platform", [
        ("https://www.reddit.com/r/worldnews/comments/abc123/title", "reddit"),
        ("https://x.com/user/status/123456789", "x"),
        ("https://twitter.com/user/status/987654321", "x"),
        ("https://tiktok.com/@user/video/111222333", "tiktok"),
        ("https://facebook.com/user/posts/444555", "facebook"),
        ("https://instagram.com/p/ABC123/", "instagram"),
    ])
    def test_detect_all_platforms(self, url, expected_platform):
        """Should detect all supported platforms."""
        assert detect_platform(url) == expected_platform
