"""Instagram adapter (Apify actor ``apify/instagram-scraper``).

Seed convention:
  - a full ``https://...instagram.com/...`` URL -> ``directUrls``
  - ``#tag`` or a bare word                     -> hashtag search

NOTE: Apify actor input schemas drift. Confirm exact keys against the actor's
page in the Apify console before relying on a new field.
"""

from __future__ import annotations

from typing import Any

from scraper.config import get_settings
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


@register
class InstagramScraper(PlatformScraper):
    platform = Platform.instagram
    actor_id = get_settings().instagram_actor_id
    enabled = True

    def build_input(self, campaign: Campaign) -> dict[str, Any]:
        settings = get_settings()
        direct_urls: list[str] = []
        hashtags: list[str] = []
        for seed in campaign.seeds:
            s = seed.strip()
            if not s:
                continue
            if s.startswith("http://") or s.startswith("https://"):
                direct_urls.append(s)
            else:
                hashtags.append(s.lstrip("#"))

        run_input: dict[str, Any] = {
            "resultsType": "posts",
            "resultsLimit": settings.results_limit_per_run,
        }
        if direct_urls:
            run_input["directUrls"] = direct_urls
        if hashtags:
            # `search` + `searchType: "hashtag"` drives hashtag discovery.
            run_input["search"] = " ".join(hashtags)
            run_input["searchType"] = "hashtag"
            run_input["searchLimit"] = len(hashtags)
        return run_input

    def normalize(
        self, raw_item: dict[str, Any], campaign: Campaign
    ) -> NormalizedPost | None:
        post_id = as_str(first(raw_item, "id", "shortCode", "shortcode"))
        if not post_id:
            return None

        short_code = as_str(first(raw_item, "shortCode", "shortcode"))
        text = as_str(first(raw_item, "caption", "text"))
        product_type = as_str(first(raw_item, "type", "productType")) or ""
        is_video = bool(
            raw_item.get("isVideo")
            or "video" in product_type.lower()
            or raw_item.get("videoUrl")
        )
        children = raw_item.get("childPosts") or raw_item.get("sidecar") or []
        is_carousel = bool(children) or "sidecar" in product_type.lower()

        if is_carousel:
            media_type = "carousel"
        elif is_video:
            media_type = "video"
        else:
            media_type = "image"

        handle = as_str(first(raw_item, "ownerUsername", "username"))

        return NormalizedPost(
            platform=Platform.instagram,
            platform_post_id=post_id,
            url=as_str(raw_item.get("url"))
            or (f"https://www.instagram.com/p/{short_code}/" if short_code else None),
            author_handle=handle,
            author_id=as_str(first(raw_item, "ownerId", "ownerFbid")),
            author_url=f"https://www.instagram.com/{handle}/" if handle else None,
            content_text=text,
            lang=None,
            posted_at=parse_datetime(first(raw_item, "timestamp", "taken_at")),
            like_count=as_int(first(raw_item, "likesCount", "likeCount")),
            comment_count=as_int(first(raw_item, "commentsCount", "commentCount")),
            share_count=None,
            view_count=as_int(first(raw_item, "videoViewCount", "videoPlayCount")),
            media_type=media_type,
            has_video=is_video,
            video_url=as_str(raw_item.get("videoUrl")),
            thumbnail_url=as_str(first(raw_item, "displayUrl", "thumbnailUrl")),
            hashtags=extract_hashtags(text, raw_item.get("hashtags")),
            mentions=extract_mentions(text, raw_item.get("mentions")),
            country=campaign.country,
            topic=campaign.topic,
            campaign_id=campaign.id,
            raw=raw_item,
        )
