"""Relevance and deduplication helpers for Albania/Kushner/Trump scrapes."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

ALBANIA_RE = re.compile(
    r"\b(albania|albanian|shqip(?:e|eria|ëria)?|tirana|tiran[ëe]|"
    r"vlora|vlor[ëe]|sazan|dh[ëe]rmi|rama|edirama)\b",
    re.IGNORECASE,
)
TRUMP_FAMILY_RE = re.compile(r"\b(trump|kushner|ivanka|jared)\b", re.IGNORECASE)
STORY_RE = re.compile(
    r"\b(protest\w*|demonstrat\w*|resort|island|sazan|vlora|vlor[ëe]|"
    r"development|project|invest\w*|billion|construction|bulldozer\w*|"
    r"protected|park)\b",
    re.IGNORECASE,
)


def post_relevance_tier(post: dict) -> str:
    """Classify whether a post is relevant to the Albania/Trump-family story."""
    text = _searchable_text(post)
    has_albania = bool(ALBANIA_RE.search(text))
    has_trump_family = bool(TRUMP_FAMILY_RE.search(text))
    has_story = bool(STORY_RE.search(text))

    if has_albania and has_trump_family and has_story:
        return "core_story"
    if has_albania and has_trump_family:
        return "broader_albania_trump_kushner"
    return "not_relevant"


def is_relevant_post(post: dict) -> bool:
    """Return True if the post should be kept for this specific investigation."""
    return post_relevance_tier(post) != "not_relevant"


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


def filter_and_dedupe_posts(posts: list[dict]) -> tuple[list[dict], dict[str, int]]:
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
        tier = post_relevance_tier(post)
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
