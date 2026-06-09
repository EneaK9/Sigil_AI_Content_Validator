"""
X (Twitter) adapter for fetching tweet content.
Uses Twitter API v2 free tier with bearer token authentication.
"""
import os
import re
from datetime import datetime, timezone

import requests

from adapters.base import BaseAdapter
from core.models import PostData, ScrapingError


class XAdapter(BaseAdapter):
    """
    Adapter for fetching X (Twitter) post content.
    
    Uses the Twitter API v2 free tier endpoint.
    Requires X_BEARER_TOKEN environment variable to be set.
    """
    
    API_BASE = "https://api.twitter.com/2"
    
    def fetch(self, url: str) -> PostData:
        """
        Fetch tweet content from an X/Twitter URL.
        
        Args:
            url: X/Twitter post URL (e.g., https://x.com/user/status/123456789)
            
        Returns:
            PostData object with tweet content
            
        Raises:
            ScrapingError: If the tweet cannot be fetched
        """
        bearer_token = os.environ.get("X_BEARER_TOKEN")
        if not bearer_token:
            raise ScrapingError(
                "X_BEARER_TOKEN environment variable is not set.\n\n"
                "To get a bearer token:\n"
                "1. Go to https://developer.twitter.com/\n"
                "2. Create a project and app\n"
                "3. Generate a bearer token\n"
                "4. Add to your .env file: X_BEARER_TOKEN=your-token-here"
            )
        
        tweet_id = self._extract_tweet_id(url)
        
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "User-Agent": "PolicyGuard/1.0"
        }
        
        params = {
            "tweet.fields": "text,author_id,created_at,attachments",
            "expansions": "author_id,attachments.media_keys",
            "media.fields": "url,type",
            "user.fields": "username"
        }
        
        api_url = f"{self.API_BASE}/tweets/{tweet_id}"
        
        try:
            response = requests.get(api_url, headers=headers, params=params, timeout=10)
        except requests.Timeout:
            raise ScrapingError(
                f"X API request timed out after 10 seconds. "
                f"Try again later."
            )
        except requests.RequestException as e:
            raise ScrapingError(
                f"Failed to connect to X API: {e}"
            )
        
        if response.status_code == 401:
            raise ScrapingError(
                "X API returned 401 Unauthorized. "
                "Your bearer token may be invalid or expired. "
                "Check your X_BEARER_TOKEN environment variable."
            )
        
        if response.status_code == 404:
            raise ScrapingError(
                f"Tweet not found (404). "
                f"The tweet may have been deleted or the ID is incorrect. "
                f"URL: {url}"
            )
        
        if response.status_code == 403:
            raise ScrapingError(
                f"Access forbidden (403). "
                f"The tweet may be from a protected/private account. "
                f"URL: {url}"
            )
        
        if response.status_code != 200:
            raise ScrapingError(
                f"X API returned HTTP {response.status_code}. "
                f"URL: {url}"
            )
        
        try:
            data = response.json()
        except ValueError:
            raise ScrapingError(
                f"X API returned invalid JSON. "
                f"URL: {url}"
            )
        
        return self._parse_response(url, data)
    
    def _extract_tweet_id(self, url: str) -> str:
        """
        Extract tweet ID from X/Twitter URL.
        
        Args:
            url: X/Twitter URL
            
        Returns:
            Tweet ID string
            
        Raises:
            ScrapingError: If tweet ID cannot be extracted
        """
        # Match patterns like:
        # https://x.com/username/status/123456789
        # https://twitter.com/username/status/123456789
        pattern = r"(?:x\.com|twitter\.com)/\w+/status/(\d+)"
        match = re.search(pattern, url)
        
        if not match:
            raise ScrapingError(
                f"Could not extract tweet ID from URL: {url}\n"
                f"Expected format: https://x.com/username/status/TWEET_ID"
            )
        
        return match.group(1)
    
    def _parse_response(self, url: str, data: dict) -> PostData:
        """
        Parse X API response into PostData.
        
        Args:
            url: Original URL
            data: Parsed JSON response from X API
            
        Returns:
            PostData object
        """
        if "data" not in data:
            error_msg = data.get("errors", [{}])[0].get("message", "Unknown error")
            raise ScrapingError(
                f"X API error: {error_msg}. "
                f"URL: {url}"
            )
        
        tweet = data["data"]
        text = tweet.get("text", "")
        
        # Get author username from includes
        author = ""
        if "includes" in data and "users" in data["includes"]:
            users = data["includes"]["users"]
            if users:
                author = f"@{users[0].get('username', '')}"
        
        # Extract image URLs from media attachments
        image_urls = self._extract_image_urls(data)
        
        if not text:
            raise ScrapingError(
                f"Tweet has no text content. "
                f"URL: {url}"
            )
        
        return PostData(
            url=url,
            platform="x",
            text=text,
            author=author,
            title="",
            image_urls=image_urls,
            scraped_at=datetime.now(timezone.utc).isoformat()
        )
    
    def _extract_image_urls(self, data: dict) -> list[str]:
        """
        Extract image URLs from X API response media includes.
        
        Args:
            data: Full API response data
            
        Returns:
            List of image URLs
        """
        image_urls: list[str] = []
        
        includes = data.get("includes", {})
        media_list = includes.get("media", [])
        
        for media in media_list:
            media_type = media.get("type", "")
            media_url = media.get("url", "")
            
            # Include photos and animated GIFs
            if media_type in ("photo", "animated_gif") and media_url:
                image_urls.append(media_url)
        
        return image_urls
