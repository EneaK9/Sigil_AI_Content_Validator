"""Twitter / X adapter - DISABLED STUB.

See ``linkedin.py`` for the step-by-step template. While ``enabled = False`` the
runner skips this platform, but it stays registered for discoverability.
"""

from __future__ import annotations

from typing import Any

from scraper.models import Campaign, NormalizedPost, Platform
from scraper.platforms.base import PlatformScraper, register

_NOT_IMPLEMENTED = "Twitter adapter not implemented yet"


@register
class TwitterScraper(PlatformScraper):
    platform = Platform.twitter
    actor_id = ""  # set a real Apify actor id when implementing
    enabled = False

    def build_input(self, campaign: Campaign) -> dict[str, Any]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def normalize(
        self, raw_item: dict[str, Any], campaign: Campaign
    ) -> NormalizedPost | None:
        raise NotImplementedError(_NOT_IMPLEMENTED)
