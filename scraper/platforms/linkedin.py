"""LinkedIn adapter - DISABLED STUB.

This is the template for adding a new platform. To implement LinkedIn:
  1. Set ``enabled = True`` and a real ``actor_id``.
  2. Implement ``build_input`` (map seeds -> actor input).
  3. Implement ``normalize`` (map a dataset item -> NormalizedPost).
No changes to the Apify client, collector, runner, or DB layer are needed - the
registry wires it in automatically.

While ``enabled = False`` the runner skips this platform entirely, but it still
appears in the registry so it is discoverable.
"""

from __future__ import annotations

from typing import Any

from scraper.models import Campaign, NormalizedPost, Platform
from scraper.platforms.base import PlatformScraper, register

_NOT_IMPLEMENTED = "LinkedIn adapter not implemented yet"


@register
class LinkedInScraper(PlatformScraper):
    platform = Platform.linkedin
    actor_id = ""  # set a real Apify actor id when implementing
    enabled = False

    def build_input(self, campaign: Campaign) -> dict[str, Any]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def normalize(
        self, raw_item: dict[str, Any], campaign: Campaign
    ) -> NormalizedPost | None:
        raise NotImplementedError(_NOT_IMPLEMENTED)
