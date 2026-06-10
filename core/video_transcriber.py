"""
Video transcriber for extracting and transcribing audio from video URLs.
Uses yt-dlp for audio extraction and OpenAI Whisper API for transcription.
"""
import os
import tempfile
from typing import Optional

import yt_dlp
from openai import OpenAI

from config import WHISPER_MAX_FILE_SIZE_BYTES, MAX_TRANSCRIPT_LENGTH_CHARS


def transcribe_video(video_url: str) -> Optional[str]:
    """
    Download audio from video_url using yt-dlp and transcribe with OpenAI Whisper.
    
    Args:
        video_url: URL of the video to transcribe
        
    Returns:
        Transcript text on success, None on any failure.
        Never raises - all errors are caught and result in None.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = _download_audio(video_url, tmpdir)
            if audio_path is None:
                return None

            if os.path.getsize(audio_path) > WHISPER_MAX_FILE_SIZE_BYTES:
                return None

            return _transcribe(audio_path)
    except Exception:
        return None


def _download_audio(video_url: str, output_dir: str) -> Optional[str]:
    """
    Download audio-only from video_url into output_dir.
    
    Args:
        video_url: URL of the video
        output_dir: Directory to save the audio file
        
    Returns:
        File path on success, None on failure.
    """
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": f"{output_dir}/audio.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "64",
        }],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
    except Exception:
        return None

    for fname in os.listdir(output_dir):
        if fname.startswith("audio."):
            return os.path.join(output_dir, fname)

    return None


def _transcribe(audio_path: str) -> Optional[str]:
    """
    Send audio file to OpenAI Whisper API and return transcript text.
    
    Args:
        audio_path: Path to the audio file
        
    Returns:
        Transcript text on success, None on failure.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    
    try:
        client = OpenAI(api_key=api_key)

        with open(audio_path, "rb") as audio_file:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )

        transcript = response.strip() if isinstance(response, str) else response.text.strip()
        
        if not transcript:
            return None
            
        return transcript[:MAX_TRANSCRIPT_LENGTH_CHARS]
    except Exception:
        return None
