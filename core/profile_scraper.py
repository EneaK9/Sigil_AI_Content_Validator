"""
Profile scraping module for bot detection.

Fetches account metadata from social media profile URLs.
"""
import os
import re
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from config import SCRAPER_USER_AGENT, REDDIT_USER_AGENT
from core.models import ScrapingError

logger = logging.getLogger("policyguard.profile_scraper")


def detect_platform_from_url(url: str) -> str:
    """
    Detect which platform a URL belongs to.
    
    Args:
        url: Profile URL
        
    Returns:
        Platform name (x, reddit, tiktok, instagram, facebook)
        
    Raises:
        ScrapingError: If platform cannot be detected
    """
    url_lower = url.lower()
    
    if "tiktok.com" in url_lower:
        return "tiktok"
    elif "x.com" in url_lower or "twitter.com" in url_lower:
        return "x"
    elif "reddit.com" in url_lower:
        return "reddit"
    elif "instagram.com" in url_lower:
        return "instagram"
    elif "facebook.com" in url_lower or "fb.com" in url_lower:
        return "facebook"
    else:
        raise ScrapingError(f"Cannot detect platform from URL: {url}")


def scrape_profile(url: str) -> Dict[str, Any]:
    """
    Scrape profile data from a URL.
    
    Args:
        url: Profile URL
        
    Returns:
        Dictionary of account data suitable for bot detection
        
    Raises:
        ScrapingError: If profile cannot be scraped
    """
    platform = detect_platform_from_url(url)
    
    scrapers = {
        "tiktok": scrape_tiktok_profile,
        "x": scrape_x_profile,
        "reddit": scrape_reddit_profile,
        "instagram": scrape_instagram_profile,
        "facebook": scrape_facebook_profile,
    }
    
    scraper = scrapers.get(platform)
    if not scraper:
        raise ScrapingError(f"No profile scraper for platform: {platform}")
    
    logger.info(f"[PROFILE] Scraping {platform} profile: {url}")
    
    account_data = scraper(url)
    account_data["_scraped_from_url"] = url
    account_data["_scraped_at"] = datetime.now(timezone.utc).isoformat()
    
    return account_data


def _extract_username_from_url(url: str, platform: str) -> str:
    """Extract username from profile URL."""
    patterns = {
        "tiktok": r"tiktok\.com/@([^/?]+)",
        "x": r"(?:x\.com|twitter\.com)/([^/?]+)",
        "reddit": r"reddit\.com/(?:user|u)/([^/?]+)",
        "instagram": r"instagram\.com/([^/?]+)",
        "facebook": r"facebook\.com/(?:people/[^/]+/\d+|profile\.php\?id=\d+|([^/?]+))",
    }
    
    pattern = patterns.get(platform)
    if pattern:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1) or match.group(0).split("/")[-1]
    
    return "unknown"


# =============================================================================
# TikTok Profile Scraper
# =============================================================================

def scrape_tiktok_profile(url: str) -> Dict[str, Any]:
    """
    Scrape TikTok profile data.
    
    TikTok profiles show follower/following counts in meta tags and page content.
    """
    headers = {
        "User-Agent": SCRAPER_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
    except requests.RequestException as e:
        raise ScrapingError(f"Failed to fetch TikTok profile: {e}")
    
    if response.status_code != 200:
        raise ScrapingError(f"TikTok returned HTTP {response.status_code}")
    
    soup = BeautifulSoup(response.text, "html.parser")
    username = _extract_username_from_url(url, "tiktok")
    
    # Try to extract data from meta tags and scripts
    account_data = {
        "username": username,
        "follower_count": 0,
        "following_count": 0,
        "video_count": 0,
        "like_count": 0,
        "bio": "",
        "profile_image": "",
        "is_verified": False,
    }
    
    # Extract from og:description which often contains follower info
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        desc = og_desc["content"]
        
        # Parse patterns like "123.4K Followers, 50 Following, 10 Videos"
        followers_match = re.search(r"([\d.]+[KMB]?)\s*Followers", desc, re.IGNORECASE)
        following_match = re.search(r"([\d.]+[KMB]?)\s*Following", desc, re.IGNORECASE)
        likes_match = re.search(r"([\d.]+[KMB]?)\s*Likes", desc, re.IGNORECASE)
        
        if followers_match:
            account_data["follower_count"] = _parse_count(followers_match.group(1))
        if following_match:
            account_data["following_count"] = _parse_count(following_match.group(1))
        if likes_match:
            account_data["like_count"] = _parse_count(likes_match.group(1))
    
    # Extract bio from meta description
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        # Bio is often after the stats in the description
        content = meta_desc["content"]
        # Try to extract the actual bio text (after stats)
        bio_match = re.search(r"Videos?\.\s*(.+)", content)
        if bio_match:
            account_data["bio"] = bio_match.group(1).strip()
    
    # Extract profile image from og:image
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        account_data["profile_image"] = og_image["content"]
    
    # Check for verified badge in title
    title_tag = soup.find("title")
    if title_tag:
        title_text = title_tag.get_text()
        if "✓" in title_text or "verified" in title_text.lower():
            account_data["is_verified"] = True
    
    logger.info(f"[PROFILE] TikTok @{username}: {account_data['follower_count']} followers")
    
    return account_data


# =============================================================================
# X (Twitter) Profile Scraper
# =============================================================================

def scrape_x_profile(url: str) -> Dict[str, Any]:
    """
    Scrape X/Twitter profile data.
    
    Uses Twitter API v2 if X_BEARER_TOKEN is available.
    Falls back to meta tag scraping otherwise.
    """
    username = _extract_username_from_url(url, "x")
    bearer_token = os.environ.get("X_BEARER_TOKEN")
    
    if bearer_token:
        return _scrape_x_api(username, bearer_token)
    else:
        return _scrape_x_meta(url, username)


def _scrape_x_api(username: str, bearer_token: str) -> Dict[str, Any]:
    """Scrape X profile using API v2."""
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "User-Agent": "PolicyGuard/1.0"
    }
    
    params = {
        "user.fields": "created_at,description,public_metrics,profile_image_url,verified"
    }
    
    api_url = f"https://api.twitter.com/2/users/by/username/{username}"
    
    try:
        response = requests.get(api_url, headers=headers, params=params, timeout=10)
    except requests.RequestException as e:
        raise ScrapingError(f"Failed to fetch X profile: {e}")
    
    if response.status_code == 401:
        raise ScrapingError("X API unauthorized. Check X_BEARER_TOKEN.")
    
    if response.status_code == 404:
        raise ScrapingError(f"X user not found: @{username}")
    
    if response.status_code != 200:
        raise ScrapingError(f"X API returned HTTP {response.status_code}")
    
    data = response.json()
    
    if "data" not in data:
        raise ScrapingError(f"X user not found: @{username}")
    
    user = data["data"]
    metrics = user.get("public_metrics", {})
    
    account_data = {
        "username": username,
        "created_at": user.get("created_at"),
        "followers_count": metrics.get("followers_count", 0),
        "following_count": metrics.get("following_count", 0),
        "tweet_count": metrics.get("tweet_count", 0),
        "listed_count": metrics.get("listed_count", 0),
        "description": user.get("description", ""),
        "default_profile_image": "default_profile" in user.get("profile_image_url", ""),
        "is_verified": user.get("verified", False),
    }
    
    logger.info(f"[PROFILE] X @{username}: {account_data['followers_count']} followers")
    
    return account_data


def _scrape_x_meta(url: str, username: str) -> Dict[str, Any]:
    """Scrape X profile from meta tags (fallback when no API token)."""
    headers = {
        "User-Agent": SCRAPER_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
    except requests.RequestException as e:
        raise ScrapingError(f"Failed to fetch X profile: {e}")
    
    if response.status_code != 200:
        raise ScrapingError(f"X returned HTTP {response.status_code}")
    
    soup = BeautifulSoup(response.text, "html.parser")
    
    account_data = {
        "username": username,
        "followers_count": 0,
        "following_count": 0,
        "tweet_count": 0,
        "description": "",
        "default_profile_image": False,
    }
    
    # Extract from og:description
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        desc = og_desc["content"]
        
        followers_match = re.search(r"([\d,.]+)\s*Followers", desc, re.IGNORECASE)
        following_match = re.search(r"([\d,.]+)\s*Following", desc, re.IGNORECASE)
        
        if followers_match:
            account_data["followers_count"] = _parse_count(followers_match.group(1))
        if following_match:
            account_data["following_count"] = _parse_count(following_match.group(1))
    
    logger.info(f"[PROFILE] X @{username} (meta scrape): {account_data['followers_count']} followers")
    
    return account_data


# =============================================================================
# Reddit Profile Scraper
# =============================================================================

def scrape_reddit_profile(url: str) -> Dict[str, Any]:
    """
    Scrape Reddit user profile data.
    
    Uses Reddit's public .json endpoint for user about.
    """
    username = _extract_username_from_url(url, "reddit")
    
    # Build the about.json URL
    api_url = f"https://www.reddit.com/user/{username}/about.json"
    
    headers = {"User-Agent": REDDIT_USER_AGENT}
    
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
    except requests.RequestException as e:
        raise ScrapingError(f"Failed to fetch Reddit profile: {e}")
    
    if response.status_code == 404:
        raise ScrapingError(f"Reddit user not found: u/{username}")
    
    if response.status_code != 200:
        raise ScrapingError(f"Reddit returned HTTP {response.status_code}")
    
    data = response.json()
    user_data = data.get("data", {})
    
    account_data = {
        "username": username,
        "created_utc": user_data.get("created_utc"),
        "link_karma": user_data.get("link_karma", 0),
        "comment_karma": user_data.get("comment_karma", 0),
        "total_karma": user_data.get("total_karma", 0),
        "has_verified_email": user_data.get("has_verified_email", False),
        "is_gold": user_data.get("is_gold", False),
        "is_mod": user_data.get("is_mod", False),
        "icon_img": user_data.get("icon_img", ""),
        "subreddits_posted": [],  # Would need to fetch posts to get this
    }
    
    logger.info(f"[PROFILE] Reddit u/{username}: {account_data['total_karma']} karma")
    
    return account_data


# =============================================================================
# Instagram Profile Scraper
# =============================================================================

def scrape_instagram_profile(url: str) -> Dict[str, Any]:
    """
    Scrape Instagram profile data.
    
    Note: Instagram heavily restricts scraping. This uses meta tag extraction
    which may have limited data. For better results, use the JSON endpoint.
    """
    headers = {
        "User-Agent": SCRAPER_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
    except requests.RequestException as e:
        raise ScrapingError(f"Failed to fetch Instagram profile: {e}")
    
    if response.status_code != 200:
        raise ScrapingError(f"Instagram returned HTTP {response.status_code}")
    
    soup = BeautifulSoup(response.text, "html.parser")
    username = _extract_username_from_url(url, "instagram")
    
    account_data = {
        "username": username,
        "follower_count": 0,
        "following_count": 0,
        "media_count": 0,
        "biography": "",
        "profile_pic_url": "",
        "is_verified": False,
        "is_private": False,
    }
    
    # Extract from og:description
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        desc = og_desc["content"]
        
        # Parse patterns like "123K Followers, 50 Following, 100 Posts"
        followers_match = re.search(r"([\d,.]+[KMB]?)\s*Followers", desc, re.IGNORECASE)
        following_match = re.search(r"([\d,.]+[KMB]?)\s*Following", desc, re.IGNORECASE)
        posts_match = re.search(r"([\d,.]+[KMB]?)\s*Posts", desc, re.IGNORECASE)
        
        if followers_match:
            account_data["follower_count"] = _parse_count(followers_match.group(1))
        if following_match:
            account_data["following_count"] = _parse_count(following_match.group(1))
        if posts_match:
            account_data["media_count"] = _parse_count(posts_match.group(1))
        
        # Try to extract bio (usually at the end of description)
        bio_match = re.search(r"Posts?\s*[-–—]\s*(.+)", desc)
        if bio_match:
            account_data["biography"] = bio_match.group(1).strip()
    
    # Extract profile image
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        account_data["profile_pic_url"] = og_image["content"]
    
    logger.info(f"[PROFILE] Instagram @{username}: {account_data['follower_count']} followers")
    
    return account_data


# =============================================================================
# Facebook Profile Scraper
# =============================================================================

def scrape_facebook_profile(url: str) -> Dict[str, Any]:
    """
    Scrape Facebook profile/page data.
    
    Note: Facebook heavily restricts scraping. This provides minimal data
    from meta tags. For full data, use the JSON endpoint.
    """
    headers = {
        "User-Agent": SCRAPER_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
    except requests.RequestException as e:
        raise ScrapingError(f"Failed to fetch Facebook profile: {e}")
    
    if response.status_code != 200:
        raise ScrapingError(f"Facebook returned HTTP {response.status_code}")
    
    soup = BeautifulSoup(response.text, "html.parser")
    username = _extract_username_from_url(url, "facebook")
    
    account_data = {
        "name": username,
        "username": username,
        "follower_count": 0,
        "friend_count": 0,
        "is_page": False,
        "about": "",
    }
    
    # Try to get name from og:title
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        account_data["name"] = og_title["content"]
    
    # Extract from og:description
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        desc = og_desc["content"]
        
        followers_match = re.search(r"([\d,.]+[KMB]?)\s*(?:followers|likes)", desc, re.IGNORECASE)
        if followers_match:
            account_data["follower_count"] = _parse_count(followers_match.group(1))
        
        # Check if it's a page
        if "page" in desc.lower() or "likes" in desc.lower():
            account_data["is_page"] = True
    
    logger.info(f"[PROFILE] Facebook {account_data['name']}: {account_data['follower_count']} followers")
    
    return account_data


# =============================================================================
# Helper Functions
# =============================================================================

def _parse_count(count_str: str) -> int:
    """
    Parse count string like "1.2K", "500", "1,234" to integer.
    """
    if not count_str:
        return 0
    
    count_str = count_str.strip().replace(",", "")
    
    multipliers = {
        "K": 1_000,
        "M": 1_000_000,
        "B": 1_000_000_000,
    }
    
    for suffix, multiplier in multipliers.items():
        if suffix in count_str.upper():
            try:
                num = float(count_str.upper().replace(suffix, ""))
                return int(num * multiplier)
            except ValueError:
                return 0
    
    try:
        return int(float(count_str))
    except ValueError:
        return 0
