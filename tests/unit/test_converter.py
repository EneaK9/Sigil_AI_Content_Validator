"""Unit tests for the scraper <-> validator converter boundary."""
import pytest

from sigil.pipeline.converter import db_row_to_post_data, validator_platform


class TestValidatorPlatform:
    def test_twitter_maps_to_x(self):
        assert validator_platform("twitter") == "x"

    @pytest.mark.parametrize(
        "platform", ["tiktok", "instagram", "facebook", "linkedin", "reddit", "x"]
    )
    def test_other_platforms_unchanged(self, platform):
        assert validator_platform(platform) == platform


class TestDbRowToPostData:
    def test_twitter_row_becomes_x_postdata(self):
        post = db_row_to_post_data(
            {
                "platform": "twitter",
                "platform_post_id": "123",
                "url": "https://x.com/u/status/123",
                "author_handle": "u",
                "content_text": "hello",
            }
        )
        # PostData would raise on platform="twitter"; the boundary maps it to "x".
        assert post.platform == "x"
        assert post.text == "hello"
        assert post.author == "u"

    def test_missing_url_builds_fallback(self):
        post = db_row_to_post_data(
            {
                "platform": "tiktok",
                "platform_post_id": "999",
                "url": None,
                "content_text": "x",
            }
        )
        assert "999" in post.url

    def test_media_urls_collected(self):
        post = db_row_to_post_data(
            {
                "platform": "instagram",
                "platform_post_id": "1",
                "url": "https://insta/p/1",
                "thumbnail_url": "https://img/1.jpg",
                "video_url": "https://vid/1.mp4",
                "content_text": "c",
            }
        )
        assert post.image_urls == ["https://img/1.jpg"]
        assert post.video_urls == ["https://vid/1.mp4"]
