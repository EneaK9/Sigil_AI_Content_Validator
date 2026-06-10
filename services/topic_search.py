"""
Topic search service.

Finds posts about a topic across platforms. Reddit is the only platform with
a free, unauthenticated search API, so it is the live source; other platforms
are reported as not live until search adapters/credentials exist for them.

Reddit aggressively rate-limits its .json endpoints by IP, so we try the JSON
search first (richer data: scores, comment counts) and fall back to the RSS
feed (still live, but without engagement numbers) when JSON is blocked.
"""
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from config import REDDIT_USER_AGENT

logger = logging.getLogger("policyguard.services.topic_search")

REDDIT_SEARCH_JSON_URL = "https://www.reddit.com/search.json"
REDDIT_SEARCH_RSS_URL = "https://www.reddit.com/search.rss"
ATOM_NS = "{http://www.w3.org/2005/Atom}"


@dataclass
class TopicPost:
    """A post found by topic search, platform-agnostic."""
    id: str
    platform: str
    url: str
    author: str
    title: str
    text: str
    created_utc: float
    score: int = 0
    num_comments: int = 0
    subreddit: str = ""
    subreddit_subscribers: int = 0
    extra: dict = field(default_factory=dict)


def _reddit_time_filter(days: int) -> str:
    """Map a day count onto Reddit's search `t` parameter."""
    if days <= 1:
        return "day"
    if days <= 7:
        return "week"
    if days <= 31:
        return "month"
    if days <= 365:
        return "year"
    return "all"


def search_reddit(query: str, days: int = 30, limit: int = 50) -> list[TopicPost]:
    """
    Search Reddit for posts about a topic.

    Tries the public .json endpoint first (full engagement data); when Reddit
    blocks it (403 by IP), falls back to the RSS feed.

    Args:
        query: Topic to search for
        days: Lookback window in days
        limit: Max number of posts to return (Reddit caps at 100)

    Returns:
        List of TopicPost sorted by Reddit's "top" relevance
    """
    posts = _search_reddit_json(query, days, limit)
    if posts:
        return posts
    logger.info("Falling back to Reddit RSS search")
    return _search_reddit_rss(query, days, limit)


def _search_reddit_json(query: str, days: int, limit: int) -> list[TopicPost]:
    """Search via the .json endpoint. Returns [] when blocked or empty."""
    params = {
        "q": query,
        "sort": "top",
        "t": _reddit_time_filter(days),
        "limit": min(limit, 100),
        "type": "link",
    }
    headers = {"User-Agent": REDDIT_USER_AGENT}

    try:
        response = requests.get(
            REDDIT_SEARCH_JSON_URL, params=params, headers=headers, timeout=15
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning(f"Reddit JSON search failed: {e}")
        return []

    posts: list[TopicPost] = []
    for child in data.get("data", {}).get("children", []):
        p = child.get("data", {})
        author = p.get("author") or ""
        title = p.get("title") or ""
        selftext = (p.get("selftext") or "").strip()
        text = f"{title}\n\n{selftext}" if selftext else title
        if not text:
            continue

        posts.append(TopicPost(
            id=p.get("name") or p.get("id", ""),
            platform="reddit",
            url=f"https://www.reddit.com{p.get('permalink', '')}",
            author=f"u/{author}" if author else "unknown",
            title=title,
            text=text,
            created_utc=float(p.get("created_utc") or 0),
            score=int(p.get("score") or 0),
            num_comments=int(p.get("num_comments") or 0),
            subreddit=p.get("subreddit") or "",
            subreddit_subscribers=int(p.get("subreddit_subscribers") or 0),
        ))

    logger.info(f"Reddit JSON search '{query}' ({params['t']}): {len(posts)} posts")
    return posts


def _search_reddit_rss(query: str, days: int, limit: int) -> list[TopicPost]:
    """
    Search via the RSS (Atom) feed. Live titles/snippets/authors, but no
    scores or comment counts (engagement stays empty for these posts).
    """
    params = {
        "q": query,
        "sort": "top",
        "t": _reddit_time_filter(days),
        "limit": min(limit, 100),
        "type": "link",  # posts only - excludes subreddit/community results
    }
    # RSS responds to browser-like UAs even when .json endpoints are blocked.
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(
            REDDIT_SEARCH_RSS_URL, params=params, headers=headers, timeout=15
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except (requests.RequestException, ET.ParseError) as e:
        logger.warning(f"Reddit RSS search failed: {e}")
        return []

    posts: list[TopicPost] = []
    for entry in root.findall(f"{ATOM_NS}entry")[:limit]:
        title = (entry.findtext(f"{ATOM_NS}title") or "").strip()
        if not title:
            continue

        author_el = entry.find(f"{ATOM_NS}author/{ATOM_NS}name")
        author = (author_el.text or "").strip() if author_el is not None else ""

        link_el = entry.find(f"{ATOM_NS}link")
        url = link_el.get("href", "") if link_el is not None else ""

        category_el = entry.find(f"{ATOM_NS}category")
        subreddit = (category_el.get("label", "") if category_el is not None else "").removeprefix("r/")

        published = (
            entry.findtext(f"{ATOM_NS}published")
            or entry.findtext(f"{ATOM_NS}updated")
            or ""
        )
        created_utc = 0.0
        if published:
            try:
                created_utc = datetime.fromisoformat(
                    published.replace("Z", "+00:00")
                ).astimezone(timezone.utc).timestamp()
            except ValueError:
                pass

        # Entry content is HTML; extract readable text for the snippet/judging.
        content_html = entry.findtext(f"{ATOM_NS}content") or ""
        content_text = BeautifulSoup(content_html, "html.parser").get_text(" ", strip=True)
        # Strip the boilerplate "submitted by ... [link] [comments]" suffix.
        for marker in ("submitted by", "[link]"):
            idx = content_text.find(marker)
            if idx > 0:
                content_text = content_text[:idx].strip()
        text = f"{title}\n\n{content_text}" if content_text else title

        posts.append(TopicPost(
            id=entry.findtext(f"{ATOM_NS}id") or url,
            platform="reddit",
            url=url,
            author=author or "unknown",
            title=title,
            text=text,
            created_utc=created_utc,
            subreddit=subreddit,
            extra={"source": "rss"},
        ))

    logger.info(f"Reddit RSS search '{query}' ({params['t']}): {len(posts)} posts")
    return posts
