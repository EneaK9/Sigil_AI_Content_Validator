"""
JSON input parser for PolicyGuard.

Parses pre-extracted post data in JSON format and converts to PostData objects.
Supports both single posts and batch arrays.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from core.detector import detect_platform
from core.models import PostData


class JsonInputError(Exception):
    """Raised when JSON input is invalid or missing required fields."""
    pass


def parse_json_post(data: dict) -> tuple[PostData, Optional[str]]:
    """
    Parse a single JSON post object into PostData.
    
    Args:
        data: Dict with post data following the JSON contract
        
    Returns:
        Tuple of (PostData, video_transcript or None)
        
    Raises:
        JsonInputError: If required fields are missing or invalid
    """
    # Validate required fields
    if "url" not in data:
        raise JsonInputError("Missing required field 'url' in JSON input")
    if "message" not in data:
        raise JsonInputError("Missing required field 'message' in JSON input")
    
    url = data["url"]
    message = data["message"]
    
    if not isinstance(url, str) or not url.strip():
        raise JsonInputError("Field 'url' must be a non-empty string")
    if not isinstance(message, str):
        raise JsonInputError("Field 'message' must be a string")
    
    # Detect platform from URL
    try:
        platform = detect_platform(url)
    except ValueError as e:
        raise JsonInputError(f"Could not detect platform from URL: {e}")
    
    # Extract optional fields
    author = data.get("author.name", "") or ""
    title = data.get("title", "") or ""
    
    # Handle image URLs - can be string or null
    image_urls = []
    image_uri = data.get("image.uri")
    if image_uri and isinstance(image_uri, str):
        image_urls.append(image_uri)
    
    # Handle video URLs - can be string or null
    video_urls = []
    video = data.get("video")
    if video and isinstance(video, str):
        video_urls.append(video)
    
    # Extract video transcript if provided
    video_transcript = data.get("video_transcript")
    if video_transcript is not None and not isinstance(video_transcript, str):
        video_transcript = None
    
    # Build PostData
    post = PostData(
        url=url,
        platform=platform,
        text=message,
        author=author,
        title=title,
        image_urls=image_urls,
        video_urls=video_urls,
        scraped_at=datetime.now(timezone.utc).isoformat()
    )
    
    return post, video_transcript


def parse_json_input(json_str: str) -> list[tuple[PostData, Optional[str]]]:
    """
    Parse JSON input string into list of (PostData, video_transcript) tuples.
    
    Supports both single object and array of objects.
    
    Args:
        json_str: JSON string (single object or array)
        
    Returns:
        List of (PostData, video_transcript) tuples
        
    Raises:
        JsonInputError: If JSON is invalid or missing required fields
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise JsonInputError(f"Invalid JSON: {e}")
    
    # Handle both single object and array
    if isinstance(data, dict):
        posts = [data]
    elif isinstance(data, list):
        if not data:
            raise JsonInputError("Empty array provided")
        posts = data
    else:
        raise JsonInputError("JSON must be an object or array of objects")
    
    results = []
    for i, post_data in enumerate(posts):
        if not isinstance(post_data, dict):
            raise JsonInputError(f"Item {i} is not a JSON object")
        try:
            result = parse_json_post(post_data)
            results.append(result)
        except JsonInputError as e:
            raise JsonInputError(f"Item {i}: {e}")
    
    return results


def load_json_file(file_path: str) -> list[tuple[PostData, Optional[str]]]:
    """
    Load and parse JSON from a file.
    
    Args:
        file_path: Path to JSON file
        
    Returns:
        List of (PostData, video_transcript) tuples
        
    Raises:
        JsonInputError: If file cannot be read or JSON is invalid
    """
    path = Path(file_path)
    if not path.exists():
        raise JsonInputError(f"File not found: {file_path}")
    
    try:
        content = path.read_text(encoding="utf-8")
    except IOError as e:
        raise JsonInputError(f"Cannot read file: {e}")
    
    return parse_json_input(content)


def load_json_stdin() -> list[tuple[PostData, Optional[str]]]:
    """
    Load and parse JSON from stdin.
    
    Returns:
        List of (PostData, video_transcript) tuples
        
    Raises:
        JsonInputError: If stdin is empty or JSON is invalid
    """
    if sys.stdin.isatty():
        raise JsonInputError("No JSON data provided via stdin")
    
    content = sys.stdin.read()
    if not content.strip():
        raise JsonInputError("Empty input from stdin")
    
    return parse_json_input(content)
