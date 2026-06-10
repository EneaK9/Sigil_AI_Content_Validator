"""
Image fetcher for downloading and encoding images for Claude analysis.
Downloads images and returns base64-encoded data with media type.
"""
import base64
from typing import Optional
from urllib.parse import urlparse

import requests

from config import SCRAPER_TIMEOUT_SECONDS, SCRAPER_USER_AGENT
from core.models import ScrapingError


# Constants
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

# Extension to media type mapping
EXTENSION_TO_MEDIA_TYPE = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _get_media_type_from_url(url: str) -> Optional[str]:
    """
    Attempt to determine media type from URL file extension.
    
    Args:
        url: Image URL
        
    Returns:
        Media type string or None if cannot be determined
    """
    parsed = urlparse(url)
    path = parsed.path.lower()
    
    for ext, media_type in EXTENSION_TO_MEDIA_TYPE.items():
        if path.endswith(ext):
            return media_type
    
    return None


def _get_media_type(response: requests.Response, url: str) -> str:
    """
    Determine media type from response headers or URL extension.
    
    Args:
        response: HTTP response object
        url: Original URL (for extension fallback)
        
    Returns:
        Media type string
        
    Raises:
        ScrapingError: If media type cannot be determined or is unsupported
    """
    # Try Content-Type header first
    content_type = response.headers.get("Content-Type", "")
    
    # Extract media type (remove charset and other parameters)
    if content_type:
        media_type = content_type.split(";")[0].strip().lower()
        if media_type in SUPPORTED_IMAGE_TYPES:
            return media_type
    
    # Fallback to URL extension
    media_type = _get_media_type_from_url(url)
    if media_type:
        return media_type
    
    raise ScrapingError(
        f"Could not determine image type for URL: {url}\n"
        f"Content-Type header: {content_type}\n"
        f"Supported types: {', '.join(SUPPORTED_IMAGE_TYPES)}"
    )


def fetch_image_as_base64(url: str) -> tuple[str, str]:
    """
    Download an image and return it as base64-encoded data.
    
    Args:
        url: URL of the image to download
        
    Returns:
        Tuple of (base64_data, media_type)
        
    Raises:
        ScrapingError: If image cannot be downloaded, is too large, or has unsupported type
    """
    headers = {
        "User-Agent": SCRAPER_USER_AGENT,
        "Accept": "image/*",
    }
    
    try:
        # First, do a HEAD request to check Content-Length if available
        head_response = requests.head(
            url, 
            headers=headers, 
            timeout=SCRAPER_TIMEOUT_SECONDS,
            allow_redirects=True
        )
        
        content_length = head_response.headers.get("Content-Length")
        if content_length:
            size = int(content_length)
            if size > MAX_IMAGE_SIZE_BYTES:
                raise ScrapingError(
                    f"Image too large: {size / (1024*1024):.1f}MB exceeds {MAX_IMAGE_SIZE_BYTES / (1024*1024):.0f}MB limit.\n"
                    f"URL: {url}"
                )
        
        # Download the image
        response = requests.get(
            url,
            headers=headers,
            timeout=SCRAPER_TIMEOUT_SECONDS,
            allow_redirects=True
        )
        response.raise_for_status()
        
    except requests.Timeout:
        raise ScrapingError(
            f"Image download timed out after {SCRAPER_TIMEOUT_SECONDS} seconds.\n"
            f"URL: {url}"
        )
    except requests.HTTPError as e:
        raise ScrapingError(
            f"Failed to download image: HTTP {e.response.status_code}.\n"
            f"URL: {url}"
        )
    except requests.RequestException as e:
        raise ScrapingError(
            f"Failed to download image: {e}\n"
            f"URL: {url}"
        )
    
    # Verify size after download (in case Content-Length was missing or wrong)
    image_data = response.content
    if len(image_data) > MAX_IMAGE_SIZE_BYTES:
        raise ScrapingError(
            f"Image too large: {len(image_data) / (1024*1024):.1f}MB exceeds {MAX_IMAGE_SIZE_BYTES / (1024*1024):.0f}MB limit.\n"
            f"URL: {url}"
        )
    
    # Determine media type
    media_type = _get_media_type(response, url)
    
    # Encode to base64
    base64_data = base64.b64encode(image_data).decode("utf-8")
    
    return (base64_data, media_type)
