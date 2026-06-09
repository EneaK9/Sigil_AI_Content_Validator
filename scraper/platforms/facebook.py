"""Facebook adapter (Apify actor ``apify/facebook-posts-scraper``).

IMPORTANT: Facebook keyword search via Apify is weak/unreliable. This actor
scrapes posts from specific *page URLs*, so campaigns must supply page URLs as
their ``seeds`` (e.g. ``https://www.facebook.com/somepage``). Non-URL seeds are
ignored with a warning rather than silently mishandled.

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
        # FB keyword search is weak -> seeds MUST be page URLs.
        start_urls: list[dict[str, str]] = []
        for seed in campaign.seeds:
            s = seed.strip()
            if s.startswith("http://") or s.startswith("https://"):
                start_urls.append({"url": s})
            else:
                log.warning(
                    "facebook_non_url_seed_ignored",
                    campaign_id=str(campaign.id),
                    seed=s,
                )
        run_input: dict[str, Any] = {
            "startUrls": start_urls,
            "resultsLimit": settings.results_limit_per_run,
        }
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
