"""Topic-specific relevance profiles.

The scraper normalizes raw Apify items into a common post shape; after that we
apply a lightweight relevance gate + dedupe to keep each client/topic focused.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RelevanceProfile:
    """Regex-based relevance profile."""

    name: str
    required_any: list[re.Pattern]
    optional_any: list[re.Pattern]

    def is_relevant(self, text: str) -> bool:
        if not self.required_any:
            return True
        if not any(r.search(text) for r in self.required_any):
            return False
        if not self.optional_any:
            return True
        return any(r.search(text) for r in self.optional_any)


def profile_for(client: str | None, topic: str | None) -> RelevanceProfile | None:
    key = f"{(client or '').strip().lower()}:{(topic or '').strip().lower()}"
    return _PROFILES.get(key)


def _r(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


_PROFILES: dict[str, RelevanceProfile] = {
    # Existing Sigil story profile (Albania/Kushner/Trump/Rama)
    "sigil:albania_political": RelevanceProfile(
        name="sigil:albania_political",
        required_any=[
            _r(r"\b(albania|albanian|shqip(?:e|eria|ëria)?|tirana|tiran[ëe]|vlora|vlor[ëe]|sazan)\b"),
        ],
        optional_any=[
            _r(r"\b(trump|kushner|ivanka|jared|rama|edirama)\b"),
            _r(r"\b(protest\w*|demonstrat\w*|resort|island|development|project|invest\w*|billion|construction)\b"),
        ],
    ),
    # Kevin O'Leary / Utah AI data center backlash profile
    "kevin:utah_datacenter_backlash": RelevanceProfile(
        name="kevin:utah_datacenter_backlash",
        required_any=[
            _r(r"\b(kevin\s*o['’]leary|o['’]leary)\b"),
            _r(r"\b(data\s*center|datacenter|hyperscale|ai\s*data\s*center)\b"),
        ],
        optional_any=[
            _r(r"\b(utah|box\s*elder|hansel\s*valley|great\s*salt\s*lake|mida|stratos)\b"),
            _r(r"\b(backlash|protest\w*|oppos\w*|boycott|petition|outrage|concern)\b"),
            _r(r"\b(water|power|electricity|grid|environment\w*|wildlife|lake)\b"),
            _r(r"\b(china|chinese|ccp)\b"),
        ],
    ),
}

