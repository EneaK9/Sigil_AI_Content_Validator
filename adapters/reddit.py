"""
Reddit adapter for fetching post content.
Uses Reddit's public .json endpoint (no OAuth required).
"""
from datetime import datetime, timezone
from typing import Optional
import re

import requests

from adapters.base import BaseAdapter
from config import REDDIT_USER_AGENT
from core.models import PostData, ScrapingError


class RedditAdapter(BaseAdapter):
    """
    Adapter for fetching Reddit post content.
    
    Uses the public .json endpoint by appending .json to any Reddit post URL.
    No authentication required for public posts.
    """
    
    def fetch(self, url: str) -> PostData:
        """
        Fetch post content from a Reddit URL.
        
        Args:
            url: Reddit post URL (e.g., https://reddit.com/r/sub/comments/id/title)
            
        Returns:
            PostData object with post content
            
        Raises:
            ScrapingError: If the post cannot be fetched
        """
        json_url = self._build_json_url(url)
        
        headers = {"User-Agent": REDDIT_USER_AGENT}
        
        try:
            response = requests.get(json_url, headers=headers, timeout=10)
        except requests.Timeout:
            raise ScrapingError(
                f"Reddit request timed out after 10 seconds. "
                f"The Reddit servers may be slow. Try again later."
            )
        except requests.RequestException as e:
            raise ScrapingError(
                f"Failed to connect to Reddit: {e}. "
                f"Check your internet connection and try again."
            )
        
        if response.status_code == 404:
            raise ScrapingError(
                f"Reddit returned 404 for this URL. "
                f"The post may have been deleted or the URL is incorrect. "
                f"URL: {url}"
            )
        
        if response.status_code == 403:
            raise ScrapingError(
                f"Reddit returned 403 for this URL. "
                f"The subreddit is likely private or quarantined. "
                f"Try a different post URL."
            )
        
        if response.status_code != 200:
            raise ScrapingError(
                f"Reddit returned HTTP {response.status_code}. "
                f"URL: {url}"
            )
        
        try:
            data = response.json()
        except ValueError:
            raise ScrapingError(
                f"Reddit returned invalid JSON. "
                f"The URL may not point to a valid Reddit post. "
                f"URL: {url}"
            )
        
        return self._parse_response(url, data)
    
    def _build_json_url(self, url: str) -> str:
        """
        Convert a Reddit URL to its JSON endpoint.
        
        Args:
            url: Original Reddit URL
            
        Returns:
            URL with .json appended (handling query strings properly)
        """
        # Remove trailing slash
        url = url.rstrip("/")
        
        # Handle query strings
        if "?" in url:
            base, query = url.split("?", 1)
            return f"{base}.json?{query}"
        
        return f"{url}.json"
    
    def _parse_response(self, url: str, data: list) -> PostData:
        """
        Parse Reddit JSON response into PostData.
        
        Args:
            url: Original URL
            data: Parsed JSON response from Reddit
            
        Returns:
            PostData object
            
        Raises:
            ScrapingError: If response structure is unexpected
        """
        try:
            post = data[0]["data"]["children"][0]["data"]
        except (KeyError, IndexError, TypeError) as e:
            raise ScrapingError(
                f"Unexpected Reddit API response structure. "
                f"The URL may not point to a valid Reddit post. "
                f"URL: {url}"
            )
        
        title = post.get("title", "")
        selftext = post.get("selftext", "")
        author = post.get("author", "")
        
        # Build text content
        if selftext:
            text = f"{title}\n\n{selftext}" if title else selftext
        elif title:
            # Link post (no selftext) - use title only with note
            text = f"{title}\n\n[This is a link post with no text content. Only the title is available for analysis.]"
        else:
            raise ScrapingError(
                f"Reddit post has no title or text content. "
                f"URL: {url}"
            )
        
        # Extract image URLs
        image_urls = self._extract_image_urls(post)
        
        return PostData(
            url=url,
            platform="reddit",
            text=text,
            author=f"u/{author}" if author else "",
            title=title,
            image_urls=image_urls,
            scraped_at=datetime.now(timezone.utc).isoformat()
        )
    
    def _extract_image_urls(self, post: dict) -> list[str]:
        """
        Extract image URLs from Reddit post data.
        
        Handles:
        - Single image posts (post_hint == "image")
        - Gallery posts (is_gallery with media_metadata)
        - Preview images as fallback
        
        Args:
            post: Reddit post data dict
            
        Returns:
            List of image URLs
        """
        image_urls: list[str] = []
        
        # Case 1: Single image post
        if post.get("post_hint") == "image":
            image_url = post.get("url", "")
            if image_url and self._is_image_url(image_url):
                image_urls.append(self._unescape_url(image_url))
                return image_urls
        
        # Case 2: Gallery post
        if post.get("is_gallery") and post.get("media_metadata"):
            media_metadata = post["media_metadata"]
            gallery_data = post.get("gallery_data", {}).get("items", [])
            
            # Use gallery_data order if available, otherwise iterate media_metadata
            if gallery_data:
                for item in gallery_data:
                    media_id = item.get("media_id")
                    if media_id and media_id in media_metadata:
                        media = media_metadata[media_id]
                        image_url = self._extract_gallery_image_url(media)
                        if image_url:
                            image_urls.append(image_url)
            else:
                for media_id, media in media_metadata.items():
                    image_url = self._extract_gallery_image_url(media)
                    if image_url:
                        image_urls.append(image_url)
            
            if image_urls:
                return image_urls
        
        # Case 3: Preview image fallback
        preview = post.get("preview", {})
        images = preview.get("images", [])
        if images:
            source = images[0].get("source", {})
            image_url = source.get("url", "")
            if image_url:
                image_urls.append(self._unescape_url(image_url))
        
        return image_urls
    
    def _extract_gallery_image_url(self, media: dict) -> Optional[str]:
        """
        Extract image URL from gallery media metadata entry.
        
        Args:
            media: Media metadata entry
            
        Returns:
            Image URL or None
        """
        # Try to get the source image URL
        source = media.get("s", {})
        image_url = source.get("u") or source.get("gif")
        
        if image_url:
            return self._unescape_url(image_url)
        
        return None
    
    def _unescape_url(self, url: str) -> str:
        """
        Unescape HTML entities in URL (Reddit encodes & as &amp;).
        
        Args:
            url: URL that may contain HTML entities
            
        Returns:
            Unescaped URL
        """
        return url.replace("&amp;", "&")
    
    def _is_image_url(self, url: str) -> bool:
        """
        Check if URL appears to be a direct image link.
        
        Args:
            url: URL to check
            
        Returns:
            True if URL looks like an image
        """
        url_lower = url.lower()
        image_extensions = (".jpg", ".jpeg", ".png", ".gif", ".webp")
        image_hosts = ("i.redd.it", "i.imgur.com", "preview.redd.it")
        
        # Check extension
        for ext in image_extensions:
            if ext in url_lower:
                return True
        
        # Check known image hosts
        for host in image_hosts:
            if host in url_lower:
                return True
        
        return False
