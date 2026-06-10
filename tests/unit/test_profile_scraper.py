"""
Unit tests for profile scraping module.
"""
import pytest
from unittest.mock import patch, MagicMock

from core.profile_scraper import (
    detect_platform_from_url,
    scrape_profile,
    _extract_username_from_url,
    _parse_count,
    scrape_tiktok_profile,
    scrape_x_profile,
    scrape_reddit_profile,
    scrape_instagram_profile,
    scrape_facebook_profile,
)
from core.models import ScrapingError


class TestDetectPlatformFromUrl:
    """Tests for platform detection from URL."""
    
    def test_detect_tiktok(self):
        assert detect_platform_from_url("https://www.tiktok.com/@username") == "tiktok"
        assert detect_platform_from_url("https://tiktok.com/@user") == "tiktok"
    
    def test_detect_x(self):
        assert detect_platform_from_url("https://x.com/username") == "x"
        assert detect_platform_from_url("https://twitter.com/username") == "x"
    
    def test_detect_reddit(self):
        assert detect_platform_from_url("https://www.reddit.com/user/username") == "reddit"
        assert detect_platform_from_url("https://reddit.com/u/username") == "reddit"
    
    def test_detect_instagram(self):
        assert detect_platform_from_url("https://www.instagram.com/username") == "instagram"
        assert detect_platform_from_url("https://instagram.com/user/") == "instagram"
    
    def test_detect_facebook(self):
        assert detect_platform_from_url("https://www.facebook.com/username") == "facebook"
        assert detect_platform_from_url("https://fb.com/page") == "facebook"
    
    def test_unknown_platform_raises(self):
        with pytest.raises(ScrapingError) as exc_info:
            detect_platform_from_url("https://myspace.com/user")
        assert "Cannot detect platform" in str(exc_info.value)


class TestExtractUsernameFromUrl:
    """Tests for username extraction."""
    
    def test_tiktok_username(self):
        assert _extract_username_from_url("https://www.tiktok.com/@cooluser", "tiktok") == "cooluser"
        assert _extract_username_from_url("https://tiktok.com/@user_123", "tiktok") == "user_123"
    
    def test_x_username(self):
        assert _extract_username_from_url("https://x.com/elonmusk", "x") == "elonmusk"
        assert _extract_username_from_url("https://twitter.com/jack", "x") == "jack"
    
    def test_reddit_username(self):
        assert _extract_username_from_url("https://reddit.com/user/spez", "reddit") == "spez"
        assert _extract_username_from_url("https://www.reddit.com/u/test_user", "reddit") == "test_user"
    
    def test_instagram_username(self):
        assert _extract_username_from_url("https://instagram.com/instagram", "instagram") == "instagram"
    
    def test_facebook_username(self):
        assert _extract_username_from_url("https://facebook.com/zuck", "facebook") == "zuck"


class TestParseCount:
    """Tests for count parsing."""
    
    def test_parse_simple_number(self):
        assert _parse_count("1234") == 1234
        assert _parse_count("500") == 500
    
    def test_parse_with_commas(self):
        assert _parse_count("1,234") == 1234
        assert _parse_count("1,234,567") == 1234567
    
    def test_parse_k_suffix(self):
        assert _parse_count("1.2K") == 1200
        assert _parse_count("50k") == 50000
    
    def test_parse_m_suffix(self):
        assert _parse_count("1.5M") == 1500000
        assert _parse_count("2m") == 2000000
    
    def test_parse_b_suffix(self):
        assert _parse_count("1B") == 1000000000
    
    def test_parse_empty(self):
        assert _parse_count("") == 0
        assert _parse_count(None) == 0


class TestScrapeTikTokProfile:
    """Tests for TikTok profile scraping."""
    
    @patch("core.profile_scraper.requests.get")
    def test_successful_scrape(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """
        <html>
        <head>
            <meta property="og:description" content="1.5M Followers, 100 Following, 50 Videos. Check out my content!">
            <meta property="og:image" content="https://example.com/avatar.jpg">
            <title>@testuser | TikTok</title>
        </head>
        </html>
        """
        mock_get.return_value = mock_response
        
        result = scrape_tiktok_profile("https://www.tiktok.com/@testuser")
        
        assert result["username"] == "testuser"
        assert result["follower_count"] == 1500000
        assert result["following_count"] == 100
    
    @patch("core.profile_scraper.requests.get")
    def test_http_error(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        with pytest.raises(ScrapingError) as exc_info:
            scrape_tiktok_profile("https://www.tiktok.com/@nonexistent")
        assert "404" in str(exc_info.value)


class TestScrapeXProfile:
    """Tests for X/Twitter profile scraping."""
    
    @patch("core.profile_scraper.os.environ.get")
    @patch("core.profile_scraper.requests.get")
    def test_api_scrape_with_token(self, mock_get, mock_env):
        mock_env.return_value = "test_bearer_token"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "username": "testuser",
                "created_at": "2020-01-01T00:00:00Z",
                "description": "Test bio",
                "public_metrics": {
                    "followers_count": 1000,
                    "following_count": 500,
                    "tweet_count": 200,
                },
                "profile_image_url": "https://example.com/avatar.jpg",
            }
        }
        mock_get.return_value = mock_response
        
        result = scrape_x_profile("https://x.com/testuser")
        
        assert result["username"] == "testuser"
        assert result["followers_count"] == 1000
        assert result["tweet_count"] == 200
    
    @patch("core.profile_scraper.os.environ.get")
    @patch("core.profile_scraper.requests.get")
    def test_meta_scrape_without_token(self, mock_get, mock_env):
        mock_env.return_value = None  # No token
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """
        <html>
        <head>
            <meta property="og:description" content="1,000 Followers, 500 Following">
        </head>
        </html>
        """
        mock_get.return_value = mock_response
        
        result = scrape_x_profile("https://x.com/testuser")
        
        assert result["username"] == "testuser"
        assert result["followers_count"] == 1000


class TestScrapeRedditProfile:
    """Tests for Reddit profile scraping."""
    
    @patch("core.profile_scraper.requests.get")
    def test_successful_scrape(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "name": "testuser",
                "created_utc": 1577836800,
                "link_karma": 5000,
                "comment_karma": 15000,
                "total_karma": 20000,
                "has_verified_email": True,
            }
        }
        mock_get.return_value = mock_response
        
        result = scrape_reddit_profile("https://reddit.com/user/testuser")
        
        assert result["username"] == "testuser"
        assert result["link_karma"] == 5000
        assert result["comment_karma"] == 15000
    
    @patch("core.profile_scraper.requests.get")
    def test_user_not_found(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        with pytest.raises(ScrapingError) as exc_info:
            scrape_reddit_profile("https://reddit.com/user/nonexistent")
        assert "not found" in str(exc_info.value)


class TestScrapeInstagramProfile:
    """Tests for Instagram profile scraping."""
    
    @patch("core.profile_scraper.requests.get")
    def test_successful_scrape(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """
        <html>
        <head>
            <meta property="og:description" content="10K Followers, 500 Following, 100 Posts - Travel photographer">
            <meta property="og:image" content="https://example.com/avatar.jpg">
        </head>
        </html>
        """
        mock_get.return_value = mock_response
        
        result = scrape_instagram_profile("https://instagram.com/testuser")
        
        assert result["username"] == "testuser"
        assert result["follower_count"] == 10000
        assert result["media_count"] == 100


class TestScrapeFacebookProfile:
    """Tests for Facebook profile scraping."""
    
    @patch("core.profile_scraper.requests.get")
    def test_successful_scrape(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """
        <html>
        <head>
            <meta property="og:title" content="Test Page">
            <meta property="og:description" content="5,000 followers - Page about testing">
        </head>
        </html>
        """
        mock_get.return_value = mock_response
        
        result = scrape_facebook_profile("https://facebook.com/testpage")
        
        assert result["name"] == "Test Page"
        assert result["follower_count"] == 5000


class TestScrapeProfile:
    """Tests for the main scrape_profile function."""
    
    @patch("core.profile_scraper.scrape_tiktok_profile")
    def test_routes_to_correct_scraper(self, mock_tiktok):
        mock_tiktok.return_value = {"username": "test"}
        
        result = scrape_profile("https://www.tiktok.com/@test")
        
        mock_tiktok.assert_called_once()
        assert "_scraped_from_url" in result
        assert "_scraped_at" in result
    
    def test_unsupported_url(self):
        with pytest.raises(ScrapingError):
            scrape_profile("https://myspace.com/user")
