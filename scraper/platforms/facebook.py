"""Facebook adapter (Apify actor ``scrapio/facebook-posts-search-scraper``).

This adapter uses a SEARCH-based scraper that finds Facebook posts by keyword.
Seeds can be:
  - Search keywords (e.g. "football", "Edi Rama")
  - Full search URLs (e.g. "https://www.facebook.com/search/top/?q=football")

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
class FacebookScraper(PlatformScraper):
    platform = Platform.facebook
    actor_id = get_settings().facebook_actor_id
    enabled = True

    def build_input(self, campaign: Campaign) -> dict[str, Any]:
        settings = get_settings()
        
        search_queries: list[str] = []
        start_urls: list[str] = []
        
        for seed in campaign.seeds:
            s = seed.strip()
            if not s:
                continue
            if s.startswith("http://") or s.startswith("https://"):
                start_urls.append(s)
            else:
                search_queries.append(s)
        
        run_input: dict[str, Any] = {
            "maxPosts": min(settings.results_limit_per_run, 500),
            "proxyConfiguration": {"useApifyProxy": True},
        }
        
        if start_urls:
            run_input["startUrls"] = start_urls
        if search_queries:
            run_input["searchQueries"] = search_queries
        
        return run_input

    def normalize(
        self, raw_item: dict[str, Any], campaign: Campaign
    ) -> NormalizedPost | None:
        post_id = as_str(first(raw_item, "postId", "id", "post_id"))
        if not post_id:
            return None

        text = as_str(first(raw_item, "text", "message", "postText"))
        video_url = as_str(first(raw_item, "videoUrl", "video_url"))
        has_video = bool(video_url) or as_str(raw_item.get("type")) == "Video"

        user = raw_item.get("user") or raw_item.get("author") or {}
        if isinstance(user, str):
            user = {"name": user}

        return NormalizedPost(
            platform=Platform.facebook,
            platform_post_id=post_id,
            url=as_str(first(raw_item, "url", "postUrl", "topLevelUrl")),
            author_handle=as_str(first(user, "name", "username")),
            author_id=as_str(first(user, "id", "userId")),
            author_url=as_str(first(user, "profileUrl", "url")),
            content_text=text,
            lang=None,
            posted_at=parse_datetime(first(raw_item, "time", "date", "publishedAt")),
            like_count=as_int(first(raw_item, "likes", "likesCount", "reactionsCount")),
            comment_count=as_int(first(raw_item, "comments", "commentsCount")),
            share_count=as_int(first(raw_item, "shares", "sharesCount")),
            view_count=as_int(first(raw_item, "viewsCount", "videoViewCount")),
            media_type="video" if has_video else "text",
            has_video=has_video,
            video_url=video_url,
            thumbnail_url=as_str(first(raw_item, "thumbnailUrl", "thumbUrl")),
            hashtags=extract_hashtags(text, raw_item.get("hashtags")),
            mentions=extract_mentions(text, raw_item.get("mentions")),
            country=campaign.country,
            topic=campaign.topic,
            campaign_id=campaign.id,
            raw=raw_item,
        )
