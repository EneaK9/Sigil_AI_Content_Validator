# PolicyGuard

**A comprehensive CLI tool for automated social media content policy compliance checking using Claude AI.**

PolicyGuard analyzes social media posts against platform-specific Community Guidelines and Terms of Service, returning detailed JSON verdicts that identify policy violations with precise explanations, severity levels, and actionable recommendations.

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   URL or    │────▶│   Fetch     │────▶│    Load     │────▶│   Claude    │────▶│    JSON     │
│    Text     │     │ Post+Images │     │  Policies   │     │   Judge     │     │   Verdict   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                          │                                        ▲
                          │ image_urls                             │ multimodal
                          ▼                                        │ message
                    ┌─────────────┐                                │
                    │   Fetch     │────────────────────────────────┘
                    │   Images    │   (base64 + media_type)
                    └─────────────┘
```

---

## Table of Contents

- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Basic Usage](#basic-usage)
  - [Advanced Options](#advanced-options)
  - [CLI Reference](#cli-reference)
- [Output Format](#output-format)
- [Image Analysis](#image-analysis)
- [Platform Support](#platform-support)
  - [Reddit](#reddit)
  - [X (Twitter)](#x-twitter)
  - [TikTok](#tiktok)
  - [Facebook](#facebook)
  - [Instagram](#instagram)
- [Policy Management](#policy-management)
- [How It Works](#how-it-works)
- [Error Handling](#error-handling)
- [Testing](#testing)
- [Extending PolicyGuard](#extending-policyguard)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- **Multi-Platform Support**: Reddit, X/Twitter, TikTok, Facebook, and Instagram
- **Automated Post Fetching**: Automatically scrapes post content from URLs (where supported)
- **Image Analysis**: Automatically extracts and analyzes images using Claude's vision capabilities
- **Manual Text Input**: Analyze any text against any platform's policies
- **Detailed Verdicts**: Get comprehensive JSON output with:
  - Pass/Fail verdict
  - List of violations with severity levels (HIGH/MEDIUM/LOW)
  - Exact quotes from the post that triggered violations (or image descriptions for visual violations)
  - Specific policy references
  - Confidence scores
  - Actionable recommendations
- **Policy Caching**: Platform policies are cached locally for fast, offline-capable analysis
- **Extensible Architecture**: Easy to add new platforms with the adapter pattern
- **Robust Error Handling**: Clear, actionable error messages for every failure mode
- **Comprehensive Test Suite**: 200+ tests covering unit, integration, and AI judgment quality

---

## Architecture Overview

PolicyGuard follows a modular architecture with clear separation of concerns:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              policyguard.py                                │
│                           (CLI Entry Point)                                │
└─────────────────────────────────┬──────────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
        ▼                         ▼                         ▼
┌───────────────┐       ┌─────────────────┐       ┌─────────────────┐
│    core/      │       │    adapters/    │       │    scrapers/    │
│  detector.py  │       │   reddit.py     │       │ policy_scraper  │
│   judge.py    │       │     x.py        │       │      .py        │
│  models.py    │       │   tiktok.py     │       └─────────────────┘
│policy_loader  │       │  facebook.py    │
│     .py       │       │ instagram.py    │
│image_fetcher  │       └─────────────────┘
│     .py       │
└───────────────┘
        │                         │
        │                         │
        ▼                         ▼
┌───────────────┐       ┌─────────────────┐
│   policies/   │       │  External APIs  │
│  (cached MD)  │       │ Reddit, X, etc. │
└───────────────┘       └─────────────────┘
```

### Core Principles

1. **One Claude call per post** - No RAG, no chunking. Full context in a single API call.
2. **Policies are cached** - Never fetched live during analysis. Separate `refresh` command.
3. **Per-platform adapters** - Fully isolated. One adapter breaking doesn't affect others.
4. **Structured JSON output** - Always returns parseable JSON, never markdown or prose.
5. **Fail loudly** - Every error says exactly what failed, why, and what to do next.
6. **No hidden state** - Everything is a file on disk or a return value.

---

## Installation

### Prerequisites

- Python 3.9 or higher
- An Anthropic API key ([get one here](https://console.anthropic.com/))
- (Optional) X/Twitter Bearer Token for X URL support

### Step-by-Step Installation

```bash
# 1. Clone the repository
git clone https://github.com/EneaK9/Sigil_AI_Content_Validator.git
cd Sigil_AI_Content_Validator

# 2. Create and activate a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env

# 5. Edit .env and add your API key
# ANTHROPIC_API_KEY=sk-ant-your-key-here

# 6. Initialize the policy cache (required before first use)
python policyguard.py refresh

# 7. Verify installation
python policyguard.py --help
```

### Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `anthropic` | ≥0.25.0 | Claude API client |
| `requests` | ≥2.31.0 | HTTP requests for scraping |
| `beautifulsoup4` | ≥4.12.0 | HTML parsing for policy scraping |
| `python-dotenv` | ≥1.0.0 | Environment variable management |

---

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Required - Your Anthropic API key
ANTHROPIC_API_KEY=sk-ant-api03-...

# Optional - Required only for X/Twitter URL support
X_BEARER_TOKEN=AAAA...
```

### Configuration File (`config.py`)

All constants are centralized in `config.py`:

```python
# Claude API settings
CLAUDE_MODEL = "claude-sonnet-4-20250514"  # Model to use
CLAUDE_MAX_TOKENS = 2000                    # Max response tokens

# Scraper settings
SCRAPER_TIMEOUT_SECONDS = 10               # HTTP timeout
SCRAPER_USER_AGENT = "Mozilla/5.0..."      # Browser user agent

# Paths
POLICIES_DIR = "policies"                  # Cached policy files
DEBUG_DIR = "debug"                        # Debug output

# Supported platforms
SUPPORTED_PLATFORMS = ["reddit", "x", "tiktok", "facebook", "instagram"]
AUTO_SCRAPE_PLATFORMS = ["reddit", "x", "tiktok"]  # Can auto-fetch posts
```

---

## Usage

### Basic Usage

#### Check a post by URL (auto-detect platform)

```bash
python policyguard.py check "https://www.reddit.com/r/worldnews/comments/abc123/post_title"
```

Output:
```
✓ Detected platform: reddit
✓ Post scraped from Reddit (author: u/username)
✓ Policies loaded for reddit (49,679 chars)
⚡ Sending to Claude for analysis...
{
  "verdict": "PASS",
  "platform": "reddit",
  "post_url": "https://www.reddit.com/r/...",
  ...
}
```

#### Check with manual text input

For platforms that can't be auto-scraped (Facebook, Instagram) or when you want to test specific text:

```bash
python policyguard.py check --platform reddit --text "I think this policy is unfair and should be changed."
```

#### Check Facebook/Instagram posts

```bash
# Copy the post text manually and use --text
python policyguard.py check --platform facebook --text "Paste the Facebook post content here"
python policyguard.py check --platform instagram --text "Paste the Instagram caption here"
```

### Advanced Options

#### Save output to file

```bash
python policyguard.py check "URL" --output result.json
# Creates result.json with the verdict
```

#### Quiet mode (JSON only)

Suppress status messages, output only the JSON verdict (useful for scripting):

```bash
python policyguard.py check "URL" --quiet
```

#### Combine options

```bash
python policyguard.py check --platform reddit --text "Some text" --output result.json --quiet
```

### CLI Reference

#### `check` - Analyze a post for policy violations

```
python policyguard.py check [URL] [OPTIONS]

Arguments:
  URL                    URL of the post to check (optional if using --text)

Options:
  -t, --text TEXT        Post text for manual input (requires --platform)
  -p, --platform NAME    Platform name: reddit, x, tiktok, facebook, instagram
  -o, --output FILE      Save JSON output to file
  -q, --quiet            Only print JSON, no status messages
  -h, --help             Show help message
```

**Examples:**

```bash
# Auto-detect from URL
python policyguard.py check "https://reddit.com/r/test/comments/abc/title"

# Manual text input
python policyguard.py check --platform x --text "Tweet content here"

# Save to file with quiet mode
python policyguard.py check "URL" -o result.json -q
```

#### `refresh` - Update cached policy files

```
python policyguard.py refresh [OPTIONS]

Options:
  -p, --platform NAME    Only refresh policies for this platform
  -h, --help             Show help message
```

**Examples:**

```bash
# Refresh all platforms
python policyguard.py refresh

# Refresh only Reddit policies
python policyguard.py refresh --platform reddit
```

**Output:**

```
Refreshing policy cache...

✓ Scraped reddit_content_policy → policies/reddit_content_policy.md (4,100 chars)
✓ Scraped reddit_user_agreement → policies/reddit_user_agreement.md (45,515 chars)
✗ FAILED facebook_community — HTTP 403. Skipping. Existing file preserved.
...

Policy refresh complete: 6/10 succeeded, 4 failed.
Failed: facebook_community, facebook_tos, instagram_community, instagram_tos
```

#### `show-policy` - Display cached policy

```
python policyguard.py show-policy PLATFORM

Arguments:
  PLATFORM               Platform name: reddit, x, tiktok, facebook, instagram
```

**Examples:**

```bash
# View Reddit policies
python policyguard.py show-policy reddit

# Pipe to less for easier reading
python policyguard.py show-policy reddit | less
```

---

## Output Format

### Verdict JSON Structure

Every `check` command returns a JSON object with this structure:

```json
{
  "verdict": "PASS | FAIL",
  "platform": "reddit | x | tiktok | facebook | instagram",
  "post_url": "https://...",
  "post_text": "The full text of the analyzed post...",
  "violations": [
    {
      "rule": "Name of the violated rule",
      "severity": "HIGH | MEDIUM | LOW",
      "explanation": "Plain English explanation of why this is a violation",
      "policy_reference": "Exact section name from the policy document",
      "quote": "Verbatim phrase from the post that triggered this"
    }
  ],
  "passed_checks": ["List", "of", "policy", "categories", "that", "passed"],
  "confidence": 0.0 - 1.0,
  "recommendation": "What should be changed (empty string if PASS)",
  "checked_at": "2024-01-15T10:30:00+00:00"
}
```

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `verdict` | string | `"PASS"` if no violations, `"FAIL"` if violations found |
| `platform` | string | Platform the post was analyzed against |
| `post_url` | string | Original URL or `"manual-input"` for --text |
| `post_text` | string | Full text that was analyzed |
| `violations` | array | List of violation objects (empty if PASS) |
| `passed_checks` | array | Policy categories that were checked and passed |
| `confidence` | float | 0.0-1.0 confidence score (higher = more certain) |
| `recommendation` | string | Suggested fix (empty if PASS) |
| `checked_at` | string | ISO 8601 timestamp of the analysis |

### Violation Object

| Field | Type | Description |
|-------|------|-------------|
| `rule` | string | Exact rule name from the platform's policies |
| `severity` | string | `"HIGH"`, `"MEDIUM"`, or `"LOW"` |
| `explanation` | string | Why this violates the policy |
| `policy_reference` | string | Specific policy section reference |
| `quote` | string | Exact text from the post that triggered this, or image description (e.g., `"[Image 1: ...]"`) for visual violations |

### Severity Levels

| Severity | Description | Examples |
|----------|-------------|----------|
| **HIGH** | Serious violations requiring immediate action | Direct threats, calls for violence, illegal content |
| **MEDIUM** | Significant violations | Hate speech, harassment, doxxing |
| **LOW** | Minor violations | Spam indicators, mild incivility |

### Confidence Scores

| Range | Meaning |
|-------|---------|
| 0.95+ | Very confident in the verdict |
| 0.80-0.94 | Confident, clear case |
| 0.60-0.79 | Moderate confidence, some ambiguity |
| Below 0.60 | Low confidence, borderline case |

### Example Outputs

#### Passing Post

```json
{
  "verdict": "PASS",
  "platform": "reddit",
  "post_url": "https://reddit.com/r/cooking/comments/abc/recipe",
  "post_text": "Here's my grandmother's recipe for apple pie...",
  "violations": [],
  "passed_checks": [
    "harassment/bullying",
    "hate speech",
    "threats of violence",
    "spam",
    "privacy violations",
    "illegal content"
  ],
  "confidence": 0.98,
  "recommendation": "",
  "checked_at": "2024-01-15T10:30:00+00:00"
}
```

#### Failing Post (Single Violation)

```json
{
  "verdict": "FAIL",
  "platform": "reddit",
  "post_url": "https://reddit.com/r/...",
  "post_text": "These people deserve to get hurt...",
  "violations": [
    {
      "rule": "Threats of Violence",
      "severity": "HIGH",
      "explanation": "The post explicitly calls for physical harm against a group of people, which violates Reddit's prohibition on content that threatens, incites, or glorifies violence.",
      "policy_reference": "Reddit Content Policy - Rule 1: Remember the human",
      "quote": "deserve to get hurt"
    }
  ],
  "passed_checks": [
    "spam",
    "privacy violations"
  ],
  "confidence": 0.96,
  "recommendation": "Remove the language calling for harm. Express disagreement without threatening violence.",
  "checked_at": "2024-01-15T10:31:00+00:00"
}
```

#### Failing Post (Multiple Violations)

```json
{
  "verdict": "FAIL",
  "platform": "reddit",
  "post_url": "manual-input",
  "post_text": "All [group] are criminals. Here's their address: 123 Main St...",
  "violations": [
    {
      "rule": "Hate Speech",
      "severity": "MEDIUM",
      "explanation": "Blanket negative characterization of an entire group constitutes hate speech.",
      "policy_reference": "Reddit Content Policy - Hate Speech",
      "quote": "All [group] are criminals"
    },
    {
      "rule": "Personal Information",
      "severity": "HIGH",
      "explanation": "Sharing someone's address without consent violates privacy policies.",
      "policy_reference": "Reddit Content Policy - Rule 3",
      "quote": "123 Main St"
    }
  ],
  "passed_checks": ["spam"],
  "confidence": 0.94,
  "recommendation": "Remove both the generalized hate speech and the personal address information.",
  "checked_at": "2024-01-15T10:32:00+00:00"
}
```

---

## Image Analysis

PolicyGuard automatically extracts and analyzes images from social media posts using Claude's native vision capabilities.

### How It Works

1. **Image Extraction**: When fetching a post, adapters extract image URLs:
   - **Reddit**: Single images, galleries, preview images
   - **X/Twitter**: Photos and animated GIFs from media attachments
   - **TikTok**: Video thumbnail (`og:image` meta tag)

2. **Image Fetching**: Images are downloaded and converted to base64:
   - Maximum image size: 5MB per image
   - Supported formats: JPEG, PNG, WebP, GIF
   - Up to 4 images analyzed by default (configurable)

3. **Multimodal Analysis**: Images are sent to Claude alongside post text:
   - Images receive the same policy scrutiny as text
   - Violations in images are reported with visual descriptions

### Image Violation Format

When a violation is found in an image, the `quote` field contains a description instead of text:

```json
{
  "rule": "Hate Symbols",
  "severity": "HIGH",
  "explanation": "The image displays a prohibited hate symbol, which violates the platform's policy against hateful imagery.",
  "policy_reference": "Community Guidelines - Hateful Conduct",
  "quote": "[Image 1: hate symbol displayed prominently in center of image]"
}
```

### Platform Image Support

| Platform | Image Types Extracted |
|----------|----------------------|
| Reddit | Direct images, galleries (up to 20 images), preview thumbnails |
| X/Twitter | Photo attachments, animated GIFs |
| TikTok | Video thumbnail only |
| Facebook | N/A (manual text input only) |
| Instagram | N/A (manual text input only) |

### Configuration

Image analysis settings in `config.py`:

```python
MAX_IMAGES_PER_POST = 20       # Claude's hard ceiling
PREFERRED_MAX_IMAGES = 4       # Default limit for cost control
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB per image
```

### Limitations

- **No video analysis**: Only static images and GIF thumbnails are analyzed
- **Cost consideration**: Each image adds to API costs; limit controlled by `PREFERRED_MAX_IMAGES`
- **Facebook/Instagram**: Images cannot be automatically extracted due to authentication walls
- **Failed image loads**: If an image fails to download, analysis continues with remaining content and a note is added

---

## Platform Support

### Overview

| Platform | Auto-Fetch | Manual Text | Image Analysis | API/Method | Notes |
|----------|------------|-------------|----------------|------------|-------|
| Reddit | ✅ Yes | ✅ Yes | ✅ Yes | Public `.json` endpoint | No auth required |
| X/Twitter | ✅ Yes | ✅ Yes | ✅ Yes | API v2 | Requires bearer token |
| TikTok | ✅ Yes | ✅ Yes | ✅ Thumbnail | HTML meta tags | Limited to caption + thumbnail |
| Facebook | ❌ No | ✅ Yes | ❌ No | N/A | Auth wall, use --text |
| Instagram | ❌ No | ✅ Yes | ❌ No | N/A | Auth wall, use --text |

### Reddit

**Supported URL formats:**
- `https://reddit.com/r/subreddit/comments/id/title`
- `https://www.reddit.com/r/subreddit/comments/id/title`
- `https://old.reddit.com/r/subreddit/comments/id/title`
- `https://redd.it/id`

**How it works:**
- Appends `.json` to the URL to get structured data
- Extracts: title, selftext (body), author
- Handles link posts (title only) with a note

**Limitations:**
- Cannot access private subreddits (403 error)
- Cannot access quarantined subreddits without auth
- Deleted posts return 404

**Example:**
```bash
python policyguard.py check "https://reddit.com/r/worldnews/comments/abc123/title"
```

### X (Twitter)

**Supported URL formats:**
- `https://x.com/username/status/tweet_id`
- `https://twitter.com/username/status/tweet_id`

**Requirements:**
- `X_BEARER_TOKEN` environment variable must be set
- Get a bearer token from [Twitter Developer Portal](https://developer.twitter.com/)

**How it works:**
- Extracts tweet ID from URL
- Calls Twitter API v2 `/tweets/{id}` endpoint
- Extracts: tweet text, author username

**Limitations:**
- Cannot access protected/private accounts
- Requires API access (free tier available)

**Setup:**
```bash
# Add to .env
X_BEARER_TOKEN=your-bearer-token-here
```

**Example:**
```bash
python policyguard.py check "https://x.com/user/status/1234567890"
```

### TikTok

**Supported URL formats:**
- `https://tiktok.com/@username/video/video_id`
- `https://www.tiktok.com/@username/video/video_id`
- `https://vm.tiktok.com/shortcode/`

**How it works:**
- Fetches the HTML page
- Extracts caption from `<meta property="og:description">` or `<meta name="description">`
- Falls back to page title if needed

**Limitations:**
- Only extracts text caption, not video content
- Some videos may have empty or minimal captions
- If caption can't be extracted, returns a note for manual review

**Example:**
```bash
python policyguard.py check "https://tiktok.com/@user/video/1234567890"
```

### Facebook

**Auto-fetch: NOT SUPPORTED**

Facebook requires authentication to access post content. Attempting to auto-fetch will return:

```
Error: Facebook posts cannot be automatically scraped due to Meta's authentication
walls. To check a Facebook post, use the --text flag:

  python policyguard.py check --platform facebook --text "paste post text here"
```

**Manual text input:**
```bash
# Copy the post text from Facebook, then:
python policyguard.py check --platform facebook --text "The copied post text..."
```

### Instagram

**Auto-fetch: NOT SUPPORTED**

Same as Facebook - requires authentication.

```
Error: Instagram posts cannot be automatically scraped due to Meta's authentication
walls. To check an Instagram post, use the --text flag:

  python policyguard.py check --platform instagram --text "paste post text here"
```

**Manual text input:**
```bash
python policyguard.py check --platform instagram --text "The caption from the Instagram post..."
```

---

## Policy Management

### How Policies Work

1. **Scraping**: The `refresh` command fetches policy pages and converts them to Markdown
2. **Caching**: Policies are stored in `policies/*.md` files
3. **Loading**: During `check`, policies are loaded from cache (never live-fetched)
4. **Analysis**: Full policy text is sent to Claude along with the post

### Policy Files

| Platform | Files |
|----------|-------|
| Reddit | `reddit_content_policy.md`, `reddit_user_agreement.md` |
| X/Twitter | `x_rules.md`, `x_tos.md` |
| TikTok | `tiktok_community.md`, `tiktok_tos.md` |
| Facebook | `facebook_community.md`, `facebook_tos.md` |
| Instagram | `instagram_community.md`, `instagram_tos.md` |

### Policy Sources

| Policy | URL |
|--------|-----|
| Reddit Content Policy | https://redditinc.com/policies/reddit-rules |
| Reddit User Agreement | https://redditinc.com/policies/user-agreement |
| X Rules | https://help.x.com/en/rules-and-policies |
| X Terms | https://x.com/en/tos |
| TikTok Community | https://www.tiktok.com/safety/en-GB/policies-and-engagement/overview |
| TikTok Terms | https://www.tiktok.com/legal/page/row/terms-of-service/en |
| Facebook Community | https://transparency.meta.com/policies/community-standards |
| Facebook Terms | https://www.facebook.com/terms |
| Instagram Community | https://help.instagram.com/581066165581870 |
| Instagram Terms | https://help.instagram.com/581066165581870 |

### Refreshing Policies

```bash
# Refresh all (recommended monthly)
python policyguard.py refresh

# Refresh specific platform
python policyguard.py refresh --platform reddit
```

**Note:** Some platforms (Facebook, Instagram) use JavaScript-rendered pages that may not scrape completely. The scraper preserves existing files if a refresh fails.

### Viewing Cached Policies

```bash
python policyguard.py show-policy reddit
python policyguard.py show-policy x
python policyguard.py show-policy tiktok
```

---

## How It Works

### Analysis Flow

```
1. INPUT
   ├── URL provided? → Detect platform → Fetch post via adapter
   └── --text provided? → Use manual text with --platform

2. LOAD POLICIES
   └── Read cached policies/*.md files for the platform

3. BUILD PROMPT
   ├── System prompt: "You are a policy compliance analyst..."
   └── User prompt: Platform + Post + Policies + JSON schema

4. CALL CLAUDE
   ├── Single API call with full context
   └── Model: claude-sonnet-4-20250514, max 2000 tokens

5. PARSE RESPONSE
   ├── Extract raw JSON from response
   ├── Validate required fields
   └── Build Verdict object

6. OUTPUT
   ├── Print JSON to stdout
   └── Optionally save to --output file
```

### The Claude Prompt

**System Prompt:**
```
You are a precise, impartial social media policy compliance analyst.

Your job is to determine whether a given post violates the platform's
Community Guidelines or Terms of Service.

Rules you must follow:
1. Only flag genuine violations. Do not flag things that are merely
   controversial, edgy, or offensive but do not violate written policy.
2. Always quote the specific phrase from the post that triggered the violation.
3. Always cite the exact policy section or rule name, not a vague description.
4. Your confidence score must reflect genuine uncertainty — if the post is
   clearly fine, return 0.95+. If it is borderline, return 0.5-0.75.
5. Return ONLY raw JSON. No markdown fences. No explanation. No preamble.
6. If images are provided, analyze them with the same rigor as the text.
   Violations found in images are just as serious as violations in text.
   In the "quote" field for image violations, describe what you saw instead
   of quoting text, e.g.: "[Image 1: hate symbol displayed prominently in center of image]"
```

**User Prompt Template:**
```
PLATFORM: {platform_name}

POST URL: {url}
POST AUTHOR: {author}
POST TITLE: {title}
POST TEXT:
---
{post_text}
---

PLATFORM POLICIES (Community Guidelines + Terms of Service):
---
{policies_text}
---

Analyze the post against the policies above and return a JSON object...
```

### Why This Approach?

1. **Single API Call**: Claude Sonnet has 200K token context. All policies combined are ~50K tokens. No need for RAG or chunking.

2. **Cached Policies**: Policies change infrequently. Caching them:
   - Makes analysis fast (no HTTP latency)
   - Works offline after initial setup
   - Ensures consistent analysis

3. **Structured JSON**: Forcing JSON output:
   - Enables programmatic processing
   - Prevents hallucinated prose
   - Makes validation straightforward

---

## Error Handling

PolicyGuard provides detailed, actionable error messages for every failure mode.

### Common Errors

#### Missing API Key

```
Error: ANTHROPIC_API_KEY environment variable is not set.
Create a .env file with: ANTHROPIC_API_KEY=your-key-here
```

**Fix:** Add your API key to `.env`

#### Missing Policy Files

```
Error: Policy file 'reddit_content_policy.md' not found.
Run: python policyguard.py refresh
```

**Fix:** Run `python policyguard.py refresh`

#### Unsupported URL

```
Error: Could not detect platform from URL: https://youtube.com/watch?v=abc

Supported URL patterns:
  reddit: reddit.com/r/, redd.it/
  x: x.com/, twitter.com/
  tiktok: tiktok.com/@, vm.tiktok.com/
  facebook: facebook.com/, fb.com/, fb.watch/
  instagram: instagram.com/p/, instagram.com/reel/

Make sure the URL contains one of the patterns above.
```

**Fix:** Use a supported platform URL or `--text` with `--platform`

#### Reddit Post Not Found

```
Error: Reddit returned 404 for this URL.
The post may have been deleted or the URL is incorrect.
URL: https://reddit.com/r/...
```

**Fix:** Verify the post exists and the URL is correct

#### Private Subreddit

```
Error: Reddit returned 403 for this URL.
The subreddit is likely private or quarantined.
Try a different post URL.
```

**Fix:** Use a post from a public subreddit

#### Facebook/Instagram URL

```
Error: Facebook posts cannot be automatically scraped due to Meta's authentication
walls. To check a Facebook post, use the --text flag:

  python policyguard.py check --platform facebook --text "paste post text here"
```

**Fix:** Copy the post text manually and use `--text`

#### Missing X Bearer Token

```
Error: X_BEARER_TOKEN environment variable is not set.

To get a bearer token:
1. Go to https://developer.twitter.com/
2. Create a project and app
3. Generate a bearer token
4. Add to your .env file: X_BEARER_TOKEN=your-token-here
```

**Fix:** Set up X/Twitter API access

#### Claude API Error

```
Error: Claude API error: [details]
Check your API key and internet connection.
```

**Fix:** Verify API key, check Anthropic status page

#### Invalid JSON from Claude

```
Error: Claude returned invalid JSON. Raw response saved to debug/last_response.txt
First 200 chars: [response preview]
```

**Fix:** Check `debug/last_response.txt` for details, retry the request

---

## Testing

PolicyGuard includes a comprehensive test suite with 200+ tests.

### Test Categories

| Category | Count | Description |
|----------|-------|-------------|
| Unit Tests | 146 | Individual component testing (including image fetcher + adapter image extraction) |
| Integration Tests | 24 | CLI and full flow testing |
| Edge Case Tests | 32 | Boundary conditions |
| Judge Quality Tests | 19 | Live Claude API verification |

### Running Tests

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Run all non-live tests (fast, no API calls)
python -m pytest tests/unit tests/integration tests/edge_cases -v

# Run with coverage report
python -m pytest tests/unit tests/integration tests/edge_cases --cov=. --cov-report=term-missing

# Run live judge quality tests (requires API key, costs money)
source .env && export ANTHROPIC_API_KEY && python -m pytest tests/judge -v

# Run specific test file
python -m pytest tests/unit/test_detector.py -v

# Run specific test
python -m pytest tests/unit/test_models.py::TestPostData::test_create_valid_post_data -v
```

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── unit/
│   ├── test_detector.py     # URL pattern matching
│   ├── test_models.py       # Dataclass validation
│   ├── test_policy_loader.py # Policy loading
│   ├── test_adapters.py     # All platform adapters
│   └── test_image_fetcher.py # Image downloading/encoding
├── integration/
│   ├── test_cli.py          # CLI commands
│   └── test_full_flow.py    # End-to-end with mocks
├── edge_cases/
│   └── test_edge_cases.py   # Boundary conditions
└── judge/
    └── test_judge_quality.py # Live Claude tests
```

### Judge Quality Tests

The judge quality tests verify Claude's accuracy on various content types:

| Test Category | Expectation |
|--------------|-------------|
| Legitimate political opinion | PASS |
| Cooking recipe | PASS |
| Tech discussion | PASS |
| Direct violence threat | FAIL (HIGH) |
| Personal threat | FAIL (HIGH) |
| Hate speech | FAIL (MEDIUM) |
| Harsh political criticism | PASS or low confidence |
| Code snippets | PASS (not flagged as violent) |
| News quotes | PASS |
| Fiction writing | PASS |

---

## Extending PolicyGuard

### Adding a New Platform

Follow these 6 steps to add support for a new platform:

#### Step 1: Create the Adapter

Create `adapters/newplatform.py`:

```python
"""
NewPlatform adapter for fetching post content.
"""
from datetime import datetime, timezone

import requests

from adapters.base import BaseAdapter
from core.models import PostData, ScrapingError


class NewPlatformAdapter(BaseAdapter):
    """Adapter for NewPlatform posts."""
    
    def fetch(self, url: str) -> PostData:
        """
        Fetch post content from NewPlatform.
        
        Args:
            url: Post URL
            
        Returns:
            PostData object
            
        Raises:
            ScrapingError: If post cannot be fetched
        """
        # 1. Extract post ID from URL
        post_id = self._extract_post_id(url)
        
        # 2. Fetch content (API call or HTML scraping)
        try:
            response = requests.get(f"https://api.newplatform.com/posts/{post_id}")
            response.raise_for_status()
            data = response.json()
        except requests.HTTPError as e:
            raise ScrapingError(
                f"NewPlatform returned HTTP {e.response.status_code}. "
                f"The post may not exist or is private."
            )
        
        # 3. Return PostData
        return PostData(
            url=url,
            platform="newplatform",
            text=data["content"],
            author=data.get("author", ""),
            title=data.get("title", ""),
            scraped_at=datetime.now(timezone.utc).isoformat()
        )
    
    def _extract_post_id(self, url: str) -> str:
        """Extract post ID from URL."""
        # Implementation depends on URL format
        import re
        match = re.search(r"newplatform\.com/post/(\w+)", url)
        if not match:
            raise ScrapingError(f"Could not extract post ID from: {url}")
        return match.group(1)
```

#### Step 2: Add URL Patterns

In `config.py`, add to `PLATFORM_PATTERNS`:

```python
PLATFORM_PATTERNS = {
    # ... existing platforms ...
    "newplatform": ["newplatform.com/post/", "newplatform.com/p/"],
}
```

#### Step 3: Add Policy Sources

In `config.py`, add to `POLICY_SOURCES`:

```python
POLICY_SOURCES = {
    # ... existing sources ...
    "newplatform_community": "https://newplatform.com/community-guidelines",
    "newplatform_tos": "https://newplatform.com/terms-of-service",
}
```

#### Step 4: Map Policy Files

In `config.py`, add to `PLATFORM_POLICY_FILES`:

```python
PLATFORM_POLICY_FILES = {
    # ... existing mappings ...
    "newplatform": ["newplatform_community.md", "newplatform_tos.md"],
}
```

#### Step 5: Register the Adapter

In `policyguard.py`, add to `get_adapter()`:

```python
def get_adapter(platform: str):
    # ... existing adapters ...
    elif platform == "newplatform":
        from adapters.newplatform import NewPlatformAdapter
        return NewPlatformAdapter()
```

#### Step 6: Update Constants

In `config.py`, add to `SUPPORTED_PLATFORMS`:

```python
SUPPORTED_PLATFORMS = ["reddit", "x", "tiktok", "facebook", "instagram", "newplatform"]
AUTO_SCRAPE_PLATFORMS = ["reddit", "x", "tiktok", "newplatform"]  # If auto-scrape works
```

#### Step 7: Scrape Policies

```bash
python policyguard.py refresh --platform newplatform
```

#### Step 8: Test

```bash
# Test URL detection
python -c "from core.detector import detect_platform; print(detect_platform('https://newplatform.com/post/abc123'))"

# Test fetching
python policyguard.py check "https://newplatform.com/post/abc123"
```

---

## Project Structure

```
policyguard/
│
├── policyguard.py              # CLI entry point (only file users run)
│
├── config.py                   # All configuration constants
│
├── core/                       # Core business logic
│   ├── __init__.py
│   ├── detector.py             # URL → platform detection
│   ├── image_fetcher.py        # Download + base64 encode images
│   ├── judge.py                # Claude API integration (multimodal)
│   ├── models.py               # Dataclasses + exceptions
│   └── policy_loader.py        # Load policies from cache
│
├── adapters/                   # Platform-specific fetching
│   ├── __init__.py
│   ├── base.py                 # Abstract base class
│   ├── reddit.py               # Reddit (.json endpoint)
│   ├── x.py                    # X/Twitter (API v2)
│   ├── tiktok.py               # TikTok (meta tags)
│   ├── facebook.py             # Facebook (not supported)
│   └── instagram.py            # Instagram (not supported)
│
├── scrapers/                   # Policy scraping
│   ├── __init__.py
│   └── policy_scraper.py       # HTML → Markdown conversion
│
├── policies/                   # Cached policy files (auto-generated)
│   ├── reddit_content_policy.md
│   ├── reddit_user_agreement.md
│   ├── x_rules.md
│   ├── x_tos.md
│   ├── tiktok_community.md
│   ├── tiktok_tos.md
│   └── ...
│
├── debug/                      # Debug output
│   └── last_response.txt       # Saved when Claude returns invalid JSON
│
├── tests/                      # Test suite
│   ├── conftest.py             # Shared fixtures
│   ├── unit/                   # Unit tests
│   ├── integration/            # Integration tests
│   ├── edge_cases/             # Edge case tests
│   └── judge/                  # Live Claude tests
│
├── requirements.txt            # Production dependencies
├── requirements-test.txt       # Test dependencies
├── pytest.ini                  # Pytest configuration
├── .env.example                # Environment template
├── .gitignore                  # Git ignore rules
└── README.md                   # This file
```

---

## API Reference

### Data Models (`core/models.py`)

#### `PostData`

```python
@dataclass
class PostData:
    url: str                    # Original URL or "manual-input"
    platform: str               # "reddit" | "x" | "tiktok" | "facebook" | "instagram"
    text: str                   # Full post text/body
    author: str = ""            # Username (empty if unavailable)
    title: str = ""             # Post title (empty if N/A)
    image_urls: list[str] = []  # URLs of images in the post (auto-extracted)
    scraped_at: str = ""        # ISO 8601 timestamp (auto-generated)
```

#### `Violation`

```python
@dataclass
class Violation:
    rule: str             # Violated rule name
    severity: str         # "HIGH" | "MEDIUM" | "LOW"
    explanation: str      # Why this is a violation
    policy_reference: str # Exact policy section
    quote: str            # Verbatim triggering phrase or "[Image N: description]" for visual violations
```

#### `Verdict`

```python
@dataclass
class Verdict:
    verdict: str          # "PASS" | "FAIL"
    platform: str
    post_url: str
    post_text: str
    violations: list[Violation]
    passed_checks: list[str]
    confidence: float     # 0.0 to 1.0
    recommendation: str
    checked_at: str       # ISO 8601 timestamp

    def to_dict(self) -> dict: ...  # Serialize to dict
    def to_json(self) -> str: ...   # Serialize to JSON string
```

### Exceptions

| Exception | When Raised |
|-----------|-------------|
| `NotSupportedError` | Platform doesn't support auto-scraping |
| `PolicyNotFoundError` | Policy cache file missing |
| `ScrapingError` | HTTP error during post fetching |
| `JudgmentError` | Claude API error or invalid response |

### Functions

#### `detect_platform(url: str) -> str`

Detect platform from URL. Raises `ValueError` if not supported.

#### `load_policies(platform: str) -> str`

Load cached policies for a platform. Raises `PolicyNotFoundError` if missing.

#### `judge(post: PostData, policies_text: str) -> Verdict`

Send post to Claude for analysis (text + images if available). Raises `JudgmentError` on failure.

#### `fetch_image_as_base64(url: str) -> tuple[str, str]`

Download an image and return `(base64_data, media_type)`. Raises `ScrapingError` on failure.

---

## Troubleshooting

### "Policy file not found" after fresh clone

**Problem:** You cloned the repo but haven't initialized the policy cache.

**Solution:**
```bash
python policyguard.py refresh
```

### "Claude returned invalid JSON"

**Problem:** The model returned malformed JSON.

**Solution:**
1. Check `debug/last_response.txt` for the raw response
2. Retry the request (transient issue)
3. If persistent, the post may be confusing the model

### Policies not updating

**Problem:** `refresh` reports success but policies seem outdated.

**Solution:**
1. Check the character count in the output
2. Some platforms use JavaScript rendering - the scraper may get limited content
3. For Facebook/Instagram, the scraper often fails (expected)

### X/Twitter requests failing

**Problem:** Getting 401/403 errors for X URLs.

**Solution:**
1. Verify `X_BEARER_TOKEN` is set in `.env`
2. Check the token hasn't expired
3. Verify you have API access (apply at developer.twitter.com)

### Slow analysis

**Problem:** Analysis takes a long time.

**Solution:**
- Claude API latency is typically 2-5 seconds
- Long posts take longer
- No way to speed up without using a faster model

### False positives/negatives

**Problem:** Judge is flagging safe content or missing violations.

**Solution:**
1. Check confidence score - low confidence means uncertainty
2. Review the policies being used (`show-policy`)
3. Claude is not perfect - use human review for important decisions

---

## Contributing

Contributions are welcome! Please follow these guidelines:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/my-feature`
3. **Write tests** for any new functionality
4. **Ensure all tests pass**: `python -m pytest`
5. **Follow code style**:
   - Type hints on all functions
   - Docstrings on public functions
   - No function longer than 60 lines
   - Constants in `config.py`
6. **Submit a pull request**

### Code Style

- Python 3.9+
- Type hints everywhere
- One-line docstrings for simple functions
- No bare `except Exception` catches
- Use `pathlib.Path` for all file paths
- No `print()` in modules (only in CLI layer)

---

## License

MIT License

Copyright (c) 2024

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
