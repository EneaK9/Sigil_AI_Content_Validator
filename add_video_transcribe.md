# Add Video Transcription via yt-dlp + OpenAI Whisper

## Goal
When a post contains a video URL, download the audio with yt-dlp and transcribe it using the OpenAI Whisper API. Append the transcript to the Claude prompt as plain text. If transcription fails for any reason, silently fall back to analyzing text and images only.

---

## New Dependencies

Add to `requirements.txt`:
```
yt-dlp
openai
```

---

## 1. Update `core/models.py` — Add `video_urls` to `PostData`

Add alongside the existing `image_urls` field:

```python
video_urls: list[str] = field(default_factory=list)
```

---

## 2. Update `config.py`

```python
MAX_CAPTION_LENGTH_CHARS = 5000   # Truncate long transcripts to control token cost
WHISPER_MAX_FILE_SIZE_BYTES = 24 * 1024 * 1024  # 24MB — just under OpenAI's 25MB limit
```

---

## 3. Create `core/video_transcriber.py`

This module takes a video URL, downloads audio-only with yt-dlp, sends it to Whisper, and returns a transcript string or `None`.

```python
import os
import tempfile
import yt_dlp
from openai import OpenAI

from config import WHISPER_MAX_FILE_SIZE_BYTES, MAX_CAPTION_LENGTH_CHARS


def transcribe_video(video_url: str) -> str | None:
    """
    Download audio from video_url using yt-dlp and transcribe with OpenAI Whisper.
    Returns transcript text on success, None on any failure.
    Never raises.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = _download_audio(video_url, tmpdir)
            if audio_path is None:
                return None

            if os.path.getsize(audio_path) > WHISPER_MAX_FILE_SIZE_BYTES:
                return None  # File too large for Whisper API

            return _transcribe(audio_path)
    except Exception:
        return None


def _download_audio(video_url: str, output_dir: str) -> str | None:
    """
    Download audio-only from video_url into output_dir.
    Returns the file path on success, None on failure.
    """
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": f"{output_dir}/audio.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "64",  # Low quality — we only need intelligible speech
        }],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
    except Exception:
        return None

    # Find the downloaded file
    for fname in os.listdir(output_dir):
        if fname.startswith("audio."):
            return os.path.join(output_dir, fname)

    return None


def _transcribe(audio_path: str) -> str | None:
    """
    Send audio file to OpenAI Whisper API and return transcript text.
    """
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    with open(audio_path, "rb") as audio_file:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text"
        )

    transcript = response.strip() if isinstance(response, str) else response.text.strip()
    return transcript[:MAX_CAPTION_LENGTH_CHARS] if transcript else None
```

---

## 4. Update Adapters — Populate `video_urls` in `PostData`

Each adapter already returns `PostData`. Now they also populate `video_urls`.

### Reddit adapter
```python
# Video posts
if post.get("is_video") and post.get("media", {}).get("reddit_video", {}).get("fallback_url"):
    video_urls = [post["media"]["reddit_video"]["fallback_url"]]
```

### TikTok adapter
```python
# TikTok post URL is the video itself — pass it directly
video_urls = [post_url]
```

### X adapter
```python
# Extract from media expansions (same API call used for images)
video_urls = [
    m["url"] for m in response_data.get("includes", {}).get("media", [])
    if m.get("type") == "video" and m.get("url")
]
```

---

## 5. Update `core/judge.py` — Fetch and Append Transcripts

Add a helper to fetch transcripts for all video URLs on a post:

```python
from core.video_transcriber import transcribe_video

def fetch_video_transcripts(post: PostData) -> str:
    """
    Transcribe each video URL. Returns a formatted string to append
    to the prompt, or empty string if nothing was transcribed.
    """
    transcripts = []
    for i, video_url in enumerate(post.video_urls, 1):
        transcript = transcribe_video(video_url)
        if transcript:
            transcripts.append(f"[Video {i} transcript]\n{transcript}")

    if not transcripts:
        return ""

    return "\n\n" + "\n\n".join(transcripts)
```

Update `build_user_prompt` (or wherever the prompt text is assembled) to append transcripts:

```python
transcript_text = fetch_video_transcripts(post)
prompt = existing_prompt_text + transcript_text
```

No changes needed to the multimodal content builder — transcripts are plain text.

---

## 6. Update the System Prompt

Append to the existing rules:

```
7. If a video transcript is provided, analyze it with the same rigor as the post text.
   Violations found in transcripts are just as serious as violations in text.
   In the "quote" field for transcript violations, include the relevant excerpt and label it,
   e.g.: "[Video transcript: 'exact words spoken here']"
```

---

## Failure behaviour

`transcribe_video` must **never raise**. The outer try/except in the function covers everything. If it returns `None`, the post proceeds with text and image analysis only — no error, no flag, no log noise.

Optionally log at debug level:
```python
logger.debug(f"Video transcription skipped for: {video_url}")
```

---

## Output JSON — transcript violations

```json
{
  "rule": "Hate Speech",
  "severity": "HIGH",
  "explanation": "Speaker uses a racial slur while threatening a group.",
  "policy_reference": "TikTok Community Guidelines — Hate Speech",
  "quote": "[Video transcript: 'exact words spoken here']"
}
```

---

## What NOT to add
- No local Whisper model
- No ffmpeg called directly — yt-dlp handles it internally via its postprocessor
- No per-platform download logic — yt-dlp handles all platforms uniformly

---

## Implementation order

1. Add `yt-dlp` and `openai` to `requirements.txt`
2. Add constants to `config.py`
3. Add `video_urls` to `PostData` in `core/models.py`
4. Create `core/video_transcriber.py`
5. Update Reddit, TikTok, and X adapters to populate `video_urls`
6. Update `core/judge.py` to fetch and append transcripts
7. Update system prompt
8. Test with a public TikTok or X video URL
9. Test with an invalid/private URL — confirm clean fallback with no crash