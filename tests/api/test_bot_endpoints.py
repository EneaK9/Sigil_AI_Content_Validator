"""
API endpoint tests for bot detection.
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


# =============================================================================
# Single Check Endpoint Tests
# =============================================================================

class TestBotCheckEndpoint:
    """Tests for POST /api/v1/bot/check"""
    
    def test_requires_platform(self, client):
        """Check endpoint requires platform field."""
        response = client.post("/api/v1/bot/check", json={
            "account_data": {"username": "test"}
        })
        assert response.status_code == 422
    
    def test_requires_account_data(self, client):
        """Check endpoint requires account_data field."""
        response = client.post("/api/v1/bot/check", json={
            "platform": "x"
        })
        assert response.status_code == 422
    
    def test_invalid_platform_rejected(self, client):
        """Invalid platform is rejected."""
        response = client.post("/api/v1/bot/check", json={
            "platform": "myspace",
            "account_data": {"username": "test"}
        })
        assert response.status_code == 422
    
    def test_returns_verdict(self, client):
        """Check endpoint returns proper verdict response."""
        response = client.post("/api/v1/bot/check", json={
            "platform": "x",
            "username": "test_user",
            "account_data": {
                "followers_count": 1000,
                "following_count": 500,
                "tweet_count": 200,
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert "verdict" in data
        assert data["verdict"] in ["HUMAN", "SUSPICIOUS", "BOT", "UNKNOWN"]
        assert "score" in data
        assert "confidence" in data
        assert "signals" in data
    
    def test_detects_x_bot(self, client):
        """Detects obvious X bot."""
        response = client.post("/api/v1/bot/check", json={
            "platform": "x",
            "username": "user_839271",
            "account_data": {
                "created_at": "2026-05-01T00:00:00Z",  # Very recent
                "followers_count": 10,
                "following_count": 4950,  # Near ceiling
                "tweet_count": 2,  # Very few
                "description": "Crypto NFT telegram invest DM",  # Spam bio
                "default_profile_image": True,
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["verdict"] == "BOT"
    
    def test_recognizes_human_account(self, client):
        """Recognizes legitimate human account."""
        response = client.post("/api/v1/bot/check", json={
            "platform": "reddit",
            "username": "longtime_redditor",
            "account_data": {
                "created_utc": 1577836800,  # 2020-01-01
                "link_karma": 5000,
                "comment_karma": 15000,
                "has_verified_email": True,
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["verdict"] in ["HUMAN", "UNKNOWN"]
    
    def test_response_structure(self, client):
        """Response contains all required fields."""
        response = client.post("/api/v1/bot/check", json={
            "platform": "instagram",
            "account_data": {
                "username": "test_account",
                "follower_count": 500,
                "following_count": 200,
                "media_count": 50,
            }
        })
        assert response.status_code == 200
        data = response.json()
        
        # Check all required fields
        assert "verdict" in data
        assert "score" in data
        assert "confidence" in data
        assert "platform" in data
        assert "username" in data
        assert "signals" in data
        assert "triggered_count" in data
        assert "checked_at" in data
        
        # Check signal structure
        for signal in data["signals"]:
            assert "name" in signal
            assert "triggered" in signal
            assert "weight" in signal
            assert "evidence" in signal
    
    def test_supports_all_platforms(self, client):
        """All supported platforms work."""
        platforms = ["x", "reddit", "tiktok", "instagram", "facebook"]
        
        for platform in platforms:
            response = client.post("/api/v1/bot/check", json={
                "platform": platform,
                "account_data": {"username": f"test_{platform}"}
            })
            assert response.status_code == 200, f"Failed for platform: {platform}"
            assert response.json()["platform"] == platform


# =============================================================================
# Batch Check Endpoint Tests
# =============================================================================

class TestBotBatchEndpoint:
    """Tests for POST /api/v1/bot/check/batch"""
    
    def test_batch_creates_job(self, client):
        """Batch endpoint returns job ID."""
        response = client.post("/api/v1/bot/check/batch", json={
            "accounts": [
                {"platform": "x", "account_data": {"username": "user1"}},
                {"platform": "reddit", "account_data": {"username": "user2"}},
            ]
        })
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["total"] == 2
        assert data["status"] == "pending"
    
    def test_batch_rejects_empty_array(self, client):
        """Batch endpoint rejects empty accounts array."""
        response = client.post("/api/v1/bot/check/batch", json={
            "accounts": []
        })
        assert response.status_code == 422
    
    def test_batch_validates_accounts(self, client):
        """Batch endpoint validates each account."""
        response = client.post("/api/v1/bot/check/batch", json={
            "accounts": [
                {"platform": "x"},  # Missing account_data
            ]
        })
        assert response.status_code == 422
    
    def test_batch_handles_multiple_platforms(self, client):
        """Batch can process accounts from different platforms."""
        response = client.post("/api/v1/bot/check/batch", json={
            "accounts": [
                {"platform": "x", "account_data": {"username": "x_user", "tweet_count": 100}},
                {"platform": "reddit", "account_data": {"username": "reddit_user", "link_karma": 100}},
                {"platform": "instagram", "account_data": {"username": "ig_user", "media_count": 50}},
            ]
        })
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3


# =============================================================================
# Job Status Endpoint Tests
# =============================================================================

class TestBotJobEndpoint:
    """Tests for GET /api/v1/bot/jobs/{job_id}"""
    
    def test_nonexistent_job_returns_404(self, client):
        """Getting nonexistent job returns 404."""
        response = client.get("/api/v1/bot/jobs/nonexistent-id")
        assert response.status_code == 404
    
    def test_get_existing_job(self, client):
        """Can retrieve existing job status."""
        # First create a batch job
        create_response = client.post("/api/v1/bot/check/batch", json={
            "accounts": [
                {"platform": "x", "account_data": {"username": "test"}},
            ]
        })
        job_id = create_response.json()["job_id"]
        
        # Then get the job
        response = client.get(f"/api/v1/bot/jobs/{job_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["job_id"] == job_id
        assert "status" in data
        assert "progress" in data
        assert "results" in data
    
    def test_job_response_structure(self, client):
        """Job response has correct structure."""
        # Create a batch job
        create_response = client.post("/api/v1/bot/check/batch", json={
            "accounts": [
                {"platform": "x", "account_data": {"username": "test1"}},
                {"platform": "reddit", "account_data": {"username": "test2"}},
            ]
        })
        job_id = create_response.json()["job_id"]
        
        # Get job status
        response = client.get(f"/api/v1/bot/jobs/{job_id}")
        data = response.json()
        
        # Check structure
        assert "job_id" in data
        assert "status" in data
        assert "progress" in data
        assert "completed" in data["progress"]
        assert "total" in data["progress"]
        assert "failed" in data["progress"]
        assert "results" in data
        assert "errors" in data
        assert "created_at" in data


# =============================================================================
# Arbitrate Endpoint Tests
# =============================================================================

class TestBotArbitrateEndpoint:
    """Tests for POST /api/v1/bot/arbitrate"""
    
    def test_requires_all_fields(self, client):
        """Arbitrate endpoint requires all fields."""
        response = client.post("/api/v1/bot/arbitrate", json={
            "platform": "x",
            "username": "test",
            # Missing account_data and triggered_signals
        })
        assert response.status_code == 422
    
    @patch("anthropic.Anthropic")
    def test_returns_verdict(self, mock_anthropic_class, client):
        """Arbitrate endpoint returns Claude's verdict."""
        # Mock Claude response
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="BOT\nThis account shows clear signs of automation.")]
        mock_client.messages.create.return_value = mock_response
        
        response = client.post("/api/v1/bot/arbitrate", json={
            "platform": "x",
            "username": "suspicious_user",
            "account_data": {
                "followers_count": 100,
                "following_count": 4500,
                "tweet_count": 10,
            },
            "triggered_signals": [
                {"name": "low_follower_ratio", "triggered": True, "weight": 3, "evidence": "Bad ratio"},
                {"name": "following_gt_4900", "triggered": True, "weight": 3, "evidence": "Near ceiling"},
            ]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["verdict"] in ["BOT", "HUMAN", "UNCERTAIN"]
        assert "reasoning" in data
    
    @patch("api.routes.bot.os.environ.get")
    def test_handles_missing_api_key(self, mock_env_get, client):
        """Returns error when API key is missing."""
        mock_env_get.return_value = None
        
        response = client.post("/api/v1/bot/arbitrate", json={
            "platform": "x",
            "username": "test",
            "account_data": {"followers_count": 100},
            "triggered_signals": [
                {"name": "test", "triggered": True, "weight": 2, "evidence": "Test"}
            ]
        })
        
        assert response.status_code == 500
        assert "API_KEY" in response.json()["detail"]


# =============================================================================
# Platform-Specific Detection Tests
# =============================================================================

class TestPlatformSpecificDetection:
    """Test platform-specific bot patterns via API."""
    
    def test_x_immediate_bot_pattern(self, client):
        """X immediate bot pattern detected via API."""
        response = client.post("/api/v1/bot/check", json={
            "platform": "x",
            "account_data": {
                "username": "bot_account",
                "created_at": "2026-05-20T00:00:00Z",  # <30 days
                "tweet_count": 2,  # <5
                "following_count": 4950,  # >4900
                "followers_count": 5,
            }
        })
        assert response.status_code == 200
        assert response.json()["verdict"] == "BOT"
    
    def test_tiktok_zero_videos_high_followers(self, client):
        """TikTok zero videos + high followers = BOT."""
        response = client.post("/api/v1/bot/check", json={
            "platform": "tiktok",
            "account_data": {
                "username": "fake_influencer",
                "video_count": 0,
                "follower_count": 50000,
                "following_count": 100,
            }
        })
        assert response.status_code == 200
        assert response.json()["verdict"] == "BOT"
    
    def test_reddit_karma_farming(self, client):
        """Reddit karma farming pattern detected."""
        response = client.post("/api/v1/bot/check", json={
            "platform": "reddit",
            "account_data": {
                "username": "karma_farmer",
                "created_utc": 1717200000,  # Recent
                "subreddits_posted": ["freekarma4u", "pics"],
                "link_karma": 500,
                "comment_karma": 10,
            }
        })
        assert response.status_code == 200
        data = response.json()
        triggered_names = {s["name"] for s in data["signals"] if s["triggered"]}
        assert "karma_farm_subs" in triggered_names
    
    def test_instagram_engagement_farming(self, client):
        """Instagram low engagement pattern detected."""
        response = client.post("/api/v1/bot/check", json={
            "platform": "instagram",
            "account_data": {
                "username": "bought_followers",
                "follower_count": 100000,
                "following_count": 500,
                "media_count": 50,
                "avg_likes": 50,  # 0.05% engagement
                "avg_comments": 2,
            }
        })
        assert response.status_code == 200
        data = response.json()
        triggered_names = {s["name"] for s in data["signals"] if s["triggered"]}
        assert "low_engagement" in triggered_names


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Test error handling in bot endpoints."""
    
    def test_invalid_json(self, client):
        """Invalid JSON returns 422."""
        response = client.post(
            "/api/v1/bot/check",
            content="not json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
    
    def test_wrong_data_types(self, client):
        """Wrong data types return error."""
        response = client.post("/api/v1/bot/check", json={
            "platform": "x",
            "account_data": {
                "username": "test",
                "followers_count": "not a number",  # Should be int
            }
        })
        # Detector doesn't handle type conversion - returns 500
        assert response.status_code == 500
        assert "Bot detection failed" in response.json()["detail"]


# =============================================================================
# URL-Based Check Endpoint Tests
# =============================================================================

class TestBotCheckUrlEndpoint:
    """Tests for POST /api/v1/bot/check/url"""
    
    def test_requires_url(self, client):
        """Check URL endpoint requires url field."""
        response = client.post("/api/v1/bot/check/url", json={})
        assert response.status_code == 422
    
    @patch("api.routes.bot.scrape_profile")
    @patch("api.routes.bot.detect_platform_from_url")
    def test_returns_verdict_with_scraped_data(self, mock_detect, mock_scrape, client):
        """URL check returns verdict and scraped data."""
        mock_detect.return_value = "tiktok"
        mock_scrape.return_value = {
            "username": "test_user",
            "follower_count": 50000,
            "following_count": 200,
            "video_count": 100,
        }
        
        response = client.post("/api/v1/bot/check/url", json={
            "url": "https://www.tiktok.com/@test_user"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "verdict" in data
        assert "account_data" in data
        assert data["account_data"]["username"] == "test_user"
    
    @patch("api.routes.bot.detect_platform_from_url")
    def test_invalid_url_returns_400(self, mock_detect, client):
        """Invalid URL returns 400."""
        from core.models import ScrapingError
        mock_detect.side_effect = ScrapingError("Cannot detect platform")
        
        response = client.post("/api/v1/bot/check/url", json={
            "url": "https://invalid-site.com/user"
        })
        
        assert response.status_code == 400


class TestBotCheckUrlBatchEndpoint:
    """Tests for POST /api/v1/bot/check/url/batch"""
    
    def test_batch_url_creates_job(self, client):
        """Batch URL endpoint returns job ID."""
        response = client.post("/api/v1/bot/check/url/batch", json={
            "urls": [
                "https://www.tiktok.com/@user1",
                "https://x.com/user2",
            ]
        })
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["total"] == 2
        assert data["status"] == "pending"
    
    def test_batch_url_rejects_empty_array(self, client):
        """Batch URL endpoint rejects empty urls array."""
        response = client.post("/api/v1/bot/check/url/batch", json={
            "urls": []
        })
        assert response.status_code == 422
