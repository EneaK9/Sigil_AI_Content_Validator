"""
TikTok adapter for fetching video description/caption.
Uses HTML meta tag scraping since TikTok has no public content API.
"""
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from adapters.base import BaseAdapter
from config import SCRAPER_USER_AGENT
from core.models import PostData, ScrapingError


class TikTokAdapter(BaseAdapter):
    """
    Adapter for fetching TikTok video description/caption.
    
    Scrapes meta tags from the TikTok page HTML since there's no
    public API for post text content.
    """
    
    def fetch(self, url: str) -> PostData:
        """
        Fetch video description from a TikTok URL.
        
        Args:
            url: TikTok video URL
            
        Returns:
            PostData object with video description
            
        Raises:
            ScrapingError: If the content cannot be fetched
        """
        headers = {
            "User-Agent": SCRAPER_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
        except requests.Timeout:
            raise ScrapingError(
                f"TikTok request timed out after 15 seconds. "
                f"Try again later."
            )
        except requests.RequestException as e:
            raise ScrapingError(
                f"Failed to connect to TikTok: {e}"
            )
        
        if response.status_code == 404:
            raise ScrapingError(
                f"TikTok returned 404. "
                f"The video may have been deleted or the URL is incorrect. "
                f"URL: {url}"
            )
        
        if response.status_code != 200:
            raise ScrapingError(
                f"TikTok returned HTTP {response.status_code}. "
                f"URL: {url}"
            )
        
        return self._parse_html(url, response.text)
    
    def _parse_html(self, url: str, html: str) -> PostData:
        """
        Parse TikTok HTML to extract video description.
        
        Args:
            url: Original URL
            html: HTML content
            
        Returns:
            PostData object
        """
        soup = BeautifulSoup(html, "html.parser")
        
        # Try to get description from meta tags
        description = None
        author = ""
        
        # Try og:description first
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            description = og_desc["content"]
        
        # Fallback to name="description"
        if not description:
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                description = meta_desc["content"]
        
        # Try to get title as additional context
        title_tag = soup.find("title")
        title_text = title_tag.get_text(strip=True) if title_tag else ""
        
        # Try to extract author from og:title or title
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            # TikTok titles often include @username
            title_content = og_title["content"]
            if "@" in title_content:
                parts = title_content.split("@")
                if len(parts) > 1:
                    author_part = parts[1].split()[0] if parts[1] else ""
                    author = f"@{author_part}" if author_part else ""
        
        # Build text content
        if description and len(description) > 20:
            text = description
        elif title_text and len(title_text) > 20:
            text = title_text
        else:
            # Cannot extract meaningful content
            text = (
                "[TikTok caption not extractable from this URL. "
                "Video content requires manual review. "
                "The post may contain visual or audio content that cannot be analyzed as text.]"
            )
        
        # Extract thumbnail/preview image from og:image
        image_urls = self._extract_image_urls(soup)
        
        # TikTok post URL is the video itself
        video_urls = [url]
        
        return PostData(
            url=url,
            platform="tiktok",
            text=text,
            author=author,
            title="",
            image_urls=image_urls,
            video_urls=video_urls,
            scraped_at=datetime.now(timezone.utc).isoformat()
        )
    
    def _extract_image_urls(self, soup: BeautifulSoup) -> list[str]:
        """
        Extract image URLs from TikTok page meta tags.
        
        Args:
            soup: BeautifulSoup parsed HTML
            
        Returns:
            List of image URLs (typically just the og:image thumbnail)
        """
        image_urls: list[str] = []
        
        # Try og:image meta tag
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            image_url = og_image["content"]
            if image_url and image_url.startswith("http"):
                image_urls.append(image_url)
        
        return image_urls
