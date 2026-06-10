"""
Unit tests for core/image_fetcher.py - Image downloading and encoding.
"""
import base64
import pytest
from unittest.mock import patch, MagicMock

from core.image_fetcher import (
    fetch_image_as_base64,
    _get_media_type_from_url,
    _get_media_type,
    MAX_IMAGE_SIZE_BYTES,
    SUPPORTED_IMAGE_TYPES,
)
from core.models import ScrapingError


class TestGetMediaTypeFromUrl:
    """Tests for URL-based media type detection."""

    @pytest.mark.parametrize("url,expected", [
        ("https://example.com/image.jpg", "image/jpeg"),
        ("https://example.com/image.jpeg", "image/jpeg"),
        ("https://example.com/image.JPG", "image/jpeg"),
        ("https://example.com/image.png", "image/png"),
        ("https://example.com/image.PNG", "image/png"),
        ("https://example.com/image.webp", "image/webp"),
        ("https://example.com/image.gif", "image/gif"),
    ])
    def test_detect_from_extension(self, url, expected):
        """Should detect media type from file extension."""
        assert _get_media_type_from_url(url) == expected

    @pytest.mark.parametrize("url", [
        "https://example.com/image",
        "https://example.com/image.bmp",
        "https://example.com/image.svg",
        "https://example.com/",
    ])
    def test_unknown_extension_returns_none(self, url):
        """Should return None for unknown extensions."""
        assert _get_media_type_from_url(url) is None


class TestGetMediaType:
    """Tests for media type detection from response."""

    def test_from_content_type_header(self):
        """Should use Content-Type header when available."""
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "image/png; charset=utf-8"}
        
        result = _get_media_type(mock_response, "https://example.com/image")
        assert result == "image/png"

    def test_fallback_to_url_extension(self):
        """Should fallback to URL extension if Content-Type is missing."""
        mock_response = MagicMock()
        mock_response.headers = {}
        
        result = _get_media_type(mock_response, "https://example.com/image.jpg")
        assert result == "image/jpeg"

    def test_unsupported_type_raises_error(self):
        """Should raise error for unsupported media types."""
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "image/bmp"}
        
        with pytest.raises(ScrapingError) as exc_info:
            _get_media_type(mock_response, "https://example.com/image.bmp")
        
        assert "Could not determine image type" in str(exc_info.value)


class TestFetchImageAsBase64:
    """Tests for fetch_image_as_base64 function."""

    @patch("core.image_fetcher.requests.head")
    @patch("core.image_fetcher.requests.get")
    def test_successful_fetch(self, mock_get, mock_head):
        """Should successfully fetch and encode image."""
        # Setup mocks
        mock_head.return_value.headers = {"Content-Length": "1000"}
        
        mock_response = MagicMock()
        mock_response.content = b"fake image data"
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_get.return_value = mock_response
        
        base64_data, media_type = fetch_image_as_base64("https://example.com/image.jpg")
        
        assert media_type == "image/jpeg"
        assert base64_data == base64.b64encode(b"fake image data").decode("utf-8")

    @patch("core.image_fetcher.requests.head")
    def test_image_too_large_from_header(self, mock_head):
        """Should reject images that are too large (from Content-Length header)."""
        mock_head.return_value.headers = {"Content-Length": str(MAX_IMAGE_SIZE_BYTES + 1)}
        
        with pytest.raises(ScrapingError) as exc_info:
            fetch_image_as_base64("https://example.com/large.jpg")
        
        assert "too large" in str(exc_info.value).lower()

    @patch("core.image_fetcher.requests.head")
    @patch("core.image_fetcher.requests.get")
    def test_image_too_large_after_download(self, mock_get, mock_head):
        """Should reject images that are too large after download."""
        mock_head.return_value.headers = {}  # No Content-Length
        
        mock_response = MagicMock()
        mock_response.content = b"x" * (MAX_IMAGE_SIZE_BYTES + 1)
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_get.return_value = mock_response
        
        with pytest.raises(ScrapingError) as exc_info:
            fetch_image_as_base64("https://example.com/large.jpg")
        
        assert "too large" in str(exc_info.value).lower()

    @patch("core.image_fetcher.requests.head")
    def test_timeout_error(self, mock_head):
        """Should handle timeout errors."""
        import requests
        mock_head.side_effect = requests.Timeout()
        
        with pytest.raises(ScrapingError) as exc_info:
            fetch_image_as_base64("https://example.com/slow.jpg")
        
        assert "timed out" in str(exc_info.value).lower()

    @patch("core.image_fetcher.requests.head")
    @patch("core.image_fetcher.requests.get")
    def test_http_error(self, mock_get, mock_head):
        """Should handle HTTP errors."""
        import requests
        mock_head.return_value.headers = {}
        
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.HTTPError(response=mock_response)
        mock_get.return_value = mock_response
        
        with pytest.raises(ScrapingError) as exc_info:
            fetch_image_as_base64("https://example.com/missing.jpg")
        
        assert "404" in str(exc_info.value)

    @patch("core.image_fetcher.requests.head")
    @patch("core.image_fetcher.requests.get")
    def test_various_image_types(self, mock_get, mock_head):
        """Should handle various supported image types."""
        mock_head.return_value.headers = {}
        
        for media_type in SUPPORTED_IMAGE_TYPES:
            mock_response = MagicMock()
            mock_response.content = b"image data"
            mock_response.headers = {"Content-Type": media_type}
            mock_get.return_value = mock_response
            
            _, result_type = fetch_image_as_base64(f"https://example.com/image")
            assert result_type == media_type
