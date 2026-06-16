"""
Pydantic models for API request validation.
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class PostInput(BaseModel):
    """
    Input model for a single post to analyze.
    Matches the JSON contract from the CLI.
    """
    url: str = Field(..., description="Post URL (used for platform detection)")
    message: str = Field(..., description="Post text content")
    post_id: Optional[str] = Field(None, description="Platform-specific post identifier")
    type: Optional[str] = Field(None, description="Post type (e.g., 'post', 'reel', 'story')")
    timestamp: Optional[int] = Field(None, description="Unix timestamp of post creation")
    reactions_count: Optional[int] = Field(None, description="Number of reactions/likes")
    comments_count: Optional[int] = Field(None, description="Number of comments")
    reshare_count: Optional[int] = Field(None, description="Number of shares/reposts")
    author_name: Optional[str] = Field(None, alias="author.name", description="Author's display name")
    author_url: Optional[str] = Field(None, alias="author.url", description="Author's profile URL")
    image_uri: Optional[str] = Field(None, alias="image.uri", description="Direct URL to post image")
    video: Optional[str] = Field(None, description="Direct URL to post video")
    video_transcript: Optional[str] = Field(None, description="Pre-transcribed video audio")
    external_url: Optional[str] = Field(None, description="External link in the post")

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "url": "https://www.facebook.com/permalink.php?story_fbid=abc&id=123",
                "message": "Check out this amazing post!",
                "author.name": "John Doe",
                "image.uri": "https://example.com/image.jpg",
                "video": None,
                "video_transcript": None
            }
        }
    }


class BatchInput(BaseModel):
    """
    Input model for batch processing multiple posts.
    """
    posts: List[PostInput] = Field(..., description="Array of posts to analyze", min_length=1)

    model_config = {
        "json_schema_extra": {
            "example": {
                "posts": [
                    {"url": "https://facebook.com/post/1", "message": "First post"},
                    {"url": "https://facebook.com/post/2", "message": "Second post"}
                ]
            }
        }
    }


class RecheckInput(BaseModel):
    """
    Input model for re-checking the availability of previously-seen posts.

    Used by report-result monitoring: given the URLs of flagged posts, re-visit
    each and report whether it is still live, removed, or restricted.
    """
    urls: List[str] = Field(
        ...,
        description="Post URLs to re-check",
        min_length=1,
        max_length=100,  # bound the batch so a single request can't fan out unboundedly
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "urls": [
                    "https://x.com/user/status/123456789",
                    "https://reddit.com/r/sub/comments/abc/title",
                ]
            }
        }
    }
