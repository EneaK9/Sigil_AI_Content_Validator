"""
Shared pytest fixtures for PolicyGuard tests.
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import PostData, Violation, Verdict


# ============================================================================
# Environment Fixtures
# ============================================================================

@pytest.fixture
def mock_env(monkeypatch):
    """Set up mock environment variables."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")
    monkeypatch.setenv("X_BEARER_TOKEN", "test-bearer-token")


@pytest.fixture
def no_api_key(monkeypatch):
    """Remove API key from environment."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


# ============================================================================
# Sample Data Fixtures
# ============================================================================

@pytest.fixture
def sample_post_data():
    """Create a sample PostData object."""
    return PostData(
        url="https://reddit.com/r/test/comments/abc123/test_post",
        platform="reddit",
        text="This is a sample post for testing purposes.",
        author="u/testuser",
        title="Test Post Title",
        scraped_at=datetime.now(timezone.utc).isoformat()
    )


@pytest.fixture
def sample_violation():
    """Create a sample Violation object."""
    return Violation(
        rule="Violent Speech",
        severity="HIGH",
        explanation="The post contains threats of violence.",
        policy_reference="Reddit Content Policy - Rule 1",
        quote="the threatening phrase"
    )


@pytest.fixture
def sample_verdict_pass(sample_post_data):
    """Create a sample PASS verdict."""
    return Verdict(
        verdict="PASS",
        platform=sample_post_data.platform,
        post_url=sample_post_data.url,
        post_text=sample_post_data.text,
        violations=[],
        passed_checks=["Violence", "Hate Speech", "Spam"],
        confidence=0.95,
        recommendation="",
        checked_at=datetime.now(timezone.utc).isoformat()
    )


@pytest.fixture
def sample_verdict_fail(sample_post_data, sample_violation):
    """Create a sample FAIL verdict."""
    return Verdict(
        verdict="FAIL",
        platform=sample_post_data.platform,
        post_url=sample_post_data.url,
        post_text=sample_post_data.text,
        violations=[sample_violation],
        passed_checks=["Spam", "Privacy"],
        confidence=0.92,
        recommendation="Remove the threatening content.",
        checked_at=datetime.now(timezone.utc).isoformat()
    )


# ============================================================================
# Mock Response Fixtures
# ============================================================================

@pytest.fixture
def mock_reddit_response():
    """Mock Reddit JSON API response."""
    return [
        {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "Test Reddit Post",
                            "selftext": "This is the body of the Reddit post.",
                            "author": "testuser",
                            "subreddit": "test",
                            "created_utc": 1704067200
                        }
                    }
                ]
            }
        }
    ]


@pytest.fixture
def mock_reddit_link_post():
    """Mock Reddit JSON response for a link post (no selftext)."""
    return [
        {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "Check out this link",
                            "selftext": "",
                            "author": "linkposter",
                            "subreddit": "test"
                        }
                    }
                ]
            }
        }
    ]


@pytest.fixture
def mock_claude_pass_response():
    """Mock Claude API response for a passing post."""
    return {
        "verdict": "PASS",
        "violations": [],
        "passed_checks": [
            "harassment/bullying",
            "hate speech",
            "threats of violence",
            "spam",
            "privacy violations"
        ],
        "confidence": 0.95,
        "recommendation": ""
    }


@pytest.fixture
def mock_claude_fail_response():
    """Mock Claude API response for a failing post."""
    return {
        "verdict": "FAIL",
        "violations": [
            {
                "rule": "Threats of Violence",
                "severity": "HIGH",
                "explanation": "The post contains explicit threats of physical harm.",
                "policy_reference": "Reddit Content Policy - Violence",
                "quote": "I will hurt you"
            }
        ],
        "passed_checks": ["spam", "privacy"],
        "confidence": 0.98,
        "recommendation": "Remove the threatening content immediately."
    }


# ============================================================================
# Policy Fixtures
# ============================================================================

@pytest.fixture
def sample_policy_text():
    """Sample policy text for testing."""
    return """
=== Reddit Content Policy ===

# Reddit Rules

## Rule 1: Remember the human
Reddit is a place for creating community and belonging, not for attacking 
marginalized or vulnerable groups of people.

## Rule 2: Abide by community rules
Post authentic content into communities where you have a personal interest.

## Rule 3: Respect the privacy of others
Instigating harassment is not allowed. Do not post someone's personal information.

## Rule 4: Do not post or encourage the posting of sexual or suggestive content involving minors.

## Rule 5: You don't have to use your real name, but don't impersonate others.

## Rule 6: Ensure people have predictable experiences
Label content as NSFW when appropriate.

## Rule 7: Keep it legal
Don't post illegal content.

## Rule 8: Don't break the site
Don't interfere with normal use of Reddit.
"""


# ============================================================================
# URL Fixtures
# ============================================================================

@pytest.fixture
def valid_urls():
    """Dictionary of valid URLs for each platform."""
    return {
        "reddit": [
            "https://www.reddit.com/r/worldnews/comments/abc123/test_title",
            "https://reddit.com/r/test/comments/xyz789/another_post",
            "https://old.reddit.com/r/python/comments/def456/python_post",
            "https://redd.it/abc123",
        ],
        "x": [
            "https://x.com/elonmusk/status/1234567890123456789",
            "https://twitter.com/user/status/9876543210987654321",
            "https://www.x.com/test/status/1111111111111111111",
        ],
        "tiktok": [
            "https://www.tiktok.com/@user/video/1234567890123456789",
            "https://tiktok.com/@creator/video/9876543210987654321",
            "https://vm.tiktok.com/abc123/",
        ],
        "facebook": [
            "https://www.facebook.com/user/posts/123456789",
            "https://facebook.com/groups/test/posts/987654321",
            "https://fb.com/story/123",
            "https://fb.watch/abc123/",
        ],
        "instagram": [
            "https://www.instagram.com/p/ABC123xyz/",
            "https://instagram.com/reel/XYZ789abc/",
        ],
    }


@pytest.fixture
def invalid_urls():
    """List of URLs that should not match any platform."""
    return [
        "https://google.com",
        "https://example.com/post/123",
        "https://linkedin.com/posts/abc",
        "https://youtube.com/watch?v=abc123",
        "not-a-url",
        "",
        "http://",
    ]


# ============================================================================
# Test Case Fixtures for Judge Tests
# ============================================================================

@pytest.fixture
def posts_should_pass():
    """Posts that should clearly PASS policy checks."""
    return [
        {
            "platform": "reddit",
            "text": "I think the protests in Albania are a legitimate expression of democratic frustration.",
            "expected_verdict": "PASS",
            "description": "Legitimate political opinion"
        },
        {
            "platform": "reddit", 
            "text": "Here's my recipe for chocolate chip cookies: Mix flour, sugar, butter, and chocolate chips. Bake at 350F for 12 minutes.",
            "expected_verdict": "PASS",
            "description": "Innocuous cooking content"
        },
        {
            "platform": "reddit",
            "text": "I disagree with the government's economic policy. The inflation rate is too high and they should focus on reducing spending.",
            "expected_verdict": "PASS",
            "description": "Political criticism without personal attacks"
        },
        {
            "platform": "x",
            "text": "Just finished reading a great book about machine learning. Highly recommend it for anyone interested in AI!",
            "expected_verdict": "PASS",
            "description": "Book recommendation"
        },
        {
            "platform": "reddit",
            "text": "The sunset today was absolutely beautiful. Nature never fails to amaze me.",
            "expected_verdict": "PASS",
            "description": "Appreciation of nature"
        },
    ]


@pytest.fixture
def posts_should_fail_high():
    """Posts that should FAIL with HIGH severity violations."""
    return [
        {
            "platform": "reddit",
            "text": "These protesters deserve to get beaten. Someone should teach them a lesson with violence.",
            "expected_verdict": "FAIL",
            "expected_severity": "HIGH",
            "description": "Direct threat of violence"
        },
        {
            "platform": "reddit",
            "text": "I'm going to find where you live and hurt your family. You've been warned.",
            "expected_verdict": "FAIL",
            "expected_severity": "HIGH",
            "description": "Direct personal threat"
        },
        {
            "platform": "x",
            "text": "All [ethnic group] should be eliminated. They don't deserve to live.",
            "expected_verdict": "FAIL",
            "expected_severity": "HIGH",
            "description": "Genocidal hate speech"
        },
        {
            "platform": "reddit",
            "text": "Here's how to make a bomb at home: Step 1...",
            "expected_verdict": "FAIL",
            "expected_severity": "HIGH",
            "description": "Dangerous illegal content"
        },
    ]


@pytest.fixture
def posts_should_fail_medium():
    """Posts that should FAIL with MEDIUM severity violations."""
    return [
        {
            "platform": "reddit",
            "text": "All [ethnic group] people are criminals and should be deported.",
            "expected_verdict": "FAIL",
            "expected_severity": "MEDIUM",
            "description": "Hate speech against ethnic group"
        },
        {
            "platform": "reddit",
            "text": "This user is such an idiot. Everyone go to their profile and tell them how stupid they are.",
            "expected_verdict": "FAIL",
            "expected_severity": "MEDIUM",
            "description": "Harassment/brigading"
        },
        {
            "platform": "x",
            "text": "John Smith lives at 123 Main St, his phone is 555-1234. Go harass him.",
            "expected_verdict": "FAIL",
            "expected_severity": "MEDIUM",
            "description": "Doxxing"
        },
    ]


@pytest.fixture
def posts_borderline():
    """Borderline posts where confidence should be lower (<0.85)."""
    return [
        {
            "platform": "reddit",
            "text": "The police in Tirana are acting like fascists.",
            "description": "Political criticism with strong language",
            "max_confidence": 0.85
        },
        {
            "platform": "reddit",
            "text": "I hate Mondays so much. They should be illegal.",
            "description": "Hyperbolic statement, not actual hate",
            "max_confidence": 0.90
        },
        {
            "platform": "x",
            "text": "Politicians are all corrupt liars who should be thrown out.",
            "description": "Harsh political speech",
            "max_confidence": 0.85
        },
        {
            "platform": "reddit",
            "text": "This game is so bad, the developers should be ashamed. Total garbage.",
            "description": "Harsh criticism but not harassment",
            "max_confidence": 0.90
        },
    ]


# ============================================================================
# Helper Functions
# ============================================================================

def create_mock_anthropic_response(content: dict):
    """Create a mock Anthropic API response object."""
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = json.dumps(content)
    mock_response.content = [mock_content]
    return mock_response
