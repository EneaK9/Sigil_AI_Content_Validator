"""
Unit tests for core/json_input.py - JSON input parsing and validation.
"""
import json
import pytest
from unittest.mock import patch, mock_open

from core.json_input import (
    parse_json_post,
    parse_json_input,
    load_json_file,
    JsonInputError
)
from core.models import PostData


class TestParseJsonPost:
    """Tests for parse_json_post function."""
    
    def test_minimal_valid_post(self):
        """Test parsing with only required fields."""
        data = {
            "url": "https://www.facebook.com/post/123",
            "message": "Hello world"
        }
        post, transcript = parse_json_post(data)
        
        assert isinstance(post, PostData)
        assert post.url == "https://www.facebook.com/post/123"
        assert post.text == "Hello world"
        assert post.platform == "facebook"
        assert transcript is None
    
    def test_full_facebook_post(self):
        """Test parsing a complete Facebook post with all fields."""
        data = {
            "post_id": "122113665879162352",
            "type": "post",
            "url": "https://www.facebook.com/permalink.php?story_fbid=abc&id=123",
            "message": "Test post content",
            "timestamp": 1781016157,
            "reactions_count": 3,
            "comments_count": 1,
            "reshare_count": 1,
            "author.name": "Test Author",
            "author.url": "https://www.facebook.com/people/Test/123/",
            "image.uri": "https://example.com/image.jpg",
            "video": None,
            "video_transcript": None,
            "external_url": None
        }
        post, transcript = parse_json_post(data)
        
        assert post.platform == "facebook"
        assert post.text == "Test post content"
        assert post.author == "Test Author"
        assert post.image_urls == ["https://example.com/image.jpg"]
        assert post.video_urls == []
        assert transcript is None
    
    def test_post_with_video_transcript(self):
        """Test parsing post with pre-transcribed video."""
        data = {
            "url": "https://www.tiktok.com/@user/video/123",
            "message": "Check out this video",
            "video_transcript": "Hello everyone, welcome to my video"
        }
        post, transcript = parse_json_post(data)
        
        assert post.platform == "tiktok"
        assert transcript == "Hello everyone, welcome to my video"
    
    def test_post_with_video_url(self):
        """Test parsing post with video URL."""
        data = {
            "url": "https://www.facebook.com/post/123",
            "message": "Video post",
            "video": "https://example.com/video.mp4"
        }
        post, transcript = parse_json_post(data)
        
        assert post.video_urls == ["https://example.com/video.mp4"]
        assert transcript is None
    
    def test_instagram_platform_detection(self):
        """Test Instagram URL platform detection."""
        data = {
            "url": "https://www.instagram.com/p/ABC123/",
            "message": "Instagram post"
        }
        post, _ = parse_json_post(data)
        assert post.platform == "instagram"
    
    def test_reddit_platform_detection(self):
        """Test Reddit URL platform detection."""
        data = {
            "url": "https://www.reddit.com/r/test/comments/abc/title",
            "message": "Reddit post"
        }
        post, _ = parse_json_post(data)
        assert post.platform == "reddit"
    
    def test_x_twitter_platform_detection(self):
        """Test X/Twitter URL platform detection."""
        data = {
            "url": "https://x.com/user/status/123456",
            "message": "Tweet content"
        }
        post, _ = parse_json_post(data)
        assert post.platform == "x"
    
    def test_missing_url_raises_error(self):
        """Test that missing URL raises JsonInputError."""
        data = {"message": "No URL provided"}
        with pytest.raises(JsonInputError) as exc:
            parse_json_post(data)
        assert "Missing required field 'url'" in str(exc.value)
    
    def test_missing_message_raises_error(self):
        """Test that missing message raises JsonInputError."""
        data = {"url": "https://facebook.com/post/1"}
        with pytest.raises(JsonInputError) as exc:
            parse_json_post(data)
        assert "Missing required field 'message'" in str(exc.value)
    
    def test_empty_url_raises_error(self):
        """Test that empty URL raises JsonInputError."""
        data = {"url": "", "message": "Test"}
        with pytest.raises(JsonInputError) as exc:
            parse_json_post(data)
        assert "non-empty string" in str(exc.value)
    
    def test_unsupported_platform_raises_error(self):
        """Test that unsupported platform URL raises JsonInputError."""
        data = {
            "url": "https://youtube.com/watch?v=abc",
            "message": "YouTube video"
        }
        with pytest.raises(JsonInputError) as exc:
            parse_json_post(data)
        assert "Could not detect platform" in str(exc.value)
    
    def test_null_optional_fields_handled(self):
        """Test that null optional fields are handled gracefully."""
        data = {
            "url": "https://facebook.com/post/1",
            "message": "Test",
            "author.name": None,
            "image.uri": None,
            "video": None,
            "video_transcript": None
        }
        post, transcript = parse_json_post(data)
        
        assert post.author == ""
        assert post.image_urls == []
        assert post.video_urls == []
        assert transcript is None
    
    def test_non_string_video_transcript_ignored(self):
        """Test that non-string video_transcript is ignored."""
        data = {
            "url": "https://facebook.com/post/1",
            "message": "Test",
            "video_transcript": 12345  # number instead of string
        }
        post, transcript = parse_json_post(data)
        assert transcript is None


class TestParseJsonInput:
    """Tests for parse_json_input function."""
    
    def test_parse_single_object(self):
        """Test parsing a single JSON object."""
        json_str = '{"url": "https://facebook.com/post/1", "message": "Test"}'
        results = parse_json_input(json_str)
        
        assert len(results) == 1
        post, transcript = results[0]
        assert post.text == "Test"
    
    def test_parse_array_of_objects(self):
        """Test parsing an array of JSON objects."""
        json_str = '''[
            {"url": "https://facebook.com/post/1", "message": "First"},
            {"url": "https://facebook.com/post/2", "message": "Second"},
            {"url": "https://instagram.com/p/abc", "message": "Third"}
        ]'''
        results = parse_json_input(json_str)
        
        assert len(results) == 3
        assert results[0][0].text == "First"
        assert results[1][0].text == "Second"
        assert results[2][0].text == "Third"
        assert results[2][0].platform == "instagram"
    
    def test_invalid_json_raises_error(self):
        """Test that invalid JSON raises JsonInputError."""
        with pytest.raises(JsonInputError) as exc:
            parse_json_input("not valid json")
        assert "Invalid JSON" in str(exc.value)
    
    def test_empty_array_raises_error(self):
        """Test that empty array raises JsonInputError."""
        with pytest.raises(JsonInputError) as exc:
            parse_json_input("[]")
        assert "Empty array" in str(exc.value)
    
    def test_non_object_in_array_raises_error(self):
        """Test that non-object items in array raise JsonInputError."""
        with pytest.raises(JsonInputError) as exc:
            parse_json_input('["string", "not object"]')
        assert "not a JSON object" in str(exc.value)
    
    def test_error_in_array_item_includes_index(self):
        """Test that errors in array items include the item index."""
        json_str = '''[
            {"url": "https://facebook.com/post/1", "message": "Valid"},
            {"url": "https://facebook.com/post/2"}
        ]'''
        with pytest.raises(JsonInputError) as exc:
            parse_json_input(json_str)
        assert "Item 1" in str(exc.value)
        assert "message" in str(exc.value)
    
    def test_non_array_non_object_raises_error(self):
        """Test that non-array/non-object JSON raises JsonInputError."""
        with pytest.raises(JsonInputError) as exc:
            parse_json_input('"just a string"')
        assert "must be an object or array" in str(exc.value)


class TestLoadJsonFile:
    """Tests for load_json_file function."""
    
    def test_file_not_found_raises_error(self):
        """Test that missing file raises JsonInputError."""
        with pytest.raises(JsonInputError) as exc:
            load_json_file("/nonexistent/path/file.json")
        assert "File not found" in str(exc.value)
    
    def test_load_valid_file(self, tmp_path):
        """Test loading a valid JSON file."""
        json_file = tmp_path / "posts.json"
        json_file.write_text('{"url": "https://facebook.com/post/1", "message": "Test"}')
        
        results = load_json_file(str(json_file))
        
        assert len(results) == 1
        assert results[0][0].text == "Test"
    
    def test_load_batch_file(self, tmp_path):
        """Test loading a batch JSON file with multiple posts."""
        json_file = tmp_path / "batch.json"
        data = [
            {"url": "https://facebook.com/post/1", "message": "First"},
            {"url": "https://facebook.com/post/2", "message": "Second"}
        ]
        json_file.write_text(json.dumps(data))
        
        results = load_json_file(str(json_file))
        
        assert len(results) == 2


class TestIntegration:
    """Integration tests for JSON input flow."""
    
    def test_full_contract_parsing(self):
        """Test parsing the complete JSON contract as specified."""
        json_str = '''{
            "post_id": "122113665879162352",
            "type": "post",
            "url": "https://www.facebook.com/permalink.php?story_fbid=pfbid02TPhtvF57bwjunkAbWWsdyEXa6bmbWUJyE8UXBTUWPYwwuRVwPTA8jj85tDcHUTYtl&id=61584870576375",
            "message": "Bojkotoni Mediat e pushtetit Rama-Berisha.",
            "timestamp": 1781016157,
            "reactions_count": 3,
            "comments_count": 1,
            "reshare_count": 1,
            "author.name": "Personazhi Momentit",
            "author.url": "https://www.facebook.com/people/Personazhi-Momentit/61584870576375/",
            "image.uri": "https://scontent.fvii2-4.fna.fbcdn.net/v/image.jpg",
            "video": null,
            "external_url": null
        }'''
        
        results = parse_json_input(json_str)
        
        assert len(results) == 1
        post, transcript = results[0]
        
        assert post.platform == "facebook"
        assert post.text == "Bojkotoni Mediat e pushtetit Rama-Berisha."
        assert post.author == "Personazhi Momentit"
        assert len(post.image_urls) == 1
        assert "scontent" in post.image_urls[0]
        assert transcript is None
    
    def test_batch_with_mixed_platforms(self):
        """Test batch processing with different platforms."""
        json_str = '''[
            {"url": "https://facebook.com/post/1", "message": "FB post"},
            {"url": "https://instagram.com/p/abc", "message": "IG post"},
            {"url": "https://reddit.com/r/test/comments/abc/title", "message": "Reddit post"},
            {"url": "https://x.com/user/status/123", "message": "X post"},
            {"url": "https://tiktok.com/@user/video/123", "message": "TikTok post"}
        ]'''
        
        results = parse_json_input(json_str)
        
        assert len(results) == 5
        platforms = [r[0].platform for r in results]
        assert platforms == ["facebook", "instagram", "reddit", "x", "tiktok"]
    
    def test_batch_with_transcripts(self):
        """Test batch with some posts having transcripts."""
        json_str = '''[
            {"url": "https://facebook.com/post/1", "message": "No transcript"},
            {"url": "https://tiktok.com/@user/video/1", "message": "Has transcript", "video_transcript": "Hello world"}
        ]'''
        
        results = parse_json_input(json_str)
        
        assert results[0][1] is None  # No transcript
        assert results[1][1] == "Hello world"  # Has transcript
