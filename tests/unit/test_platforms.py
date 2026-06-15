"""Unit tests for platform adapter normalization."""
from uuid import uuid4

import pytest

from sigil.scraper.models import Campaign, Platform
from sigil.scraper.platforms.base import get_scraper

# Importing the package registers all adapters via decorators.
import sigil.scraper.platforms  # noqa: F401


@pytest.fixture
def campaign():
    return Campaign(id=uuid4(), platform=Platform.tiktok, topic="albania", country="AL")


class TestTikTokNormalize:
    def test_normalizes_a_video_item(self, campaign):
        adapter = get_scraper(Platform.tiktok)
        raw = {
            "id": "7649206116575939848",
            "text": "Land belongs to the people! #albania",
            "webVideoUrl": "https://www.tiktok.com/@ppl/video/7649206116575939848",
            "authorMeta": {"name": "ppl", "id": "u1"},
            "diggCount": 35,
            "commentCount": 2,
            "playCount": 3556,
            "videoMeta": {"downloadAddr": "https://v/x.mp4", "coverUrl": "https://c/x.jpg"},
        }
        post = adapter.normalize(raw, campaign)
        assert post is not None
        assert post.platform == Platform.tiktok
        assert post.platform_post_id == "7649206116575939848"
        assert post.author_handle == "ppl"
        assert post.like_count == 35
        assert post.view_count == 3556
        assert post.has_video is True
        assert post.topic == "albania"
        assert post.campaign_id == campaign.id

    def test_non_post_item_returns_none(self, campaign):
        adapter = get_scraper(Platform.tiktok)
        assert adapter.normalize({"summary": "no id here"}, campaign) is None
