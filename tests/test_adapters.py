"""Unit tests for each adapter's normalize/build_input against saved fixtures."""

from __future__ import annotations

import pytest

from scraper.models import Campaign, Platform
from scraper.platforms import get_scraper, registered_platforms
from scraper.platforms.base import iter_enabled
from tests.conftest import TEST_CAMPAIGN_ID


def _campaign(platform: Platform, seeds: list[str]) -> Campaign:
    return Campaign(
        id=TEST_CAMPAIGN_ID,
        platform=platform,
        topic="urban-life",
        country="US",
        seeds=seeds,
        daily_target=1000,
        enabled=True,
    )


def test_all_platforms_registered() -> None:
    platforms = set(registered_platforms())
    assert platforms == {
        Platform.tiktok,
        Platform.instagram,
        Platform.facebook,
        Platform.linkedin,
        Platform.twitter,
    }


def test_disabled_stubs_are_excluded_from_enabled() -> None:
    enabled = {a.platform for a in iter_enabled()}
    assert Platform.linkedin not in enabled
    assert Platform.twitter not in enabled
    assert {Platform.tiktok, Platform.instagram, Platform.facebook} <= enabled


@pytest.mark.parametrize("platform", [Platform.linkedin, Platform.twitter])
def test_stub_methods_raise_not_implemented(platform: Platform) -> None:
    adapter = get_scraper(platform)
    assert adapter.enabled is False
    campaign = _campaign(platform, ["#x"])
    with pytest.raises(NotImplementedError):
        adapter.build_input(campaign)
    with pytest.raises(NotImplementedError):
        adapter.normalize({}, campaign)


def test_tiktok_normalize(fixture_loader) -> None:
    adapter = get_scraper(Platform.tiktok)
    campaign = _campaign(Platform.tiktok, ["#citylife", "@traveler", "downtown park"])
    post = adapter.normalize(fixture_loader("tiktok"), campaign)

    assert post is not None
    assert post.platform is Platform.tiktok
    assert post.platform_post_id == "7251234567890123456"
    assert post.author_handle == "traveler"
    assert post.like_count == 15234
    assert post.view_count == 250341
    assert post.has_video is True
    assert post.video_url == "https://v.tiktok.example/video/7251234567890123456.mp4"
    assert post.media_type == "video"
    assert "citylife" in post.hashtags and "parks" in post.hashtags
    assert "cityofexample" in post.mentions
    assert post.country == "US"
    assert post.topic == "urban-life"
    assert post.campaign_id == TEST_CAMPAIGN_ID
    assert post.needs_transcription() is True
    assert post.raw["id"] == "7251234567890123456"


def test_tiktok_build_input_classifies_seeds() -> None:
    adapter = get_scraper(Platform.tiktok)
    campaign = _campaign(Platform.tiktok, ["#citylife", "@traveler", "downtown park"])
    run_input = adapter.build_input(campaign)
    assert run_input["hashtags"] == ["citylife"]
    assert run_input["profiles"] == ["traveler"]
    assert run_input["searchQueries"] == ["downtown park"]
    assert run_input["shouldDownloadVideos"] is False
    assert run_input["shouldDownloadCovers"] is False


def test_instagram_normalize_carousel(fixture_loader) -> None:
    adapter = get_scraper(Platform.instagram)
    campaign = _campaign(Platform.instagram, ["localmarket"])
    post = adapter.normalize(fixture_loader("instagram"), campaign)

    assert post is not None
    assert post.platform_post_id == "3187654321098765432"
    assert post.author_handle == "makerstories"
    assert post.media_type == "carousel"
    assert post.has_video is False
    assert post.like_count == 2043
    assert post.url == "https://www.instagram.com/p/C8xYzAbCdEf/"
    assert "handmade" in post.hashtags
    assert post.needs_transcription() is False


def test_instagram_build_input_hashtag_and_url() -> None:
    adapter = get_scraper(Platform.instagram)
    campaign = _campaign(
        Platform.instagram,
        ["localmarket", "https://www.instagram.com/p/ABC123/"],
    )
    run_input = adapter.build_input(campaign)
    assert run_input["resultsType"] == "posts"
    assert run_input["directUrls"] == ["https://www.instagram.com/p/ABC123/"]
    assert run_input["search"] == "localmarket"
    assert run_input["searchType"] == "hashtag"


def test_facebook_normalize_video(fixture_loader) -> None:
    adapter = get_scraper(Platform.facebook)
    campaign = _campaign(
        Platform.facebook, ["https://www.facebook.com/cityofexample"]
    )
    post = adapter.normalize(fixture_loader("facebook"), campaign)

    assert post is not None
    assert post.platform_post_id == "1122334455667788"
    assert post.author_handle == "City of Example"
    assert post.has_video is True
    assert post.media_type == "video"
    assert post.share_count == 120
    assert post.needs_transcription() is True


def test_facebook_build_input_uses_start_urls_only() -> None:
    adapter = get_scraper(Platform.facebook)
    campaign = _campaign(
        Platform.facebook,
        ["https://www.facebook.com/cityofexample", "not-a-url-keyword"],
    )
    run_input = adapter.build_input(campaign)
    # Non-URL seeds are ignored (FB keyword search is unreliable).
    assert run_input["startUrls"] == [
        {"url": "https://www.facebook.com/cityofexample"}
    ]


def test_normalize_skips_junk_item() -> None:
    adapter = get_scraper(Platform.tiktok)
    campaign = _campaign(Platform.tiktok, ["#x"])
    assert adapter.normalize({"not": "a post"}, campaign) is None
