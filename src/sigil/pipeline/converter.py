"""Convert between scraper and validator data models.

The scraper produces `NormalizedPost` objects stored in Supabase.
The validator expects `PostData` objects for policy compliance analysis.
This module bridges the two systems.
"""

from __future__ import annotations

from typing import Any

from sigil.validation.models import PostData
from sigil.scraper.models import Platform

# The scraper/DB platform enum (``platform_t``) uses ``twitter`` while the
# validator + policy files use ``x``. This is the single translation point
# between the two vocabularies.
_DB_TO_VALIDATOR_PLATFORM = {"twitter": "x"}


def validator_platform(db_platform: str) -> str:
    """Map a DB/scraper platform value onto the validator's platform vocabulary."""
    return _DB_TO_VALIDATOR_PLATFORM.get(db_platform, db_platform)


def db_row_to_post_data(row: dict[str, Any]) -> PostData:
    """Convert a raw database row to PostData for the validator.
    
    Args:
        row: Dict-like row from the posts table
        
    Returns:
        PostData object ready for the judge
    """
    image_urls: list[str] = []
    if row.get("thumbnail_url"):
        image_urls.append(row["thumbnail_url"])
    
    video_urls: list[str] = []
    if row.get("video_url"):
        video_urls.append(row["video_url"])
    
    platform = row["platform"]
    url = row.get("url")
    if not url:
        url = _build_fallback_url(Platform(platform), row["platform_post_id"])
    
    return PostData(
        url=url,
        platform=validator_platform(platform),
        text=row.get("content_text") or "",
        author=row.get("author_handle") or "",
        title="",
        image_urls=image_urls,
        video_urls=video_urls,
    )


def _build_fallback_url(platform: Platform, post_id: str) -> str:
    """Build a fallback URL when the original URL is missing."""
    url_templates = {
        Platform.tiktok: f"https://www.tiktok.com/@unknown/video/{post_id}",
        Platform.instagram: f"https://www.instagram.com/p/{post_id}/",
        Platform.facebook: f"https://www.facebook.com/{post_id}",
        Platform.twitter: f"https://x.com/i/status/{post_id}",
        Platform.linkedin: f"https://www.linkedin.com/feed/update/{post_id}",
    }
    return url_templates.get(platform, f"https://{platform.value}.com/p/{post_id}")
