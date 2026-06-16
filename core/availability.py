"""
Report-result monitoring: re-check whether a previously-seen post is still live.

Detection (the rest of this repo) answers "does this post violate policy?".
This module answers a different question — "is the post still up?" — by
re-visiting the URL and classifying the HTTP response. It is the closest
available proxy for the action a platform took on a reported post: platforms
don't expose their internal moderation decisions to third parties, but a post
that has become a 404/410 was almost certainly removed, and a 403 was almost
certainly restricted.

This is intentionally lightweight: it does NOT re-run Claude judgment, download
media, or parse content. It only maps the response status to an
AvailabilityStatus. The dashboard then maps that onto an evidence item's report
status (removed / restricted / still_live).
"""
import re

import requests

from config import REDDIT_USER_AGENT, SCRAPER_USER_AGENT
from core.detector import detect_platform
from core.models import AvailabilityResult, AvailabilityStatus

# X needs its own token to query authoritatively; import lazily inside the helper.
import os


def _classify_status_code(code: int) -> AvailabilityStatus:
    """Map an HTTP status code to a reachability verdict."""
    if code in (404, 410):
        return AvailabilityStatus.REMOVED
    if code in (401, 403):
        return AvailabilityStatus.RESTRICTED
    if code == 200:
        return AvailabilityStatus.LIVE
    return AvailabilityStatus.UNKNOWN


def check_availability(url: str, timeout: int = 10) -> AvailabilityResult:
    """Re-check whether a post is still reachable.

    Never raises for an unreachable post — an unreachable post is the whole
    point. Returns an AvailabilityResult with UNKNOWN only when we genuinely
    cannot tell (network failure, unsupported platform, missing X token).
    """
    try:
        platform = detect_platform(url)
    except ValueError as e:
        return AvailabilityResult(
            url=url,
            platform="unknown",
            status=AvailabilityStatus.UNKNOWN,
            detail=f"Unrecognized platform URL: {e}".split("\n")[0],
        )

    if platform in ("facebook", "instagram"):
        # Meta's auth walls make a 200/404 distinction meaningless here.
        return AvailabilityResult(
            url=url,
            platform=platform,
            status=AvailabilityStatus.UNKNOWN,
            detail=f"{platform} cannot be auto-checked (authentication wall).",
        )

    if platform == "x":
        return _check_x(url, timeout)
    if platform == "reddit":
        return _check_reddit(url, timeout)
    if platform == "tiktok":
        return _check_tiktok(url, timeout)

    return AvailabilityResult(
        url=url, platform=platform, status=AvailabilityStatus.UNKNOWN,
        detail="No availability checker for this platform.",
    )


def _request(url: str, headers: dict, timeout: int):
    """GET that returns (response, error_detail). error_detail is set on network failure."""
    try:
        return requests.get(url, headers=headers, timeout=timeout), None
    except requests.Timeout:
        return None, f"Request timed out after {timeout}s."
    except requests.RequestException as e:
        return None, f"Network error: {e}"


def _check_x(url: str, timeout: int) -> AvailabilityResult:
    """Authoritative via the X API when a token is present; otherwise UNKNOWN.

    Scraping x.com without a token returns a JS shell with a 200 even for
    deleted tweets, so we don't guess — we say UNKNOWN and explain why.
    """
    bearer = os.environ.get("X_BEARER_TOKEN")
    if not bearer:
        return AvailabilityResult(
            url=url, platform="x", status=AvailabilityStatus.UNKNOWN,
            detail="X availability requires X_BEARER_TOKEN; cannot verify without it.",
        )

    match = re.search(r"(?:x\.com|twitter\.com)/\w+/status/(\d+)", url)
    if not match:
        return AvailabilityResult(
            url=url, platform="x", status=AvailabilityStatus.UNKNOWN,
            detail="Could not extract tweet ID from URL.",
        )
    tweet_id = match.group(1)

    headers = {"Authorization": f"Bearer {bearer}", "User-Agent": "PolicyGuard/1.0"}
    resp, err = _request(f"https://api.twitter.com/2/tweets/{tweet_id}", headers, timeout)
    if resp is None:
        return AvailabilityResult(url=url, platform="x", status=AvailabilityStatus.UNKNOWN, detail=err)

    status = _classify_status_code(resp.status_code)
    detail = f"X API HTTP {resp.status_code}."

    # Inspect the errors array (present on both 200-with-errors and some 403s).
    # A suspended author is a takedown at the account level, distinct from a
    # single deleted tweet — surface it as ACCOUNT_BANNED.
    try:
        body = resp.json()
    except ValueError:
        body = {}
    errors = body.get("errors") or []
    err_text = " ".join(
        f"{e.get('title', '')} {e.get('detail', '')}" for e in errors
    ).lower()

    if "suspend" in err_text:
        status = AvailabilityStatus.ACCOUNT_BANNED
        detail = f"Author suspended: {errors[0].get('detail', 'account banned')}"
    elif resp.status_code == 200 and "data" not in body and errors:
        # 200 with an errors array (and no data) means the tweet is gone/withheld.
        status = AvailabilityStatus.REMOVED
        detail = f"Tweet unavailable: {errors[0].get('detail', 'not found')}"

    return AvailabilityResult(
        url=url, platform="x", status=status, http_status=resp.status_code, detail=detail,
    )


def _check_reddit(url: str, timeout: int) -> AvailabilityResult:
    """Reddit reports removals via 404/403, and sometimes a 200 with removal markers."""
    base = url.rstrip("/")
    json_url = f"{base}.json"
    if "?" in base:
        head, query = base.split("?", 1)
        json_url = f"{head}.json?{query}"

    resp, err = _request(json_url, {"User-Agent": REDDIT_USER_AGENT}, timeout)
    if resp is None:
        return AvailabilityResult(url=url, platform="reddit", status=AvailabilityStatus.UNKNOWN, detail=err)

    status = _classify_status_code(resp.status_code)
    detail = f"Reddit HTTP {resp.status_code}."
    if resp.status_code == 200:
        # A live URL can still host a removed post — Reddit keeps the page but
        # blanks the body and stamps removed_by_category / [deleted].
        try:
            post = resp.json()[0]["data"]["children"][0]["data"]
            if post.get("removed_by_category") or post.get("selftext") in ("[removed]", "[deleted]"):
                status = AvailabilityStatus.REMOVED
                detail = f"Post removed ({post.get('removed_by_category', 'deleted')})."
        except (KeyError, IndexError, TypeError, ValueError):
            pass
    return AvailabilityResult(
        url=url, platform="reddit", status=status, http_status=resp.status_code, detail=detail,
    )


def _check_tiktok(url: str, timeout: int) -> AvailabilityResult:
    """TikTok returns a 404 for deleted videos; 200 means the page still resolves."""
    headers = {
        "User-Agent": SCRAPER_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    resp, err = _request(url, headers, timeout)
    if resp is None:
        return AvailabilityResult(url=url, platform="tiktok", status=AvailabilityStatus.UNKNOWN, detail=err)

    status = _classify_status_code(resp.status_code)
    return AvailabilityResult(
        url=url, platform="tiktok", status=status, http_status=resp.status_code,
        detail=f"TikTok HTTP {resp.status_code}.",
    )
