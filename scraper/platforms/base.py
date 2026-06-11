"""Platform adapter contract + registry.

Adding a platform is a single file: subclass :class:`PlatformScraper`,
implement ``build_input`` and ``normalize``, and decorate the class with
``@register``. The orchestration layer only ever talks to ``get_scraper`` /
``iter_enabled`` - it never imports a concrete adapter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any, TypeVar

from scraper.models import Campaign, NormalizedPost, Platform


class PlatformScraper(ABC):
    """Abstract base every platform adapter implements."""

    platform: Platform
    actor_id: str
    enabled: bool = True

    @abstractmethod
    def build_input(self, campaign: Campaign) -> dict[str, Any]:
        """Map a campaign's seeds/limits to this actor's input JSON."""
        raise NotImplementedError

    @abstractmethod
    def normalize(
        self, raw_item: dict[str, Any], campaign: Campaign
    ) -> NormalizedPost | None:
        """Map one Apify dataset item to NormalizedPost; return None to skip junk."""
        raise NotImplementedError


_REGISTRY: dict[Platform, PlatformScraper] = {}

T = TypeVar("T", bound=PlatformScraper)


def register(cls: type[T]) -> type[T]:
    """Class decorator registering a single instance of an adapter."""
    instance = cls()
    if instance.platform in _REGISTRY:
        raise ValueError(f"Duplicate adapter registered for {instance.platform!r}")
    _REGISTRY[instance.platform] = instance
    return cls


def get_scraper(platform: Platform | str) -> PlatformScraper:
    """Return the registered adapter for a platform.

    Raises ``KeyError`` if no adapter is registered.
    """
    key = Platform(platform) if not isinstance(platform, Platform) else platform
    try:
        return _REGISTRY[key]
    except KeyError as exc:
        raise KeyError(f"No adapter registered for platform {key!r}") from exc


def iter_enabled() -> Iterator[PlatformScraper]:
    """Yield all enabled adapters (skips disabled stubs like LinkedIn/Twitter)."""
    for adapter in _REGISTRY.values():
        if adapter.enabled:
            yield adapter


def registered_platforms() -> list[Platform]:
    """Return all registered platforms (enabled and disabled)."""
    return list(_REGISTRY.keys())
