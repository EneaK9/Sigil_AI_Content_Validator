"""
Unit tests for video transcript integration in core/judge.py.
"""
import pytest
from unittest.mock import patch, MagicMock

from core.models import PostData
from core.judge import (
    fetch_video_transcripts,
    build_user_prompt,
    build_message_content,
    SYSTEM_PROMPT,
)


class TestFetchVideoTranscripts:
    """Tests for the fetch_video_transcripts function."""

    def test_no_video_urls_returns_empty_string(self):
        """Should return empty string when post has no video URLs."""
        post = PostData(
            url="https://example.com/post",
            platform="reddit",
            text="Just text",
            video_urls=[]
        )
        
        result = fetch_video_transcripts(post)
        
        assert result == ""

    @patch("core.judge.transcribe_video")
    def test_single_video_transcribed(self, mock_transcribe):
        """Should format single video transcript correctly."""
        mock_transcribe.return_value = "Hello, this is the video content."
        
        post = PostData(
            url="https://tiktok.com/@user/video/123",
            platform="tiktok",
            text="Caption",
            video_urls=["https://tiktok.com/@user/video/123"]
        )
        
        result = fetch_video_transcripts(post)
        
        assert "[Video 1 transcript]" in result
        assert "Hello, this is the video content." in result
        mock_transcribe.assert_called_once_with("https://tiktok.com/@user/video/123")

    @patch("core.judge.transcribe_video")
    def test_multiple_videos_transcribed(self, mock_transcribe):
        """Should format multiple video transcripts correctly."""
        mock_transcribe.side_effect = ["First video content.", "Second video content."]
        
        post = PostData(
            url="https://reddit.com/r/test/comments/abc/post",
            platform="reddit",
            text="Post text",
            video_urls=["https://v.redd.it/video1", "https://v.redd.it/video2"]
        )
        
        result = fetch_video_transcripts(post)
        
        assert "[Video 1 transcript]" in result
        assert "[Video 2 transcript]" in result
        assert "First video content." in result
        assert "Second video content." in result

    @patch("core.judge.transcribe_video")
    def test_failed_transcription_skipped(self, mock_transcribe):
        """Should skip videos that fail to transcribe."""
        mock_transcribe.return_value = None
        
        post = PostData(
            url="https://tiktok.com/@user/video/123",
            platform="tiktok",
            text="Caption",
            video_urls=["https://tiktok.com/@user/video/123"]
        )
        
        result = fetch_video_transcripts(post)
        
        assert result == ""

    @patch("core.judge.transcribe_video")
    def test_partial_transcription_success(self, mock_transcribe):
        """Should include only successfully transcribed videos."""
        mock_transcribe.side_effect = [None, "Second video works.", None]
        
        post = PostData(
            url="https://example.com/post",
            platform="reddit",
            text="Post text",
            video_urls=["url1", "url2", "url3"]
        )
        
        result = fetch_video_transcripts(post)
        
        assert "[Video 2 transcript]" in result
        assert "Second video works." in result
        assert "[Video 1 transcript]" not in result
        assert "[Video 3 transcript]" not in result


class TestBuildUserPromptWithTranscript:
    """Tests for build_user_prompt with transcript text."""

    def test_prompt_includes_transcript(self):
        """Should append transcript text to the prompt."""
        post = PostData(
            url="https://tiktok.com/@user/video/123",
            platform="tiktok",
            text="Check out this video!"
        )
        policies = "Be kind to others."
        transcript = "\n\n[Video 1 transcript]\nHello world!"
        
        result = build_user_prompt(post, policies, transcript)
        
        assert "[Video 1 transcript]" in result
        assert "Hello world!" in result

    def test_prompt_without_transcript(self):
        """Should work without transcript text."""
        post = PostData(
            url="https://reddit.com/r/test/comments/abc/post",
            platform="reddit",
            text="Text only post"
        )
        policies = "Follow the rules."
        
        result = build_user_prompt(post, policies)
        
        assert "Text only post" in result
        assert "Follow the rules" in result
        assert "[Video" not in result


class TestBuildMessageContentWithTranscript:
    """Tests for build_message_content integration with transcripts."""

    @patch("core.judge.fetch_video_transcripts")
    def test_text_only_with_transcript(self, mock_fetch_transcripts):
        """Should include transcript in text-only content."""
        mock_fetch_transcripts.return_value = "\n\n[Video 1 transcript]\nSpoken words here."
        
        post = PostData(
            url="https://tiktok.com/@user/video/123",
            platform="tiktok",
            text="Caption",
            image_urls=[],
            video_urls=["https://tiktok.com/@user/video/123"]
        )
        
        result = build_message_content(post, "Policies here")
        
        # Should be a string (text-only, no images)
        assert isinstance(result, str)
        assert "[Video 1 transcript]" in result
        assert "Spoken words here." in result

    @patch("core.judge.fetch_video_transcripts")
    @patch("core.judge.fetch_image_as_base64")
    def test_multimodal_with_transcript(self, mock_fetch_image, mock_fetch_transcripts):
        """Should include transcript in multimodal content with images."""
        mock_fetch_transcripts.return_value = "\n\n[Video 1 transcript]\nAudio content."
        mock_fetch_image.return_value = ("base64data", "image/jpeg")
        
        post = PostData(
            url="https://reddit.com/r/test/comments/abc/post",
            platform="reddit",
            text="Post with image and video",
            image_urls=["https://i.redd.it/image.jpg"],
            video_urls=["https://v.redd.it/video"]
        )
        
        result = build_message_content(post, "Policies")
        
        # Should be a list (multimodal with images)
        assert isinstance(result, list)
        # Last block should be the text with transcript
        text_block = result[-1]
        assert text_block["type"] == "text"
        assert "[Video 1 transcript]" in text_block["text"]
        assert "Audio content." in text_block["text"]


class TestSystemPromptVideoRule:
    """Tests for system prompt video transcript rule."""

    def test_system_prompt_has_rule_7(self):
        """Should include rule 7 for video transcript analysis."""
        assert "7." in SYSTEM_PROMPT
        assert "video transcript" in SYSTEM_PROMPT.lower()
        assert "[Video transcript:" in SYSTEM_PROMPT

    def test_system_prompt_transcript_quote_format(self):
        """Should specify the quote format for transcript violations."""
        assert "\"[Video transcript: 'exact words spoken here']\"" in SYSTEM_PROMPT
