"""
PolicyGuard configuration constants.
All configuration values live here - never hardcode values in modules.
"""
from pathlib import Path

# Claude API
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_MAX_TOKENS = 2000

# OpenAI API
OPENAI_MODEL = "gpt-4o"
OPENAI_MAX_TOKENS = 2000

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
SUPPORTED_PLATFORMS = ["reddit", "x", "tiktok", "facebook", "instagram", "linkedin"]
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
    "linkedin": ["linkedin_community.md", "linkedin_tos.md"],
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
    "linkedin": ["linkedin.com/posts/", "linkedin.com/feed/"],
}

# API settings
API_VERSION = "1.0.0"
API_HOST = "0.0.0.0"
API_PORT = 8000
MAX_CONCURRENT_CHECKS = 10  # Parallel Claude API calls for batch processing
JOB_EXPIRY_HOURS = 24       # Clean up completed jobs after this time

# Bot Detection Configuration
BOT_SIGNAL_WEIGHTS = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 5,
}

BOT_VERDICT_THRESHOLDS = {
    "BOT": {"min_score": 10, "min_signals": 4},
    "SUSPICIOUS": {"min_score": 5, "min_signals": 2},
}

# Immediate BOT patterns - if ALL signals in a tuple trigger, verdict is BOT regardless of score
BOT_IMMEDIATE_PATTERNS = {
    "x": [
        ("tweet_count_lt_5", "account_age_lt_30", "following_gt_4900"),
    ],
    "tiktok": [
        ("video_count_zero", "followers_gt_10000"),
    ],
    "instagram": [
        ("media_count_zero", "followers_gt_5000", "bio_spam"),
    ],
    "facebook": [
        ("created_lt_30_days", "followers_gt_10000", "link_only_posts"),
    ],
    "reddit": [
        ("karma_farm_subs", "template_comments", "account_age_lt_7"),
    ],
}

# Bio spam detection terms
BOT_BIO_SPAM_TERMS = [
    "telegram", "whatsapp", "dm for", "crypto", "nft", "invest",
    "forex", "bitcoin", "earn money", "passive income", "link in bio",
]

# Known karma farming subreddits
REDDIT_KARMA_FARM_SUBS = [
    "freekarma4u", "freekarma4you", "karma", "karmawhore",
    "freekarma", "karmafarming", "upvote4upvote",
]

# Automation sources that indicate bot behavior (X/Twitter)
BOT_AUTOMATION_SOURCES = {
    "IFTTT", "Zapier", "Buffer API", "Hootsuite", "dlvr.it",
    "TweetDeck", "SocialFlow", "Sprout Social",
}
