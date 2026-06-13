"""Reddit adapter (Apify actor ``xBj1aoFdikikCx40j``).

This actor searches Reddit posts and can optionally crawl comments/users.
For this pipeline we scrape posts only, using the user's provided actor input
shape and normalizing posts into the shared ``NormalizedPost`` model.
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
class RedditScraper(PlatformScraper):
    platform = Platform.reddit
    actor_id = get_settings().reddit_actor_id
    enabled = True

    def build_input(self, campaign: Campaign) -> dict[str, Any]:
        settings = get_settings()
        search_terms = [seed.strip() for seed in campaign.seeds if seed.strip()]
        max_items = min(settings.results_limit_per_run, 1000)

        return {
            "crawlComments": False,
            "includeNsfw": True,
            "maxPosts": max_items,
            "maxUsers": 100,
            "searchTerms": search_terms or [
                "rama, protests, kushner, trump, israel, albania"
            ],
            "searchTypes": ["posts"],
            "startUrls": [{"url": "https://www.reddit.com/r/albania/"}],
            "searchSort": "new",
            "timeFilter": "all",
            "postSort": "hot",
            "maxItems": max_items,
            "maxComments": 100,
            "maxCommentsPerPost": 20,
            "maxCommunities": 10,
            "pages": 1,
        }

    def normalize(
        self, raw_item: dict[str, Any], campaign: Campaign
    ) -> NormalizedPost | None:
        post_id = as_str(
            first(raw_item, "id", "postId", "post_id", "name", "fullname")
        )
        url = as_str(first(raw_item, "url", "permalink", "postUrl", "link"))
        if not post_id and url:
            post_id = url.rstrip("/").split("/")[-1]
        if not post_id:
            return None

        title = as_str(first(raw_item, "title", "postTitle")) or ""
        body = as_str(
            first(raw_item, "body", "selftext", "text", "content", "postText")
        ) or ""
        text = "\n\n".join(part for part in [title, body] if part)

        author = raw_item.get("author") or raw_item.get("user") or {}
        if isinstance(author, str):
            author = {"username": author}

        subreddit = as_str(first(raw_item, "subreddit", "communityName", "community"))
        if url and url.startswith("/"):
            url = f"https://www.reddit.com{url}"

        media_type = "text"
        video_url = as_str(first(raw_item, "videoUrl", "video_url", "mediaUrl"))
        thumbnail_url = as_str(first(raw_item, "thumbnail", "thumbnailUrl", "imageUrl"))
        if video_url:
            media_type = "video"
        elif thumbnail_url:
            media_type = "image"

        return NormalizedPost(
            platform=Platform.reddit,
            platform_post_id=post_id,
            url=url,
            author_handle=as_str(first(author, "username", "name", "author")),
            author_id=as_str(first(author, "id", "userId")),
            author_url=as_str(first(author, "url", "profileUrl")),
            content_text=text,
            lang=None,
            posted_at=parse_datetime(
                first(raw_item, "createdAt", "created_utc", "created", "date")
            ),
            like_count=as_int(first(raw_item, "score", "upvotes", "upvoteCount")),
            comment_count=as_int(
                first(raw_item, "numComments", "comments", "commentCount")
            ),
            share_count=None,
            view_count=as_int(first(raw_item, "viewCount", "views")),
            media_type=media_type,
            has_video=bool(video_url),
            video_url=video_url,
            thumbnail_url=thumbnail_url,
            hashtags=extract_hashtags(text, raw_item.get("hashtags")),
            mentions=extract_mentions(text, raw_item.get("mentions")),
            country=campaign.country,
            topic=campaign.topic,
            campaign_id=campaign.id,
            raw={**raw_item, "subreddit": subreddit},
        )
