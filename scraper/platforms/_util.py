"""Small parsing helpers shared by platform adapters.

Apify items are messy and schemas drift, so every accessor here is defensive:
missing keys and bad types degrade to ``None`` / empty rather than raising.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

_HASHTAG_RE = re.compile(r"#(\w+)", re.UNICODE)
_MENTION_RE = re.compile(r"@(\w[\w.]*)", re.UNICODE)


def first(item: dict[str, Any], *keys: str) -> Any:
    """Return the first present, non-None value among ``keys``."""
    for key in keys:
        if key in item and item[key] is not None:
            return item[key]
    return None


def as_int(value: Any) -> int | None:
    """Coerce to int, tolerating strings like '1.2K' -> None (keep it simple)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int,)):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if cleaned.isdigit():
            return int(cleaned)
    return None


def as_str(value: Any) -> str | None:
    """Coerce to a non-empty stripped string, else None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_datetime(value: Any) -> datetime | None:
    """Parse common Apify timestamp shapes into an aware UTC datetime."""
    if value is None:
        return None
    # Unix epoch (seconds).
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        # Numeric epoch as string.
        if raw.isdigit():
            return parse_datetime(int(raw))
        # ISO 8601, normalize trailing Z.
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def extract_hashtags(text: str | None, extra: Any = None) -> list[str]:
    """Collect hashtags from free text plus any structured list, deduped."""
    tags: list[str] = []
    if text:
        tags.extend(m.lower() for m in _HASHTAG_RE.findall(text))
    for tag in _coerce_tag_list(extra):
        tags.append(tag.lstrip("#").lower())
    return _dedupe(tags)


def extract_mentions(text: str | None, extra: Any = None) -> list[str]:
    """Collect @mentions from free text plus any structured list, deduped."""
    mentions: list[str] = []
    if text:
        mentions.extend(m.lower() for m in _MENTION_RE.findall(text))
    for m in _coerce_tag_list(extra):
        mentions.append(m.lstrip("@").lower())
    return _dedupe(mentions)


def _coerce_tag_list(extra: Any) -> list[str]:
    if not extra:
        return []
    out: list[str] = []
    if isinstance(extra, (list, tuple)):
        for el in extra:
            if isinstance(el, str):
                out.append(el)
            elif isinstance(el, dict):
                name = el.get("name") or el.get("hashtag") or el.get("title")
                if isinstance(name, str):
                    out.append(name)
    return out


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out
