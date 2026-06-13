"""LinkedIn adapter (Apify actor ``buIWk2uOUzTmcLsuB``).

This adapter scrapes LinkedIn posts by keyword search.
Seeds are combined into search queries.

NOTE: Apify actor input schemas drift. Confirm exact keys against the actor's
page in the Apify console before relying on a new field.
"""

from __future__ import annotations

from typing import Any

from scraper.config import get_settings
from scraper.logging_setup import get_logger
from scraper.models import Campaign, NormalizedPost, Platform
from scraper.platforms._util import (
    as_int,
    as_str,
    extract_hashtags,
    extract_mentions,
    first,
    parse_datetime,
)
from scraper.platforms.base import PlatformScraper, register

log = get_logger(__name__)


@register
class LinkedInScraper(PlatformScraper):
    platform = Platform.linkedin
    actor_id = get_settings().linkedin_actor_id
    enabled = True

    def build_input(self, campaign: Campaign) -> dict[str, Any]:
        settings = get_settings()
        
        keywords: list[str] = []
        for seed in campaign.seeds:
            s = seed.strip()
            if not s:
                continue
            if not (s.startswith("http://") or s.startswith("https://")):
                keywords.append(s)
        
        run_input: dict[str, Any] = {
            "searchQueries": keywords if keywords else ["Albania Kushner protest"],
            "maxResults": min(settings.results_limit_per_run, 1000),
            "proxyConfiguration": {"useApifyProxy": True},
        }
        
        return run_input

    def normalize(
        self, raw_item: dict[str, Any], campaign: Campaign
    ) -> NormalizedPost | None:
        post_id = as_str(first(raw_item, "postId", "id", "urn", "post_id"))
        if not post_id:
            return None

        text = as_str(first(raw_item, "text", "commentary", "content", "postText"))
        video_url = as_str(first(raw_item, "videoUrl", "video_url"))
        has_video = bool(video_url) or as_str(raw_item.get("type")) == "video"

        author = raw_item.get("author") or raw_item.get("user") or {}
        if isinstance(author, str):
            author = {"name": author}

        return NormalizedPost(
            platform=Platform.linkedin,
            platform_post_id=post_id,
            url=as_str(first(raw_item, "url", "postUrl", "shareUrl")),
            author_handle=as_str(first(author, "name", "firstName", "username")),
            author_id=as_str(first(author, "id", "urn", "profileUrn")),
            author_url=as_str(first(author, "profileUrl", "url", "linkedInUrl")),
            content_text=text,
            lang=as_str(raw_item.get("language")),
            posted_at=parse_datetime(first(raw_item, "postedAt", "publishedAt", "date", "time")),
            like_count=as_int(first(raw_item, "likes", "likeCount", "numLikes", "socialCounts.numLikes")),
            comment_count=as_int(first(raw_item, "comments", "commentCount", "numComments", "socialCounts.numComments")),
            share_count=as_int(first(raw_item, "shares", "shareCount", "numShares", "socialCounts.numShares")),
            view_count=as_int(first(raw_item, "views", "viewCount", "numViews")),
            media_type="video" if has_video else "text",
            has_video=has_video,
            video_url=video_url,
            thumbnail_url=as_str(first(raw_item, "thumbnailUrl", "imageUrl", "image")),
            hashtags=extract_hashtags(text, raw_item.get("hashtags")),
            mentions=extract_mentions(text, raw_item.get("mentions")),
            country=campaign.country,
            topic=campaign.topic,
            campaign_id=campaign.id,
            raw=raw_item,
        )
