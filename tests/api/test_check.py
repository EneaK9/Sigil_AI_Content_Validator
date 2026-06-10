"""
Tests for check endpoints.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    """Create test client."""
    with TestClient(app) as c:
        yield c


class TestCheckSingleEndpoint:
    """Tests for POST /api/v1/check"""
    
    def test_check_requires_url(self, client):
        """Check endpoint requires url field."""
        response = client.post("/api/v1/check", json={"message": "test"})
        assert response.status_code == 422
    
    def test_check_requires_message(self, client):
        """Check endpoint requires message field."""
        response = client.post("/api/v1/check", json={"url": "https://facebook.com/post/1"})
        assert response.status_code == 422
    
    def test_check_rejects_invalid_url(self, client):
        """Check endpoint rejects URLs from unsupported platforms."""
        response = client.post("/api/v1/check", json={
            "url": "https://youtube.com/watch?v=abc",
            "message": "test"
        })
        assert response.status_code == 400
        assert "platform" in response.json()["detail"].lower()
    
    @patch("api.routes.check.get_checker")
    def test_check_returns_verdict(self, mock_get_checker, client):
        """Check endpoint returns verdict on success."""
        mock_checker = MagicMock()
        mock_checker.check_post.return_value = {
            "verdict": "PASS",
            "platform": "facebook",
            "post_url": "https://facebook.com/post/1",
            "post_text": "Hello world",
            "violations": [],
            "passed_checks": ["hate speech", "violence"],
            "confidence": 0.95,
            "recommendation": "",
            "checked_at": "2024-01-01T00:00:00+00:00"
        }
        mock_get_checker.return_value = mock_checker
        
        response = client.post("/api/v1/check", json={
            "url": "https://facebook.com/post/1",
            "message": "Hello world"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["verdict"] == "PASS"
        assert data["platform"] == "facebook"
    
    @patch("api.routes.check.get_checker")
    def test_check_handles_judgment_error(self, mock_get_checker, client):
        """Check endpoint handles JudgmentError gracefully."""
        from core.models import JudgmentError
        
        mock_checker = MagicMock()
        mock_checker.check_post.side_effect = JudgmentError("API error")
        mock_get_checker.return_value = mock_checker
        
        response = client.post("/api/v1/check", json={
            "url": "https://facebook.com/post/1",
            "message": "Hello world"
        })
        
        assert response.status_code == 500
        assert "Analysis failed" in response.json()["detail"]
    
    def test_check_accepts_optional_fields(self, client):
        """Check endpoint accepts optional fields without error."""
        with patch("api.routes.check.get_checker") as mock:
            mock_checker = MagicMock()
            mock_checker.check_post.return_value = {
                "verdict": "PASS",
                "platform": "facebook",
                "post_url": "https://facebook.com/post/1",
                "post_text": "Hello",
                "violations": [],
                "passed_checks": [],
                "confidence": 0.9,
                "recommendation": "",
                "checked_at": "2024-01-01T00:00:00+00:00"
            }
            mock.return_value = mock_checker
            
            response = client.post("/api/v1/check", json={
                "url": "https://facebook.com/post/1",
                "message": "Hello",
                "author.name": "Test User",
                "image.uri": "https://example.com/image.jpg",
                "video": "https://example.com/video.mp4",
                "video_transcript": "Hello everyone"
            })
            
            assert response.status_code == 200


class TestCheckBatchEndpoint:
    """Tests for POST /api/v1/check/batch"""
    
    def test_batch_requires_posts_array(self, client):
        """Batch endpoint requires posts array."""
        response = client.post("/api/v1/check/batch", json={})
        assert response.status_code == 422
    
    def test_batch_rejects_empty_array(self, client):
        """Batch endpoint rejects empty posts array."""
        response = client.post("/api/v1/check/batch", json={"posts": []})
        assert response.status_code == 422
    
    def test_batch_returns_job_id(self, client):
        """Batch endpoint returns job ID."""
        response = client.post("/api/v1/check/batch", json={
            "posts": [
                {"url": "https://facebook.com/post/1", "message": "First"},
                {"url": "https://facebook.com/post/2", "message": "Second"}
            ]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["total"] == 2
        assert data["status"] == "pending"
    
    def test_batch_validates_posts(self, client):
        """Batch endpoint validates each post in array."""
        response = client.post("/api/v1/check/batch", json={
            "posts": [
                {"url": "https://facebook.com/post/1"},  # Missing message
            ]
        })
        assert response.status_code == 422


class TestPlatformDetection:
    """Tests for platform detection from URLs."""
    
    @pytest.mark.parametrize("url,expected_platform", [
        ("https://www.facebook.com/post/123", "facebook"),
        ("https://facebook.com/post/123", "facebook"),
        ("https://www.instagram.com/p/abc123", "instagram"),
        ("https://instagram.com/reel/abc", "instagram"),
        ("https://www.reddit.com/r/test/comments/abc/title", "reddit"),
        ("https://x.com/user/status/123", "x"),
        ("https://twitter.com/user/status/123", "x"),
        ("https://www.tiktok.com/@user/video/123", "tiktok"),
    ])
    def test_platform_detection(self, client, url, expected_platform):
        """Test platform detection from various URL formats."""
        with patch("api.routes.check.get_checker") as mock:
            mock_checker = MagicMock()
            mock_checker.check_post.return_value = {
                "verdict": "PASS",
                "platform": expected_platform,
                "post_url": url,
                "post_text": "Test",
                "violations": [],
                "passed_checks": [],
                "confidence": 0.9,
                "recommendation": "",
                "checked_at": "2024-01-01T00:00:00+00:00"
            }
            mock.return_value = mock_checker
            
            response = client.post("/api/v1/check", json={
                "url": url,
                "message": "Test"
            })
            
            assert response.status_code == 200
            # Verify check_post was called with correct platform
            call_args = mock_checker.check_post.call_args
            post_data = call_args[0][0]
            assert post_data.platform == expected_platform
