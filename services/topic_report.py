"""
Topic report assembly.

Turns topic-search results into the TopicReport shape the Sondë frontend
consumes (see frontend/types/index.ts). Policy flags are produced by running
the existing CheckerService (Claude judge) over the top posts; sentiment is
estimated with a single Claude call. Both degrade gracefully when
ANTHROPIC_API_KEY is missing so the endpoint always returns a valid report.
"""
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import anthropic

from config import CLAUDE_MODEL, SUPPORTED_PLATFORMS
from core.models import PostData, JudgmentError, PolicyNotFoundError
from services.checker import CheckerService
from services.topic_search import TopicPost, search_reddit

logger = logging.getLogger("policyguard.services.topic_report")

# Avatar tile colors assigned deterministically per handle (data, not styling).
AVATAR_PALETTE = [
    "#0E4C5C", "#A8324A", "#B9741A", "#3E7C6A", "#16212B", "#0A3A47",
]

SNIPPET_MAX_CHARS = 280
MAX_SENTIMENT_SAMPLES = 12


# ---------------------------------------------------------------- helpers

def _relative_label(created_utc: float) -> str:
    """Unix timestamp -> '2d ago' style label."""
    if not created_utc:
        return ""
    delta = max(0, time.time() - created_utc)
    if delta < 3600:
        return f"{max(1, int(delta // 60))}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    return f"{int(delta // 86400)}d ago"


def _initials(handle: str) -> str:
    cleaned = handle.removeprefix("u/").removeprefix("r/").lstrip("@")
    return cleaned[:2].lower() if cleaned else "??"


def _avatar_color(handle: str) -> str:
    return AVATAR_PALETTE[hash(handle) % len(AVATAR_PALETTE)]


def _author(handle: str) -> dict:
    return {
        "handle": handle,
        "initials": _initials(handle),
        "avatarColor": _avatar_color(handle),
    }


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= SNIPPET_MAX_CHARS:
        return text
    return text[: SNIPPET_MAX_CHARS - 1].rstrip() + "…"


def _engagement(post: TopicPost) -> dict:
    """Only include metrics we actually have (RSS results carry none)."""
    out: dict = {}
    if post.score:
        out["upvotes"] = post.score
    if post.num_comments:
        out["comments"] = post.num_comments
    return out


def _compact(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


def _volume_series(posts: list[TopicPost], days: int) -> list[dict]:
    """Bucket posts per day over the window, normalized to a 0..100 index."""
    now = datetime.now(timezone.utc)
    buckets = [0] * days
    for post in posts:
        if not post.created_utc:
            continue
        age_days = (now - datetime.fromtimestamp(post.created_utc, tz=timezone.utc)).days
        idx = days - 1 - age_days
        if 0 <= idx < days:
            buckets[idx] += 1
    peak = max(buckets) or 1
    return [
        {"date": f"d{i + 1}", "value": round(count / peak * 100)}
        for i, count in enumerate(buckets)
    ]


# ---------------------------------------------------------------- policy flags

def _severity_to_frontend(severity: str) -> str:
    return "high" if severity == "HIGH" else "low"


def _judge_posts(
    posts: list[TopicPost],
    checker: CheckerService,
    max_checks: int,
) -> list[tuple[TopicPost, dict | None]]:
    """
    Run the policy judge over the top posts concurrently.
    Returns (post, verdict) pairs; posts whose check failed are skipped.
    Empty when ANTHROPIC_API_KEY is not configured.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.warning("ANTHROPIC_API_KEY not set - skipping policy checks")
        return []

    targets = posts[:max_checks]
    if not targets:
        return []

    def check(post: TopicPost) -> tuple[TopicPost, dict | None]:
        data = PostData(
            url=post.url,
            platform=post.platform,
            text=post.text,
            author=post.author,
            title=post.title,
        )
        try:
            return post, checker.check_post(data)
        except (JudgmentError, PolicyNotFoundError) as e:
            logger.warning(f"Policy check failed for {post.url}: {e}")
            return post, None

    with ThreadPoolExecutor(max_workers=min(4, len(targets))) as pool:
        results = list(pool.map(check, targets))

    return [(post, verdict) for post, verdict in results if verdict is not None]


def _flags_from_verdicts(judged: list[tuple[TopicPost, dict]]) -> list[dict]:
    """Map judge verdicts onto the frontend Post[] shape for the flags tab."""
    flags: list[dict] = []
    for post, verdict in judged:
        violations = verdict.get("violations") or []
        if violations:
            top = violations[0]
            flag = {
                "policy": top["rule"],
                "citedRule": f"{top['policy_reference']} — \"{top['quote']}\"",
                "confidence": round(float(verdict["confidence"]) * 100),
                "severity": _severity_to_frontend(top["severity"]),
            }
            # Guardrail: flagged posts show a neutral AI summary, not raw content.
            snippet = f"AI summary: {top['explanation']}"
            redacted = True
        else:
            flag = None
            snippet = _snippet(post.text)
            redacted = False

        flags.append({
            "id": post.id,
            "platform": post.platform,
            "author": _author(post.author),
            "timestamp": _relative_label(post.created_utc),
            "snippet": snippet,
            "redacted": redacted,
            "engagement": _engagement(post),
            "flag": flag,
        })

    # Flagged posts first, highest confidence first.
    flags.sort(key=lambda f: (f["flag"] is None, -(f["flag"] or {}).get("confidence", 0)))
    return flags


# ---------------------------------------------------------------- sentiment

def _fallback_sentiment(posts: list[TopicPost]) -> tuple[dict, dict[str, str]]:
    stance = {"support": 0, "critical": 0, "neutral": 100}
    samples = [
        {"stance": "neutral", "text": _snippet(p.title), "platform": p.platform}
        for p in posts[:4]
    ]
    return {"stance": stance, "sampleComments": samples}, {}


def _estimate_sentiment(posts: list[TopicPost], query: str) -> tuple[dict, dict[str, str]]:
    """
    One Claude call: estimate the stance split and classify sample snippets.
    Returns (sentiment summary, per-post-id stance map). Falls back to a
    neutral estimate when the key is missing or the call fails.
    """
    if not os.environ.get("ANTHROPIC_API_KEY") or not posts:
        return _fallback_sentiment(posts)

    samples = [
        {"id": p.id, "platform": p.platform, "text": _snippet(p.text)}
        for p in posts[:MAX_SENTIMENT_SAMPLES]
    ]
    prompt = f"""Topic: "{query}"

Below are social media posts about this topic. For each post decide the
author's stance toward the topic: "support", "critical", or "neutral".
Then estimate the overall stance split as percentages summing to 100.

POSTS:
{json.dumps(samples, ensure_ascii=False)}

Return ONLY raw JSON (no markdown fences) with this structure:
{{
  "stance": {{"support": 0-100, "critical": 0-100, "neutral": 0-100}},
  "posts": [{{"id": "...", "stance": "support|critical|neutral"}}]
}}"""

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(response.content[0].text.strip())
        stance_by_id = {
            p["id"]: p["stance"]
            for p in data.get("posts", [])
            if p.get("stance") in ("support", "critical", "neutral")
        }
        raw = data.get("stance", {})
        stance = {
            "support": int(raw.get("support", 0)),
            "critical": int(raw.get("critical", 0)),
            "neutral": int(raw.get("neutral", 0)),
        }
        sample_comments = [
            {
                "stance": stance_by_id.get(s["id"], "neutral"),
                "text": s["text"],
                "platform": s["platform"],
            }
            for s in samples[:5]
        ]
        return {"stance": stance, "sampleComments": sample_comments}, stance_by_id
    except Exception as e:  # noqa: BLE001 - any failure degrades to fallback
        logger.warning(f"Sentiment estimation failed: {e}")
        return _fallback_sentiment(posts)


# ---------------------------------------------------------------- report

def build_topic_report(
    query: str,
    days: int,
    checker: CheckerService,
    max_checks: int = 5,
) -> dict:
    """
    Assemble a full TopicReport for the frontend.

    Live data comes from Reddit search; the other platforms are reported as
    not live (count 0) until search adapters exist for them.
    """
    posts = search_reddit(query, days=days)
    posts.sort(key=lambda p: p.score + p.num_comments, reverse=True)

    judged = _judge_posts(posts, checker, max_checks)
    flags = _flags_from_verdicts(judged)
    flagged_count = sum(1 for f in flags if f["flag"])

    sentiment_summary, stance_by_id = _estimate_sentiment(posts, query)
    volume = _volume_series(posts, days)

    # Viral: top posts by engagement (excluding nothing - flags live separately).
    viral = [
        {
            "id": p.id,
            "platform": p.platform,
            "author": _author(p.author),
            "timestamp": _relative_label(p.created_utc),
            "snippet": _snippet(p.text),
            "redacted": False,
            "engagement": _engagement(p),
            "flag": None,
        }
        for p in posts[:6]
    ]

    # Influencers: authors of the highest-engagement posts.
    influencers = []
    seen_authors: set[str] = set()
    for p in posts:
        if p.author in seen_authors:
            continue
        seen_authors.add(p.author)
        reach_label = (
            f"r/{p.subreddit} · {_compact(p.subreddit_subscribers)} members"
            if p.subreddit_subscribers
            else f"r/{p.subreddit}" if p.subreddit else "reddit"
        )
        influencers.append({
            "id": f"inf-{p.id}",
            "platform": p.platform,
            "author": _author(p.author),
            "reachLabel": reach_label,
            "quote": _snippet(p.title),
            "stance": stance_by_id.get(p.id, "neutral"),
            "engagement": _engagement(p),
        })
        if len(influencers) >= 5:
            break

    # Top accounts: grouped by author, ranked by accumulated karma on topic.
    by_author: dict[str, dict] = {}
    for p in posts:
        entry = by_author.setdefault(p.author, {"karma": 0, "count": 0})
        entry["karma"] += p.score
        entry["count"] += 1
    top_accounts = [
        {
            "id": f"acc-{i}",
            "platform": "reddit",
            "handle": handle,
            "reach": entry["karma"],
            "reachUnit": "KARMA",
            "postsOnTopic": entry["count"],
            "initials": _initials(handle),
            "avatarColor": _avatar_color(handle),
        }
        for i, (handle, entry) in enumerate(
            sorted(
                by_author.items(),
                key=lambda kv: (kv[1]["karma"], kv[1]["count"]),
                reverse=True,
            )[:5]
        )
    ]

    estimated_reach = sum(p.score * 30 + p.num_comments * 60 for p in posts)

    return {
        "query": query,
        "timeframeDays": days,
        "sources": [
            {
                "platform": platform,
                "count": len(posts) if platform == "reddit" else 0,
                "live": platform == "reddit",
            }
            for platform in SUPPORTED_PLATFORMS
        ],
        "metrics": {
            "postsFound": len(posts),
            "estimatedReach": estimated_reach,
            "flaggedForReview": flagged_count,
            "flaggedPct": round(flagged_count / len(posts) * 100, 1) if posts else 0,
            "loudestSource": "reddit",
            "loudestSharePct": 100 if posts else 0,
        },
        "flags": flags,
        "viral": viral,
        "influencers": influencers,
        "sentiment": {
            "stance": sentiment_summary["stance"],
            "interest": volume,
            "sampleComments": sentiment_summary["sampleComments"],
        },
        "volume": volume,
        "topAccounts": top_accounts,
    }
