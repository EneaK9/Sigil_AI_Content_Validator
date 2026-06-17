"""Relevance and deduplication helpers for client/topic scrapes."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from scraper.relevance_profiles import profile_for

DEFAULT_CLIENT = "sigil"
DEFAULT_TOPIC = "albania_political"


def post_relevance_tier(post: dict, *, client: str | None = None, topic: str | None = None) -> str:
    """Classify whether a post is relevant to the given client/topic."""
    resolved_client = (client or post.get("client") or DEFAULT_CLIENT)
    resolved_topic = (topic or post.get("topic") or DEFAULT_TOPIC)
    text = _searchable_text(post)
    profile = profile_for(str(resolved_client), str(resolved_topic))
    if profile is None:
        # If we don't have a profile, do not filter anything out.
        return "unknown_profile"
    return "relevant" if profile.is_relevant(text) else "not_relevant"


def is_relevant_post(post: dict, *, client: str | None = None, topic: str | None = None) -> bool:
    """Return True if the post should be kept for this client/topic."""
    return post_relevance_tier(post, client=client, topic=topic) != "not_relevant"


def dedupe_key(post: dict) -> str:
    """Build a stable dedupe key from platform + native ID, falling back to URL."""
    platform = str(post.get("platform") or "").lower()
    post_id = str(post.get("platform_post_id") or "").strip()
    if platform and post_id:
        return f"{platform}:id:{post_id}"

    url = _normalize_url(str(post.get("url") or ""))
    if platform and url:
        return f"{platform}:url:{url}"
    return f"{platform}:unknown:{hash(_searchable_text(post))}"


def filter_and_dedupe_posts(
    posts: list[dict],
    *,
    client: str | None = None,
    topic: str | None = None,
) -> tuple[list[dict], dict[str, int]]:
    """Remove irrelevant and duplicate posts, returning kept posts and stats."""
    kept: list[dict] = []
    seen: set[str] = set()
    stats = {
        "input_count": len(posts),
        "irrelevant_count": 0,
        "duplicate_count": 0,
        "kept_count": 0,
    }

    for post in posts:
        tier = post_relevance_tier(post, client=client, topic=topic)
        post["relevance_tier"] = tier
        if tier == "not_relevant":
            stats["irrelevant_count"] += 1
            continue

        key = dedupe_key(post)
        if key in seen:
            stats["duplicate_count"] += 1
            continue
        seen.add(key)
        kept.append(post)

    stats["kept_count"] = len(kept)
    return kept, stats


def _searchable_text(post: dict) -> str:
    values = [
        post.get("content_text"),
        post.get("url"),
        post.get("author_handle"),
        " ".join(post.get("hashtags") or []),
    ]
    return " ".join(str(value) for value in values if value).lower()


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))
