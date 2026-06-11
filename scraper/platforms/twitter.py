"""Twitter / X adapter (Apify actor ``apidojo/twitter-scraper-lite``).

Seed convention:
  - a full Twitter/X URL -> ``startUrls``
  - ``@handle``          -> ``twitterHandles``
  - anything else        -> Twitter advanced search query in ``searchTerms``

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
class TwitterScraper(PlatformScraper):
    platform = Platform.twitter
    actor_id = get_settings().twitter_actor_id
    enabled = True

    def build_input(self, campaign: Campaign) -> dict[str, Any]:
        settings = get_settings()
        start_urls: list[str] = []
        handles: list[str] = []
        search_terms: list[str] = []

        for seed in campaign.seeds:
            s = seed.strip()
            if not s:
                continue
            if s.startswith("http://") or s.startswith("https://"):
                start_urls.append(s)
            elif s.startswith("@"):
                handles.append(s.lstrip("@"))
            else:
                search_terms.append(s)

        run_input: dict[str, Any] = {
            "maxItems": settings.results_limit_per_run,
            "sort": "Latest",
            "includeSearchTerms": True,
        }
        if start_urls:
            run_input["startUrls"] = start_urls
        if handles:
            run_input["twitterHandles"] = handles
        if search_terms:
            run_input["searchTerms"] = search_terms
        return run_input

    def normalize(
        self, raw_item: dict[str, Any], campaign: Campaign
    ) -> NormalizedPost | None:
        post_id = as_str(first(raw_item, "id", "tweetId", "conversationId"))
        if not post_id:
            return None

        author = raw_item.get("author") or raw_item.get("user") or {}
        if isinstance(author, str):
            author = {"userName": author}

        text = as_str(first(raw_item, "text", "fullText", "content"))
        media = raw_item.get("media") or raw_item.get("extendedEntities", {}).get("media") or []
        if not isinstance(media, list):
            media = []

        video_url = _first_media_url(media, "video")
        image_url = _first_media_url(media, "image") or _first_media_url(media, "photo")
        has_video = bool(video_url) or _has_media_type(media, "video")

        if has_video:
            media_type = "video"
        elif image_url:
            media_type = "image"
        else:
            media_type = "text"

        handle = as_str(first(author, "userName", "username", "screenName", "handle"))

        return NormalizedPost(
            platform=Platform.twitter,
            platform_post_id=post_id,
            url=as_str(first(raw_item, "url", "twitterUrl"))
            or (f"https://x.com/{handle}/status/{post_id}" if handle else None),
            author_handle=handle,
            author_id=as_str(first(author, "id", "userId", "restId")),
            author_url=as_str(first(author, "url", "twitterUrl"))
            or (f"https://x.com/{handle}" if handle else None),
            content_text=text,
            lang=as_str(first(raw_item, "lang", "language")),
            posted_at=parse_datetime(first(raw_item, "createdAt", "created_at", "date")),
            like_count=as_int(first(raw_item, "likeCount", "favoriteCount", "likes")),
            comment_count=as_int(first(raw_item, "replyCount", "replies")),
            share_count=as_int(first(raw_item, "retweetCount", "quoteCount", "shares")),
            view_count=as_int(first(raw_item, "viewCount", "views")),
            media_type=media_type,
            has_video=has_video,
            video_url=video_url,
            thumbnail_url=image_url,
            hashtags=extract_hashtags(text, raw_item.get("hashtags")),
            mentions=extract_mentions(text, raw_item.get("mentions")),
            country=campaign.country,
            topic=campaign.topic,
            campaign_id=campaign.id,
            raw=raw_item,
        )


def _has_media_type(media: list[Any], expected: str) -> bool:
    expected = expected.lower()
    for item in media:
        if not isinstance(item, dict):
            continue
        media_type = as_str(first(item, "type", "mediaType")) or ""
        if expected in media_type.lower():
            return True
    return False


def _first_media_url(media: list[Any], expected: str) -> str | None:
    expected = expected.lower()
    for item in media:
        if not isinstance(item, dict):
            continue
        media_type = as_str(first(item, "type", "mediaType")) or ""
        if expected not in media_type.lower():
            continue

        variants = item.get("variants") or item.get("videoVariants") or []
        if isinstance(variants, list):
            for variant in variants:
                if isinstance(variant, dict):
                    url = as_str(first(variant, "url", "src"))
                    if url:
                        return url

        url = as_str(
            first(
                item,
                "url",
                "mediaUrl",
                "media_url",
                "media_url_https",
                "preview_image_url",
            )
        )
        if url:
            return url
    return None
