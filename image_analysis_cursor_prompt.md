# Add Image Analysis to Content Moderation Pipeline

## Goal
Extend the existing Claude-based moderation pipeline to analyze images attached to posts, not just text. Claude natively handles images — no OCR, no external vision APIs, no new dependencies.

---

## 1. Update `core/models.py` — Add `image_urls` to `PostData`

Add an `image_urls` field to the `PostData` dataclass:

```python
image_urls: list[str] = field(default_factory=list)
```

---

## 2. Create `core/image_fetcher.py`

Create a new utility module that downloads images and returns base64-encoded data:

- Download image bytes via `requests.get` with the existing `SCRAPER_TIMEOUT_SECONDS` and `SCRAPER_USER_AGENT` config values
- Enforce a **5MB max size** per image (check `Content-Length` header before downloading, then verify after)
- Detect `media_type` from the `Content-Type` response header; fall back to URL file extension (`.jpg/.jpeg → image/jpeg`, `.png → image/png`, `.webp → image/webp`, `.gif → image/gif`)
- Return a `(base64_string, media_type)` tuple
- Raise `ScrapingError` on HTTP errors or oversized images
- Define constants: `MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024` and `MAX_IMAGES_PER_POST = 20`

---

## 3. Update `config.py`

Add cost-control constants:

```python
MAX_IMAGES_PER_POST = 20      # Claude's hard ceiling
PREFERRED_MAX_IMAGES = 4      # Practical limit for cost control
```

---

## 4. Update Adapters — Populate `image_urls` in `PostData`

### Reddit adapter
Extract image URLs from the raw post JSON:
- **Single image post**: if `post_hint == "image"`, append `post["url"]`
- **Gallery post**: if `is_gallery` is true and `media_metadata` exists, iterate entries and extract `media["s"]["u"]` (unescape `&amp;` → `&`) for each valid entry
- **Preview image fallback**: if `preview.images` exists, extract `preview["images"][0]["source"]["url"]` (unescape `&amp;`)

### TikTok adapter
Extract the `og:image` meta tag from the scraped HTML:
```python
og_image = soup.find("meta", property="og:image")
if og_image and og_image.get("content"):
    image_urls = [og_image["content"]]
```

### X (Twitter) adapter
Add `media.fields=url,type` to the API request and expand `attachments.media_keys`. Then extract:
```python
image_urls = [
    m["url"] for m in response_data.get("includes", {}).get("media", [])
    if m.get("type") in ("photo", "animated_gif") and m.get("url")
]
```

---

## 5. Update `core/judge.py` — Build Multimodal Messages

Add a `build_message_content(post, policies_text)` function:

- If `post.image_urls` is empty, return the existing plain-text prompt string (no change to current behaviour)
- If images are present, build a list of content blocks:
  1. For each URL in `post.image_urls[:PREFERRED_MAX_IMAGES]`, call `fetch_image_as_base64` and append an `{"type": "image", "source": {"type": "base64", "media_type": ..., "data": ...}}` block. Catch `ScrapingError` and track skipped images.
  2. Append the text prompt as the final block: `{"type": "text", "text": prompt_text}`
  3. If any images were skipped, append a note to the prompt text before adding it
- Update the `judge()` function to pass the result of `build_message_content` as the `content` value in `client.messages.create`

---

## 6. Update the System Prompt

Append this rule to the existing system prompt:

```
6. If images are provided, analyze them with the same rigor as the text.
   Violations found in images are just as serious as violations in text.
   In the "quote" field for image violations, describe what you saw instead
   of quoting text, e.g.: "[Image 1: hate symbol displayed prominently in center of image]"
```

---

## What Claude flags in images
- Text baked into memes (slurs, threats)
- Hate symbols, nazi imagery, terrorist flags
- Graphic violence or gore
- Nudity / sexual content
- Weapons in threatening context
- Screenshots of other posts (Claude reads those too)
- Misinformation infographics

---

## Output format — image violations

Image violations use the same JSON shape as text violations; only `quote` differs:

```json
{
  "rule": "Hate Speech",
  "severity": "HIGH",
  "explanation": "Image contains a well-known white supremacist symbol.",
  "policy_reference": "Reddit Content Policy — Hate Speech",
  "quote": "[Image 1: hate symbol displayed prominently in center of image]"
}
```

---

## What NOT to add
- No Tesseract / OCR
- No external vision API
- No image preprocessing or resizing
- No new pip dependencies (only `base64` stdlib + `requests`, already present)

---

## Implementation order

1. Add `image_urls` to `PostData` in `core/models.py`
2. Create `core/image_fetcher.py`
3. Add constants to `config.py`
4. Update Reddit adapter
5. Update `core/judge.py` with multimodal message builder
6. Update system prompt
7. Test with a Reddit image post
8. Update X and TikTok adapters
