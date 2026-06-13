"""Platform adapters and registry.

Importing this package imports every adapter module so that their ``@register``
decorators populate the registry. Orchestration code should depend only on
``get_scraper`` / ``iter_enabled`` from :mod:`scraper.platforms.base`.
"""

from scraper.platforms import facebook, instagram, linkedin, reddit, tiktok, twitter
from scraper.platforms.base import (
    PlatformScraper,
    get_scraper,
    iter_enabled,
    registered_platforms,
    register,
)

__all__ = [
    "PlatformScraper",
    "get_scraper",
    "iter_enabled",
    "registered_platforms",
    "register",
    "tiktok",
    "instagram",
    "facebook",
    "linkedin",
    "reddit",
    "twitter",
]
