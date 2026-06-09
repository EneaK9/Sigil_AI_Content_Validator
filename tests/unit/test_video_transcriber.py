"""
Unit tests for core/video_transcriber.py - Video transcription functionality.
"""
import os
import pytest
from unittest.mock import patch, MagicMock

from core.video_transcriber import (
    transcribe_video,
    _download_audio,
    _transcribe,
)


class TestTranscribeVideo:
    """Tests for the main transcribe_video function."""

    @patch("core.video_transcriber._download_audio")
    @patch("core.video_transcriber._transcribe")
    @patch("os.path.getsize")
    def test_successful_transcription(self, mock_getsize, mock_transcribe, mock_download):
        """Should return transcript on successful download and transcription."""
        mock_download.return_value = "/tmp/audio.mp3"
        mock_getsize.return_value = 1000  # Small file
        mock_transcribe.return_value = "This is the transcribed text."
        
        result = transcribe_video("https://example.com/video")
        
        assert result == "This is the transcribed text."
        mock_download.assert_called_once()
        mock_transcribe.assert_called_once_with("/tmp/audio.mp3")

    @patch("core.video_transcriber._download_audio")
    def test_download_failure_returns_none(self, mock_download):
        """Should return None when download fails."""
        mock_download.return_value = None
        
        result = transcribe_video("https://example.com/video")
        
        assert result is None

    @patch("core.video_transcriber._download_audio")
    @patch("os.path.getsize")
    def test_file_too_large_returns_none(self, mock_getsize, mock_download):
        """Should return None when audio file exceeds size limit."""
        mock_download.return_value = "/tmp/audio.mp3"
        mock_getsize.return_value = 30 * 1024 * 1024  # 30MB, over limit
        
        result = transcribe_video("https://example.com/video")
        
        assert result is None

    @patch("core.video_transcriber._download_audio")
    @patch("core.video_transcriber._transcribe")
    @patch("os.path.getsize")
    def test_transcription_failure_returns_none(self, mock_getsize, mock_transcribe, mock_download):
        """Should return None when transcription fails."""
        mock_download.return_value = "/tmp/audio.mp3"
        mock_getsize.return_value = 1000
        mock_transcribe.return_value = None
        
        result = transcribe_video("https://example.com/video")
        
        assert result is None

    def test_exception_returns_none(self):
        """Should return None on any exception (never raises)."""
        with patch("core.video_transcriber._download_audio", side_effect=Exception("Boom")):
            result = transcribe_video("https://example.com/video")
            assert result is None


class TestDownloadAudio:
    """Tests for the _download_audio helper function."""

    @patch("core.video_transcriber.yt_dlp.YoutubeDL")
    @patch("os.listdir")
    def test_successful_download(self, mock_listdir, mock_ydl_class):
        """Should return audio file path on successful download."""
        mock_ydl = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl
        mock_listdir.return_value = ["audio.mp3"]
        
        result = _download_audio("https://example.com/video", "/tmp/output")
        
        assert result == "/tmp/output/audio.mp3"
        mock_ydl.download.assert_called_once_with(["https://example.com/video"])

    @patch("core.video_transcriber.yt_dlp.YoutubeDL")
    def test_download_exception_returns_none(self, mock_ydl_class):
        """Should return None when yt-dlp raises exception."""
        mock_ydl = MagicMock()
        mock_ydl.download.side_effect = Exception("Download failed")
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl
        
        result = _download_audio("https://example.com/video", "/tmp/output")
        
        assert result is None

    @patch("core.video_transcriber.yt_dlp.YoutubeDL")
    @patch("os.listdir")
    def test_no_audio_file_returns_none(self, mock_listdir, mock_ydl_class):
        """Should return None when no audio file is found after download."""
        mock_ydl = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl
        mock_listdir.return_value = ["other.txt"]  # No audio file
        
        result = _download_audio("https://example.com/video", "/tmp/output")
        
        assert result is None


class TestTranscribeHelper:
    """Tests for the _transcribe helper function."""

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("core.video_transcriber.OpenAI")
    @patch("builtins.open", create=True)
    def test_successful_transcription(self, mock_open, mock_openai_class):
        """Should return transcript text on successful API call."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = "Hello, this is the transcript."
        mock_open.return_value.__enter__.return_value = MagicMock()
        
        result = _transcribe("/tmp/audio.mp3")
        
        assert result == "Hello, this is the transcript."

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key_returns_none(self):
        """Should return None when OPENAI_API_KEY is not set."""
        # Ensure the key is not set
        if "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]
        
        result = _transcribe("/tmp/audio.mp3")
        
        assert result is None

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("core.video_transcriber.OpenAI")
    @patch("builtins.open", create=True)
    def test_api_exception_returns_none(self, mock_open, mock_openai_class):
        """Should return None when OpenAI API raises exception."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.audio.transcriptions.create.side_effect = Exception("API error")
        mock_open.return_value.__enter__.return_value = MagicMock()
        
        result = _transcribe("/tmp/audio.mp3")
        
        assert result is None

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("core.video_transcriber.OpenAI")
    @patch("builtins.open", create=True)
    def test_empty_transcript_returns_none(self, mock_open, mock_openai_class):
        """Should return None when transcript is empty."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = "   "  # Whitespace only
        mock_open.return_value.__enter__.return_value = MagicMock()
        
        result = _transcribe("/tmp/audio.mp3")
        
        assert result is None

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("core.video_transcriber.OpenAI")
    @patch("builtins.open", create=True)
    def test_long_transcript_truncated(self, mock_open, mock_openai_class):
        """Should truncate transcripts longer than MAX_TRANSCRIPT_LENGTH_CHARS."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        # Create a transcript longer than 5000 chars
        long_transcript = "A" * 10000
        mock_client.audio.transcriptions.create.return_value = long_transcript
        mock_open.return_value.__enter__.return_value = MagicMock()
        
        result = _transcribe("/tmp/audio.mp3")
        
        assert len(result) == 5000  # Truncated to MAX_TRANSCRIPT_LENGTH_CHARS
