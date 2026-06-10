"""
PolicyGuard configuration constants.
All configuration values live here - never hardcode values in modules.
"""
from pathlib import Path

# Claude API
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_MAX_TOKENS = 2000

# Scraper settings
SCRAPER_TIMEOUT_SECONDS = 10
SCRAPER_USER_AGENT = "Mozilla/5.0 (compatible; PolicyGuard/1.0; policy compliance research)"

# Reddit adapter
REDDIT_USER_AGENT = "PolicyGuard/1.0 (policy compliance research tool)"

# Paths
BASE_DIR = Path(__file__).parent
POLICIES_DIR = BASE_DIR / "policies"
DEBUG_DIR = BASE_DIR / "debug"

# Platforms
SUPPORTED_PLATFORMS = ["reddit", "x", "tiktok", "facebook", "instagram"]
AUTO_SCRAPE_PLATFORMS = ["reddit", "x", "tiktok"]

# Policy sources for scraping
POLICY_SOURCES = {
    "facebook_community": "https://transparency.meta.com/policies/community-standards",
    "facebook_tos": "https://www.facebook.com/terms",
    "instagram_community": "https://help.instagram.com/581066165581870",
    "instagram_tos": "https://help.instagram.com/581066165581870",
    "x_rules": "https://help.x.com/en/rules-and-policies",
    "x_tos": "https://x.com/en/tos",
    "tiktok_community": "https://www.tiktok.com/safety/en-GB/policies-and-engagement/overview",
    "tiktok_tos": "https://www.tiktok.com/legal/page/row/terms-of-service/en",
    "reddit_content_policy": "https://redditinc.com/policies/reddit-rules",
    "reddit_user_agreement": "https://redditinc.com/policies/user-agreement",
}

# Platform to policy files mapping
PLATFORM_POLICY_FILES = {
    "facebook": ["facebook_community.md", "facebook_tos.md"],
    "instagram": ["instagram_community.md", "instagram_tos.md"],
    "x": ["x_rules.md", "x_tos.md"],
    "tiktok": ["tiktok_community.md", "tiktok_tos.md"],
    "reddit": ["reddit_content_policy.md", "reddit_user_agreement.md"],
}

# Image analysis
MAX_IMAGES_PER_POST = 20       # Claude's hard ceiling
PREFERRED_MAX_IMAGES = 4       # Practical limit for cost control
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB per image

# Video transcription
MAX_TRANSCRIPT_LENGTH_CHARS = 5000   # Truncate long transcripts to control token cost
WHISPER_MAX_FILE_SIZE_BYTES = 24 * 1024 * 1024  # 24MB - under OpenAI's 25MB limit

# Platform URL patterns for detection
PLATFORM_PATTERNS = {
    "reddit": ["reddit.com/r/", "redd.it/"],
    "x": ["x.com/", "twitter.com/"],
    "tiktok": ["tiktok.com/@", "vm.tiktok.com/"],
    "facebook": ["facebook.com/", "fb.com/", "fb.watch/"],
    "instagram": ["instagram.com/p/", "instagram.com/reel/"],
}

# API settings
API_VERSION = "1.0.0"
API_HOST = "0.0.0.0"
API_PORT = 8000
MAX_CONCURRENT_CHECKS = 10  # Parallel Claude API calls for batch processing
JOB_EXPIRY_HOURS = 24       # Clean up completed jobs after this time
