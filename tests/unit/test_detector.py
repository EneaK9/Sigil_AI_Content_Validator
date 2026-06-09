"""
Unit tests for core/detector.py - Platform detection from URLs.
"""
import pytest
from core.detector import detect_platform, is_supported_platform, get_supported_platforms


class TestDetectPlatform:
    """Tests for detect_platform function."""

    # Reddit URLs
    @pytest.mark.parametrize("url", [
        "https://www.reddit.com/r/worldnews/comments/abc123/test",
        "https://reddit.com/r/python/comments/xyz/post",
        "https://old.reddit.com/r/test/comments/123/title",
        "http://reddit.com/r/sub/comments/id/title",
        "https://redd.it/abc123",
        "https://www.redd.it/xyz789",
    ])
    def test_detect_reddit(self, url):
        """Should detect Reddit URLs correctly."""
        assert detect_platform(url) == "reddit"

    # X/Twitter URLs
    @pytest.mark.parametrize("url", [
        "https://x.com/user/status/1234567890",
        "https://www.x.com/elonmusk/status/9876543210",
        "https://twitter.com/user/status/1111111111",
        "https://www.twitter.com/test/status/2222222222",
        "http://x.com/someone/status/123",
    ])
    def test_detect_x(self, url):
        """Should detect X/Twitter URLs correctly."""
        assert detect_platform(url) == "x"

    # TikTok URLs
    @pytest.mark.parametrize("url", [
        "https://www.tiktok.com/@user/video/123456789",
        "https://tiktok.com/@creator/video/987654321",
        "https://vm.tiktok.com/abc123/",
        "http://vm.tiktok.com/xyz789",
    ])
    def test_detect_tiktok(self, url):
        """Should detect TikTok URLs correctly."""
        assert detect_platform(url) == "tiktok"

    # Facebook URLs
    @pytest.mark.parametrize("url", [
        "https://www.facebook.com/user/posts/123",
        "https://facebook.com/groups/test/posts/456",
        "https://fb.com/story/789",
        "https://fb.watch/abc123/",
        "http://www.fb.com/post/123",
    ])
    def test_detect_facebook(self, url):
        """Should detect Facebook URLs correctly."""
        assert detect_platform(url) == "facebook"

    # Instagram URLs
    @pytest.mark.parametrize("url", [
        "https://www.instagram.com/p/ABC123/",
        "https://instagram.com/p/XYZ789/",
        "https://www.instagram.com/reel/DEF456/",
        "https://instagram.com/reel/GHI789/",
    ])
    def test_detect_instagram(self, url):
        """Should detect Instagram URLs correctly."""
        assert detect_platform(url) == "instagram"

    # Invalid URLs
    @pytest.mark.parametrize("url", [
        "https://google.com",
        "https://youtube.com/watch?v=abc123",
        "https://linkedin.com/posts/123",
        "https://example.com/post/456",
        "not-a-valid-url",
        "http://randomsite.com",
    ])
    def test_detect_invalid_urls(self, url):
        """Should raise ValueError for unsupported URLs."""
        with pytest.raises(ValueError) as exc_info:
            detect_platform(url)
        
        # Error message should list supported patterns
        assert "reddit" in str(exc_info.value).lower()
        assert "Could not detect platform" in str(exc_info.value)

    def test_detect_empty_url(self):
        """Should raise ValueError for empty URL."""
        with pytest.raises(ValueError):
            detect_platform("")

    def test_case_insensitive(self):
        """Should handle uppercase URLs."""
        assert detect_platform("HTTPS://REDDIT.COM/R/TEST/COMMENTS/123/TITLE") == "reddit"
        assert detect_platform("HTTPS://X.COM/USER/STATUS/123") == "x"


class TestIsSupportedPlatform:
    """Tests for is_supported_platform function."""

    @pytest.mark.parametrize("platform", ["reddit", "x", "tiktok", "facebook", "instagram"])
    def test_supported_platforms(self, platform):
        """Should return True for supported platforms."""
        assert is_supported_platform(platform) is True

    @pytest.mark.parametrize("platform", ["youtube", "linkedin", "pinterest", "snapchat", ""])
    def test_unsupported_platforms(self, platform):
        """Should return False for unsupported platforms."""
        assert is_supported_platform(platform) is False


class TestGetSupportedPlatforms:
    """Tests for get_supported_platforms function."""

    def test_returns_all_platforms(self):
        """Should return list of all supported platforms."""
        platforms = get_supported_platforms()
        assert isinstance(platforms, list)
        assert len(platforms) == 5
        assert "reddit" in platforms
        assert "x" in platforms
        assert "tiktok" in platforms
        assert "facebook" in platforms
        assert "instagram" in platforms
