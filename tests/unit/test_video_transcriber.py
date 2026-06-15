"""Unit tests for sigil.validation.video_transcriber."""
from unittest.mock import MagicMock, patch

import pytest

from sigil.config import get_settings
from sigil.validation.video_transcriber import (
    _download_audio,
    _transcribe,
    transcribe_video,
)

MODULE = "sigil.validation.video_transcriber"


class TestTranscribeVideo:
    @patch(f"{MODULE}._download_audio")
    @patch(f"{MODULE}._transcribe")
    @patch("os.path.getsize")
    def test_success(self, mock_getsize, mock_transcribe, mock_download):
        mock_download.return_value = "/tmp/audio.mp3"
        mock_getsize.return_value = 1000
        mock_transcribe.return_value = "transcribed text"
        assert transcribe_video("https://example.com/video") == "transcribed text"

    @patch(f"{MODULE}._download_audio", return_value=None)
    def test_download_failure_returns_none(self, _mock_download):
        assert transcribe_video("https://example.com/video") is None

    @patch(f"{MODULE}._download_audio", return_value="/tmp/audio.mp3")
    @patch("os.path.getsize", return_value=30 * 1024 * 1024)
    def test_file_too_large_returns_none(self, _size, _dl):
        assert transcribe_video("https://example.com/video") is None

    def test_exception_returns_none(self):
        with patch(f"{MODULE}._download_audio", side_effect=Exception("boom")):
            assert transcribe_video("https://example.com/video") is None


class TestDownloadAudio:
    @patch(f"{MODULE}.yt_dlp.YoutubeDL")
    @patch("os.listdir", return_value=["audio.mp3"])
    def test_success(self, _ls, mock_ydl_class):
        mock_ydl = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl
        assert _download_audio("u", "/tmp/output") == "/tmp/output/audio.mp3"

    @patch(f"{MODULE}.yt_dlp.YoutubeDL")
    def test_download_exception_returns_none(self, mock_ydl_class):
        mock_ydl = MagicMock()
        mock_ydl.download.side_effect = Exception("fail")
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl
        assert _download_audio("u", "/tmp/output") is None

    @patch(f"{MODULE}.yt_dlp.YoutubeDL")
    @patch("os.listdir", return_value=["other.txt"])
    def test_no_audio_file_returns_none(self, _ls, mock_ydl_class):
        mock_ydl_class.return_value.__enter__.return_value = MagicMock()
        assert _download_audio("u", "/tmp/output") is None


class TestTranscribeHelper:
    @pytest.fixture
    def with_openai_key(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "openai_api_key", "test-key")

    @patch(f"{MODULE}.OpenAI")
    @patch("builtins.open", create=True)
    def test_success(self, mock_open, mock_openai_class, with_openai_key):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = "the transcript"
        mock_open.return_value.__enter__.return_value = MagicMock()
        assert _transcribe("/tmp/audio.mp3") == "the transcript"

    def test_missing_api_key_returns_none(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "openai_api_key", None)
        assert _transcribe("/tmp/audio.mp3") is None

    @patch(f"{MODULE}.OpenAI")
    @patch("builtins.open", create=True)
    def test_api_exception_returns_none(self, mock_open, mock_openai_class, with_openai_key):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.audio.transcriptions.create.side_effect = Exception("api error")
        mock_open.return_value.__enter__.return_value = MagicMock()
        assert _transcribe("/tmp/audio.mp3") is None

    @patch(f"{MODULE}.OpenAI")
    @patch("builtins.open", create=True)
    def test_empty_transcript_returns_none(self, mock_open, mock_openai_class, with_openai_key):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = "   "
        mock_open.return_value.__enter__.return_value = MagicMock()
        assert _transcribe("/tmp/audio.mp3") is None

    @patch(f"{MODULE}.OpenAI")
    @patch("builtins.open", create=True)
    def test_long_transcript_truncated(self, mock_open, mock_openai_class, with_openai_key):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = "A" * 10000
        mock_open.return_value.__enter__.return_value = MagicMock()
        limit = get_settings().max_transcript_length_chars
        assert len(_transcribe("/tmp/audio.mp3")) == limit
