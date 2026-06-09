"""TikTok adapter (Apify actor ``clockworks/tiktok-scraper``).

Seed convention (a campaign's ``seeds`` is a flat list of strings):
  - ``#tag``      -> hashtag
  - ``@handle``   -> profile
  - anything else -> free-text search query

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
class TikTokScraper(PlatformScraper):
    platform = Platform.tiktok
    actor_id = get_settings().tiktok_actor_id
    enabled = True

    def build_input(self, campaign: Campaign) -> dict[str, Any]:
        settings = get_settings()
        hashtags: list[str] = []
        profiles: list[str] = []
        queries: list[str] = []
        for seed in campaign.seeds:
            s = seed.strip()
            if not s:
                continue
            if s.startswith("#"):
                hashtags.append(s.lstrip("#"))
            elif s.startswith("@"):
                profiles.append(s.lstrip("@"))
            else:
                queries.append(s)

        run_input: dict[str, Any] = {
            "resultsPerPage": settings.results_limit_per_run,
            # `maxItems`/`resultsLimit` are both honored across actor versions.
            "maxItems": settings.results_limit_per_run,
            "resultsLimit": settings.results_limit_per_run,
            # We only want URLs + metadata, never downloaded media files.
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
            "shouldDownloadSubtitles": False,
            "shouldDownloadSlideshowImages": False,
        }
        if hashtags:
            run_input["hashtags"] = hashtags
        if profiles:
            run_input["profiles"] = profiles
        if queries:
            run_input["searchQueries"] = queries
        return run_input

    def normalize(
        self, raw_item: dict[str, Any], campaign: Campaign
    ) -> NormalizedPost | None:
        post_id = as_str(first(raw_item, "id", "videoId", "itemId"))
        if not post_id:
            return None  # not a post item (e.g. summary/junk row)

        author = raw_item.get("authorMeta") or raw_item.get("author") or {}
        if isinstance(author, str):
            author = {"name": author}

        text = as_str(first(raw_item, "text", "desc", "description"))
        web_url = as_str(first(raw_item, "webVideoUrl", "url", "shareUrl"))
        video_url = as_str(
            first(raw_item, "videoUrl", "downloadAddr", "playAddr")
        ) or _nested(raw_item, "videoMeta", "downloadAddr")

        handle = as_str(first(author, "name", "uniqueId", "nickName"))
        author_id = as_str(first(author, "id", "userId", "secUid"))

        return NormalizedPost(
            platform=Platform.tiktok,
            platform_post_id=post_id,
            url=web_url,
            author_handle=handle,
            author_id=author_id,
            author_url=as_str(author.get("profileUrl"))
            or (f"https://www.tiktok.com/@{handle}" if handle else None),
            content_text=text,
            lang=as_str(first(raw_item, "language", "lang")),
            posted_at=parse_datetime(
                first(raw_item, "createTimeISO", "createTime", "createdAt")
            ),
            like_count=as_int(first(raw_item, "diggCount", "likesCount", "likeCount")),
            comment_count=as_int(first(raw_item, "commentCount", "commentsCount")),
            share_count=as_int(first(raw_item, "shareCount", "sharesCount")),
            view_count=as_int(first(raw_item, "playCount", "viewCount", "playsCount")),
            media_type="video",
            has_video=True,
            video_url=video_url,
            thumbnail_url=_nested(raw_item, "videoMeta", "coverUrl")
            or as_str(first(raw_item, "covers", "thumbnail")),
            hashtags=extract_hashtags(text, raw_item.get("hashtags")),
            mentions=extract_mentions(text, raw_item.get("mentions")),
            country=campaign.country,
            topic=campaign.topic,
            campaign_id=campaign.id,
            raw=raw_item,
        )


def _nested(item: dict[str, Any], *path: str) -> str | None:
    cur: Any = item
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return as_str(cur)
