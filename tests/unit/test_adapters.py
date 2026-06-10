"""
Unit tests for adapters - Platform-specific content fetching.
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import datetime

from adapters.reddit import RedditAdapter
from adapters.x import XAdapter
from adapters.tiktok import TikTokAdapter
from adapters.facebook import FacebookAdapter
from adapters.instagram import InstagramAdapter
from core.models import PostData, ScrapingError, NotSupportedError


class TestRedditAdapter:
    """Tests for Reddit adapter."""

    @pytest.fixture
    def adapter(self):
        return RedditAdapter()

    def test_build_json_url(self, adapter):
        """Should correctly build .json URL."""
        url = "https://reddit.com/r/test/comments/abc123/title"
        json_url = adapter._build_json_url(url)
        assert json_url == "https://reddit.com/r/test/comments/abc123/title.json"

    def test_build_json_url_trailing_slash(self, adapter):
        """Should handle trailing slashes."""
        url = "https://reddit.com/r/test/comments/abc123/title/"
        json_url = adapter._build_json_url(url)
        assert json_url == "https://reddit.com/r/test/comments/abc123/title.json"

    def test_build_json_url_with_query_string(self, adapter):
        """Should preserve query strings."""
        url = "https://reddit.com/r/test/comments/abc123/title?sort=best"
        json_url = adapter._build_json_url(url)
        assert json_url == "https://reddit.com/r/test/comments/abc123/title.json?sort=best"

    def test_parse_response_extracts_data(self, adapter, mock_reddit_response):
        """Should correctly parse Reddit JSON response."""
        post = adapter._parse_response("http://test.com", mock_reddit_response)
        
        assert isinstance(post, PostData)
        assert post.platform == "reddit"
        assert post.title == "Test Reddit Post"
        assert "body of the Reddit post" in post.text
        assert post.author == "u/testuser"

    def test_parse_link_post(self, adapter, mock_reddit_link_post):
        """Should handle link posts (no selftext)."""
        post = adapter._parse_response("http://test.com", mock_reddit_link_post)
        
        assert post.title == "Check out this link"
        assert "link post" in post.text.lower()

    def test_parse_invalid_response_raises_error(self, adapter):
        """Should raise ScrapingError for invalid response structure."""
        invalid_data = {"invalid": "structure"}
        
        with pytest.raises(ScrapingError) as exc_info:
            adapter._parse_response("http://test.com", invalid_data)
        
        assert "Unexpected" in str(exc_info.value)

    @patch("adapters.reddit.requests.get")
    def test_fetch_success(self, mock_get, adapter, mock_reddit_response):
        """Should successfully fetch and parse Reddit post."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_reddit_response
        mock_get.return_value = mock_response
        
        post = adapter.fetch("https://reddit.com/r/test/comments/abc123/title")
        
        assert post.platform == "reddit"
        assert post.title == "Test Reddit Post"

    @patch("adapters.reddit.requests.get")
    def test_fetch_404_raises_error(self, mock_get, adapter):
        """Should raise ScrapingError on 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        with pytest.raises(ScrapingError) as exc_info:
            adapter.fetch("https://reddit.com/r/test/comments/deleted/post")
        
        assert "404" in str(exc_info.value)
        assert "deleted" in str(exc_info.value).lower() or "not found" in str(exc_info.value).lower()

    @patch("adapters.reddit.requests.get")
    def test_fetch_403_raises_error(self, mock_get, adapter):
        """Should raise ScrapingError on 403 (private subreddit)."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response
        
        with pytest.raises(ScrapingError) as exc_info:
            adapter.fetch("https://reddit.com/r/private/comments/abc/post")
        
        assert "403" in str(exc_info.value)
        assert "private" in str(exc_info.value).lower()

    @patch("adapters.reddit.requests.get")
    def test_fetch_timeout_raises_error(self, mock_get, adapter):
        """Should raise ScrapingError on timeout."""
        import requests
        mock_get.side_effect = requests.Timeout()
        
        with pytest.raises(ScrapingError) as exc_info:
            adapter.fetch("https://reddit.com/r/test/comments/abc/post")
        
        assert "timed out" in str(exc_info.value).lower()

    def test_extract_image_urls_single_image(self, adapter):
        """Should extract URL from single image post."""
        post_data = {
            "title": "Test",
            "selftext": "",
            "author": "test",
            "post_hint": "image",
            "url": "https://i.redd.it/abc123.jpg"
        }
        
        image_urls = adapter._extract_image_urls(post_data)
        
        assert len(image_urls) == 1
        assert image_urls[0] == "https://i.redd.it/abc123.jpg"

    def test_extract_image_urls_gallery(self, adapter):
        """Should extract URLs from gallery post."""
        post_data = {
            "title": "Gallery Test",
            "selftext": "",
            "author": "test",
            "is_gallery": True,
            "media_metadata": {
                "img1": {"s": {"u": "https://preview.redd.it/img1.jpg?width=1080&amp;format=pjpg"}},
                "img2": {"s": {"u": "https://preview.redd.it/img2.jpg?width=1080&amp;format=pjpg"}},
            },
            "gallery_data": {
                "items": [
                    {"media_id": "img1"},
                    {"media_id": "img2"},
                ]
            }
        }
        
        image_urls = adapter._extract_image_urls(post_data)
        
        assert len(image_urls) == 2
        # Should unescape &amp; to &
        assert "&" in image_urls[0]
        assert "&amp;" not in image_urls[0]

    def test_extract_image_urls_preview_fallback(self, adapter):
        """Should fallback to preview image."""
        post_data = {
            "title": "Link Post",
            "selftext": "",
            "author": "test",
            "url": "https://example.com/article",
            "preview": {
                "images": [
                    {"source": {"url": "https://preview.redd.it/preview.jpg?auto=webp&amp;s=abc"}}
                ]
            }
        }
        
        image_urls = adapter._extract_image_urls(post_data)
        
        assert len(image_urls) == 1
        assert "preview.redd.it" in image_urls[0]

    def test_extract_image_urls_no_images(self, adapter):
        """Should return empty list for text-only post."""
        post_data = {
            "title": "Text Post",
            "selftext": "Just text, no images",
            "author": "test",
        }
        
        image_urls = adapter._extract_image_urls(post_data)
        
        assert len(image_urls) == 0

    def test_unescape_url(self, adapter):
        """Should unescape HTML entities in URLs."""
        url = "https://example.com/image.jpg?a=1&amp;b=2&amp;c=3"
        unescaped = adapter._unescape_url(url)
        assert unescaped == "https://example.com/image.jpg?a=1&b=2&c=3"

    def test_extract_video_urls_reddit_hosted(self, adapter):
        """Should extract video URL from Reddit-hosted video posts."""
        post_data = {
            "title": "Check out this video",
            "selftext": "",
            "author": "test",
            "is_video": True,
            "media": {
                "reddit_video": {
                    "fallback_url": "https://v.redd.it/abc123/DASH_720.mp4?source=fallback"
                }
            }
        }
        
        video_urls = adapter._extract_video_urls(post_data)
        
        assert len(video_urls) == 1
        assert "v.redd.it" in video_urls[0]

    def test_extract_video_urls_no_video(self, adapter):
        """Should return empty list for text-only posts."""
        post_data = {
            "title": "Text Post",
            "selftext": "Just text content",
            "author": "test",
            "is_video": False,
        }
        
        video_urls = adapter._extract_video_urls(post_data)
        
        assert len(video_urls) == 0

    def test_extract_video_urls_unescapes_amp(self, adapter):
        """Should unescape HTML entities in video URLs."""
        post_data = {
            "title": "Video post",
            "selftext": "",
            "author": "test",
            "is_video": True,
            "media": {
                "reddit_video": {
                    "fallback_url": "https://v.redd.it/abc?a=1&amp;b=2"
                }
            }
        }
        
        video_urls = adapter._extract_video_urls(post_data)
        
        assert "&amp;" not in video_urls[0]
        assert "&" in video_urls[0]


class TestXAdapter:
    """Tests for X/Twitter adapter."""

    @pytest.fixture
    def adapter(self):
        return XAdapter()

    def test_extract_tweet_id(self, adapter):
        """Should extract tweet ID from URL."""
        url = "https://x.com/user/status/1234567890123456789"
        tweet_id = adapter._extract_tweet_id(url)
        assert tweet_id == "1234567890123456789"

    def test_extract_tweet_id_twitter_domain(self, adapter):
        """Should work with twitter.com domain."""
        url = "https://twitter.com/user/status/9876543210"
        tweet_id = adapter._extract_tweet_id(url)
        assert tweet_id == "9876543210"

    def test_extract_tweet_id_invalid_url(self, adapter):
        """Should raise ScrapingError for invalid URL format."""
        with pytest.raises(ScrapingError) as exc_info:
            adapter._extract_tweet_id("https://x.com/user/likes")
        
        assert "Could not extract tweet ID" in str(exc_info.value)

    @patch.dict("os.environ", {}, clear=True)
    def test_fetch_without_bearer_token(self, adapter):
        """Should raise ScrapingError if bearer token not set."""
        with pytest.raises(ScrapingError) as exc_info:
            adapter.fetch("https://x.com/user/status/123")
        
        assert "X_BEARER_TOKEN" in str(exc_info.value)
        assert "environment variable" in str(exc_info.value).lower()

    def test_extract_image_urls_with_photos(self, adapter):
        """Should extract URLs from media includes."""
        data = {
            "data": {"text": "Tweet with photos"},
            "includes": {
                "media": [
                    {"type": "photo", "url": "https://pbs.twimg.com/media/photo1.jpg"},
                    {"type": "photo", "url": "https://pbs.twimg.com/media/photo2.jpg"},
                ]
            }
        }
        
        image_urls = adapter._extract_image_urls(data)
        
        assert len(image_urls) == 2
        assert "photo1.jpg" in image_urls[0]
        assert "photo2.jpg" in image_urls[1]

    def test_extract_image_urls_with_gif(self, adapter):
        """Should include animated GIFs."""
        data = {
            "data": {"text": "Tweet with gif"},
            "includes": {
                "media": [
                    {"type": "animated_gif", "url": "https://pbs.twimg.com/tweet_video_thumb/gif.jpg"},
                ]
            }
        }
        
        image_urls = adapter._extract_image_urls(data)
        
        assert len(image_urls) == 1

    def test_extract_image_urls_ignores_video(self, adapter):
        """Should not include video media."""
        data = {
            "data": {"text": "Tweet with video"},
            "includes": {
                "media": [
                    {"type": "video", "url": "https://pbs.twimg.com/video.mp4"},
                    {"type": "photo", "url": "https://pbs.twimg.com/photo.jpg"},
                ]
            }
        }
        
        image_urls = adapter._extract_image_urls(data)
        
        assert len(image_urls) == 1
        assert "photo.jpg" in image_urls[0]

    def test_extract_image_urls_no_media(self, adapter):
        """Should return empty list when no media."""
        data = {
            "data": {"text": "Text only tweet"},
        }
        
        image_urls = adapter._extract_image_urls(data)
        
        assert len(image_urls) == 0

    def test_extract_video_urls_with_video(self, adapter):
        """Should return tweet URL when video media is detected."""
        data = {
            "data": {"text": "Tweet with video"},
            "includes": {
                "media": [
                    {"type": "video", "media_key": "123"},
                ]
            }
        }
        tweet_url = "https://x.com/user/status/123456"
        
        video_urls = adapter._extract_video_urls(data, tweet_url)
        
        assert len(video_urls) == 1
        assert video_urls[0] == tweet_url

    def test_extract_video_urls_no_video(self, adapter):
        """Should return empty list when no video media."""
        data = {
            "data": {"text": "Tweet with photos only"},
            "includes": {
                "media": [
                    {"type": "photo", "url": "https://pbs.twimg.com/photo.jpg"},
                ]
            }
        }
        
        video_urls = adapter._extract_video_urls(data, "https://x.com/user/status/123")
        
        assert len(video_urls) == 0

    def test_extract_video_urls_mixed_media(self, adapter):
        """Should return tweet URL when video exists alongside photos."""
        data = {
            "data": {"text": "Tweet with video and photo"},
            "includes": {
                "media": [
                    {"type": "photo", "url": "https://pbs.twimg.com/photo.jpg"},
                    {"type": "video", "media_key": "456"},
                ]
            }
        }
        tweet_url = "https://x.com/user/status/789"
        
        video_urls = adapter._extract_video_urls(data, tweet_url)
        
        assert len(video_urls) == 1
        assert video_urls[0] == tweet_url


class TestTikTokAdapter:
    """Tests for TikTok adapter."""

    @pytest.fixture
    def adapter(self):
        return TikTokAdapter()

    @patch("adapters.tiktok.requests.get")
    def test_parse_html_extracts_description(self, mock_get, adapter):
        """Should extract description from meta tags."""
        html = """
        <html>
        <head>
            <meta property="og:description" content="This is a TikTok video caption #viral #fyp">
            <meta property="og:title" content="@creator on TikTok">
            <title>Video by @creator</title>
        </head>
        <body></body>
        </html>
        """
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response
        
        post = adapter.fetch("https://tiktok.com/@user/video/123")
        
        assert "TikTok video caption" in post.text
        assert post.platform == "tiktok"

    @patch("adapters.tiktok.requests.get")
    def test_parse_html_fallback_to_meta_description(self, mock_get, adapter):
        """Should fallback to meta name=description."""
        html = """
        <html>
        <head>
            <meta name="description" content="Fallback description content here">
            <title>TikTok Video</title>
        </head>
        <body></body>
        </html>
        """
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response
        
        post = adapter.fetch("https://tiktok.com/@user/video/123")
        
        assert "Fallback description" in post.text

    @patch("adapters.tiktok.requests.get")
    def test_parse_html_no_description(self, mock_get, adapter):
        """Should return note when no description extractable."""
        html = """
        <html>
        <head><title>T</title></head>
        <body></body>
        </html>
        """
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response
        
        post = adapter.fetch("https://tiktok.com/@user/video/123")
        
        assert "not extractable" in post.text.lower() or "manual review" in post.text.lower()

    @patch("adapters.tiktok.requests.get")
    def test_extract_og_image(self, mock_get, adapter):
        """Should extract og:image thumbnail."""
        html = """
        <html>
        <head>
            <meta property="og:description" content="Video caption here">
            <meta property="og:image" content="https://p16-sign.tiktokcdn.com/obj/image.jpg">
            <title>TikTok</title>
        </head>
        <body></body>
        </html>
        """
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response
        
        post = adapter.fetch("https://tiktok.com/@user/video/123")
        
        assert len(post.image_urls) == 1
        assert "tiktokcdn.com" in post.image_urls[0]

    @patch("adapters.tiktok.requests.get")
    def test_tiktok_url_becomes_video_url(self, mock_get, adapter):
        """Should include the TikTok URL as video_urls for transcription."""
        html = """
        <html>
        <head>
            <meta property="og:description" content="Video caption here">
            <title>TikTok</title>
        </head>
        <body></body>
        </html>
        """
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response
        
        post = adapter.fetch("https://tiktok.com/@user/video/123456789")
        
        assert len(post.video_urls) == 1
        assert post.video_urls[0] == "https://tiktok.com/@user/video/123456789"

    @patch("adapters.tiktok.requests.get")
    def test_no_og_image(self, mock_get, adapter):
        """Should return empty image_urls when no og:image."""
        html = """
        <html>
        <head>
            <meta property="og:description" content="Video caption">
            <title>TikTok</title>
        </head>
        <body></body>
        </html>
        """
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response
        
        post = adapter.fetch("https://tiktok.com/@user/video/123")
        
        assert len(post.image_urls) == 0


class TestFacebookAdapter:
    """Tests for Facebook adapter."""

    @pytest.fixture
    def adapter(self):
        return FacebookAdapter()

    def test_fetch_raises_not_supported_error(self, adapter):
        """Should immediately raise NotSupportedError."""
        with pytest.raises(NotSupportedError) as exc_info:
            adapter.fetch("https://facebook.com/user/posts/123")
        
        error_msg = str(exc_info.value)
        assert "cannot be automatically scraped" in error_msg
        assert "--text" in error_msg
        assert "facebook" in error_msg.lower()


class TestInstagramAdapter:
    """Tests for Instagram adapter."""

    @pytest.fixture
    def adapter(self):
        return InstagramAdapter()

    def test_fetch_raises_not_supported_error(self, adapter):
        """Should immediately raise NotSupportedError."""
        with pytest.raises(NotSupportedError) as exc_info:
            adapter.fetch("https://instagram.com/p/ABC123/")
        
        error_msg = str(exc_info.value)
        assert "cannot be automatically scraped" in error_msg
        assert "--text" in error_msg
        assert "instagram" in error_msg.lower()
