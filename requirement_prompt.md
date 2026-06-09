# PolicyGuard — Cursor Project Prompt

> This document is the single source of truth for building PolicyGuard.
> Read it fully before writing a single line of code. Every architectural
> decision, file, function, and principle is defined here. Do not deviate
> from the structure. Do not add frameworks or libraries not listed. Do not
> guess — if something is ambiguous, refer back to the principles in this doc.

---

## 1. What Is PolicyGuard

PolicyGuard is a CLI + API tool that takes a social media post URL, extracts the
post content, loads the cached Community Guidelines and Terms of Service for that
platform, sends both to the Claude API, and returns a structured JSON verdict
explaining whether the post violates any policies and exactly which ones.

It does not have a UI. It does not have a database. It does not require a login.
It is a focused, composable backend tool built for correctness and extensibility.

**One-line summary of what it does:**
```
URL in → post text out → policy rules in → Claude judges → JSON verdict out
```

**Example usage (CLI):**
```bash
python policyguard.py check "https://www.reddit.com/r/albania/comments/xyz/abc"
```

**Example output:**
```json
{
  "verdict": "FAIL",
  "platform": "reddit",
  "post_url": "https://www.reddit.com/r/...",
  "post_text": "...",
  "violations": [
    {
      "rule": "Violent Speech",
      "severity": "HIGH",
      "explanation": "Post contains a direct threat of physical harm toward a named group.",
      "policy_reference": "Reddit Content Policy — Violent Speech section",
      "quote": "the exact phrase from the post that triggered this"
    }
  ],
  "passed_checks": ["Hate Speech", "Spam", "Privacy", "Misinformation"],
  "confidence": 0.94,
  "recommendation": "Remove the threatening language in the third sentence."
}
```

---

## 2. Core Principles (Non-Negotiable)

These principles are the law of this codebase. Every function, module, and
decision must be consistent with all of them.

### Principle 1 — One Claude call per post. No RAG. No chunking.
Pass the full post text and the full platform policy Markdown in a single API
call. Claude Sonnet has a 200K token context window. All platform policies
combined are under 20K tokens. One post is under 2K tokens. There is no reason
to split this. RAG adds complexity and retrieval errors for no gain here.

### Principle 2 — Policies are a cache, not a live fetch.
Policy pages are scraped once and stored as clean Markdown files on disk under
`policies/`. They are never fetched live during a `check` run. A separate
`refresh` command re-scrapes them. This keeps the hot path fast and resilient.

### Principle 3 — Per-platform adapters, fully isolated.
Each platform (Reddit, X, TikTok, Facebook, Instagram) has its own adapter
module under `adapters/`. Adapters implement a single interface: they receive
a URL and return a `PostData` object. If one adapter breaks, the others
are unaffected. No shared scraping logic between platforms.

### Principle 4 — Structured JSON output from Claude. Always.
The Claude prompt must instruct the model to return only raw JSON, no markdown
fences, no preamble, no explanation outside the JSON. The calling code must
parse this strictly and raise a clear error if it cannot parse it, never
silently fail or return half-results.

### Principle 5 — Fail loudly and specifically.
Every error must say exactly what failed and why. No generic "something went
wrong" messages. Examples: "Reddit API returned 404 for this URL",
"Policy file for instagram not found — run: python policyguard.py refresh",
"Claude API returned invalid JSON — raw response saved to debug/last_response.txt"

### Principle 6 — Platform walls are handled honestly.
Reddit and X (limited) are fully automated. TikTok uses description/caption
text. Facebook and Instagram cannot be reliably scraped without authentication —
the adapter for these must return a clear, actionable error:
"Facebook posts cannot be auto-scraped. Use: python policyguard.py check --text 'paste post here' --platform facebook"
Never silently return empty content.

### Principle 7 — No hidden state. Everything is a file or a return value.
No global variables that mutate during a run. No singleton objects with
side effects. Policy cache = files on disk. Post data = returned object.
Claude result = returned object. Debug output = file in `debug/`.

---

## 3. Project Structure

```
policyguard/
│
├── policyguard.py              # CLI entry point — the only file a user runs
│
├── core/
│   ├── __init__.py
│   ├── detector.py             # URL → platform name
│   ├── judge.py                # Claude API call + JSON parsing
│   ├── policy_loader.py        # loads policies/*.md from disk
│   └── models.py               # PostData, Violation, Verdict dataclasses
│
├── adapters/
│   ├── __init__.py
│   ├── base.py                 # Abstract base class all adapters inherit
│   ├── reddit.py               # Reddit adapter (public JSON API)
│   ├── x.py                    # X/Twitter adapter (free API tier)
│   ├── tiktok.py               # TikTok adapter (description + caption)
│   ├── facebook.py             # Facebook adapter (graceful not-supported error)
│   └── instagram.py            # Instagram adapter (graceful not-supported error)
│
├── scrapers/
│   ├── __init__.py
│   └── policy_scraper.py       # Fetches + cleans policy pages → Markdown files
│
├── policies/                   # AUTO-GENERATED by `refresh` command. Do not edit manually.
│   ├── facebook_community.md
│   ├── facebook_tos.md
│   ├── instagram_community.md
│   ├── instagram_tos.md
│   ├── x_rules.md
│   ├── x_tos.md
│   ├── tiktok_community.md
│   ├── tiktok_tos.md
│   ├── reddit_content_policy.md
│   └── reddit_user_agreement.md
│
├── debug/                      # Auto-created. Stores last raw Claude response on error.
│   └── .gitkeep
│
├── config.py                   # All configuration: URLs, model name, timeouts
├── requirements.txt
└── README.md
```

---

## 4. Data Models (`core/models.py`)

Define these as Python `dataclasses`. Use type hints everywhere.

```python
@dataclass
class PostData:
    url: str
    platform: str           # "reddit" | "x" | "tiktok" | "facebook" | "instagram"
    text: str               # The full post text / caption / body
    author: str             # Username or handle, empty string if unavailable
    title: str              # Post title if platform has one (Reddit), else empty string
    scraped_at: str         # ISO 8601 timestamp

@dataclass
class Violation:
    rule: str               # Name of the violated rule e.g. "Violent Speech"
    severity: str           # "HIGH" | "MEDIUM" | "LOW"
    explanation: str        # Why this is a violation, in plain English
    policy_reference: str   # Exact section/rule name from the policy doc
    quote: str              # The verbatim phrase from the post that triggered this

@dataclass
class Verdict:
    verdict: str            # "PASS" | "FAIL"
    platform: str
    post_url: str
    post_text: str
    violations: list[Violation]
    passed_checks: list[str]
    confidence: float       # 0.0 to 1.0
    recommendation: str     # Empty string if verdict is PASS
    checked_at: str         # ISO 8601 timestamp

    def to_dict(self) -> dict:
        # Returns a fully serializable dict (for JSON output)
        ...

    def to_json(self) -> str:
        # Returns pretty-printed JSON string
        ...
```

---

## 5. Platform Detection (`core/detector.py`)

Simple URL pattern matching. No external library needed.

```python
PLATFORM_PATTERNS = {
    "reddit":    ["reddit.com/r/", "redd.it/"],
    "x":         ["x.com/", "twitter.com/"],
    "tiktok":    ["tiktok.com/@", "vm.tiktok.com/"],
    "facebook":  ["facebook.com/", "fb.com/", "fb.watch/"],
    "instagram": ["instagram.com/p/", "instagram.com/reel/"],
}

def detect_platform(url: str) -> str:
    """
    Returns the platform name string or raises ValueError with a clear message
    listing which URL patterns are supported.
    """
```

---

## 6. Adapters (`adapters/`)

### Base class (`adapters/base.py`)

```python
from abc import ABC, abstractmethod
from core.models import PostData

class BaseAdapter(ABC):
    @abstractmethod
    def fetch(self, url: str) -> PostData:
        """
        Fetch post content from the given URL.
        Must return a PostData object.
        Must raise a descriptive exception if content cannot be retrieved.
        Must NEVER return a PostData with an empty text field silently.
        """
        pass
```

### Reddit Adapter (`adapters/reddit.py`)

Reddit is the priority adapter. Implement it fully and robustly.

**Mechanism:**
- Append `.json` to any Reddit post URL (e.g. `https://reddit.com/r/sub/comments/id/title` → `https://reddit.com/r/sub/comments/id/title.json`)
- Set `User-Agent` header: `"PolicyGuard/1.0 (policy compliance research tool)"`
- Parse the JSON response: `data[0]['data']['children'][0]['data']` for post metadata
- `title` = `post['title']`
- `text` = `post['selftext']` (empty for link posts — in that case use title only and note it)
- `author` = `post['author']`
- Handle 404 (post not found), 403 (private subreddit), 200 with empty selftext (link post)

**Do not use the Reddit OAuth API.** The public `.json` endpoint is sufficient for public posts.

### X Adapter (`adapters/x.py`)

**Mechanism:**
- Extract tweet ID from URL: `x.com/{username}/status/{tweet_id}`
- Use the Twitter/X API v2 free tier: `GET /2/tweets/{id}?tweet.fields=text,author_id`
- Requires `BEARER_TOKEN` from environment variable `X_BEARER_TOKEN`
- If `X_BEARER_TOKEN` is not set: raise a clear error explaining how to get one
- If tweet is not found or protected: raise a clear error

### TikTok Adapter (`adapters/tiktok.py`)

TikTok does not have a public content API for post text.

**Mechanism:**
- Use `requests` with a realistic browser `User-Agent` to fetch the TikTok URL
- Parse the HTML response for the video description/caption in the meta tags:
  `<meta name="description" content="...">` or `<meta property="og:description" ...>`
- Also extract `<title>` tag content as fallback
- If neither yields content: return a PostData with a note in text that says
  `"[TikTok caption not extractable from this URL. Video content requires manual review.]"`
  and do NOT silently pass this as compliant — the judge must flag it as unanalyzable.

### Facebook Adapter (`adapters/facebook.py`)

Facebook cannot be reliably scraped without authentication.

**Mechanism:**
- Immediately raise `NotSupportedError` with this exact message:
  ```
  Facebook posts cannot be automatically scraped due to Meta's authentication
  walls. To check a Facebook post, use the --text flag:

    python policyguard.py check --platform facebook --text "paste post text here"
  ```
- Do not attempt any HTTP request.

### Instagram Adapter (`adapters/instagram.py`)

Same as Facebook.

**Mechanism:**
- Immediately raise `NotSupportedError` with this exact message:
  ```
  Instagram posts cannot be automatically scraped due to Meta's authentication
  walls. To check an Instagram post, use the --text flag:

    python policyguard.py check --platform instagram --text "paste post text here"
  ```

---

## 7. Policy Scraper (`scrapers/policy_scraper.py`)

This module is only called by the `refresh` CLI command. It is never called
during a normal `check` run.

### Policy URLs to scrape

```python
POLICY_SOURCES = {
    "facebook_community":   "https://transparency.meta.com/policies/community-standards",
    "facebook_tos":         "https://www.facebook.com/terms",
    "instagram_community":  "https://help.instagram.com/581066165581870",
    "instagram_tos":        "https://help.instagram.com/581066165581870",
    "x_rules":              "https://help.x.com/en/rules-and-policies",
    "x_tos":                "https://x.com/en/tos",
    "tiktok_community":     "https://www.tiktok.com/safety/en-GB/policies-and-engagement/overview",
    "tiktok_tos":           "https://www.tiktok.com/legal/page/row/terms-of-service/en",
    "reddit_content_policy":"https://redditinc.com/policies/reddit-rules",
    "reddit_user_agreement":"https://redditinc.com/policies/user-agreement",
}
```

### Scraping mechanism

Use `requests` + `BeautifulSoup` (html.parser, not lxml — no extra install).

For each URL:
1. Fetch with a realistic browser User-Agent and a 10-second timeout
2. Parse HTML: extract all `<p>`, `<h1>`, `<h2>`, `<h3>`, `<h4>`, `<li>` tags in document order
3. Convert to clean Markdown:
   - `<h1>` → `# text`
   - `<h2>` → `## text`
   - `<h3>` → `### text`
   - `<h4>` → `#### text`
   - `<li>` → `- text`
   - `<p>` → `text` (plain paragraph)
4. Strip all HTML attributes, scripts, nav menus, cookie banners, footer links
5. Remove consecutive blank lines (max 1 blank line between paragraphs)
6. Write to `policies/{key}.md`
7. Print: `✓ Scraped facebook_community → policies/facebook_community.md (4,821 chars)`

If a page fails to fetch (timeout, 403, etc.):
- Print: `✗ FAILED facebook_community — HTTP 403. Skipping. Existing file preserved.`
- Do NOT overwrite an existing file with empty content

After all scrapes, print a summary:
```
Policy refresh complete: 8/10 succeeded, 2 failed.
Failed: facebook_community, instagram_community
Run `python policyguard.py check` will use cached versions for failed pages.
```

---

## 8. Policy Loader (`core/policy_loader.py`)

```python
PLATFORM_POLICY_FILES = {
    "facebook":  ["facebook_community.md", "facebook_tos.md"],
    "instagram": ["instagram_community.md", "instagram_tos.md"],
    "x":         ["x_rules.md", "x_tos.md"],
    "tiktok":    ["tiktok_community.md", "tiktok_tos.md"],
    "reddit":    ["reddit_content_policy.md", "reddit_user_agreement.md"],
}

def load_policies(platform: str) -> str:
    """
    Loads all policy Markdown files for the given platform and returns
    them concatenated as a single string with clear section headers.

    Raises FileNotFoundError with this message if any file is missing:
    "Policy file 'reddit_content_policy.md' not found.
     Run: python policyguard.py refresh"
    """
```

---

## 9. Claude Judge (`core/judge.py`)

This is the most important module. Get the prompt exactly right.

### System prompt

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
   The first character of your response must be '{' and the last must be '}'.
```

### User prompt template

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

Analyze the post against the policies above and return a JSON object with
this exact structure:

{
  "verdict": "PASS" or "FAIL",
  "violations": [
    {
      "rule": "exact rule name from the policy",
      "severity": "HIGH" | "MEDIUM" | "LOW",
      "explanation": "plain English explanation of why this is a violation",
      "policy_reference": "exact section name from the policy document",
      "quote": "verbatim phrase from the post that violates this rule"
    }
  ],
  "passed_checks": ["list of policy categories that were checked and passed"],
  "confidence": 0.0 to 1.0,
  "recommendation": "what should be changed or removed, empty string if PASS"
}

If the post passes all policies, violations must be an empty array [].
```

### Claude API call

```python
import anthropic
import json
import os
from pathlib import Path

def judge(post: PostData, policies_text: str) -> Verdict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(post, policies_text)}]
    )

    raw = response.content[0].text.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Save raw response for debugging
        Path("debug").mkdir(exist_ok=True)
        Path("debug/last_response.txt").write_text(raw)
        raise ValueError(
            f"Claude returned invalid JSON. Raw response saved to debug/last_response.txt\n"
            f"First 200 chars: {raw[:200]}"
        )

    return build_verdict(post, data)
```

---

## 10. CLI Entry Point (`policyguard.py`)

Use Python's built-in `argparse`. No Click, no Typer.

### Commands

#### `check` — main command

```bash
# From URL (auto-detect platform + scrape)
python policyguard.py check "https://reddit.com/r/albania/comments/xyz/title"

# Manual text input (for Facebook/Instagram or any platform)
python policyguard.py check --platform facebook --text "The post text here"

# Output to file
python policyguard.py check "URL" --output result.json

# Quiet mode (only print the JSON, no status messages)
python policyguard.py check "URL" --quiet
```

#### `refresh` — re-scrape all policy pages

```bash
python policyguard.py refresh

# Refresh only one platform
python policyguard.py refresh --platform reddit
```

#### `show-policy` — print a cached policy to terminal

```bash
python policyguard.py show-policy reddit
```

### Flow for `check` command

```
1. If URL given:
   a. detect_platform(url)
   b. adapter = get_adapter(platform)
   c. post = adapter.fetch(url)
   d. print status: "✓ Post scraped from Reddit (author: u/username)"

2. If --text given:
   a. platform must also be given via --platform, else error
   b. build PostData manually from --text value

3. policies_text = load_policies(platform)
   print status: "✓ Policies loaded for {platform} ({len} chars)"

4. print status: "⚡ Sending to Claude for analysis..."

5. verdict = judge(post, policies_text)

6. print verdict.to_json()

7. If --output given: write to file, print "✓ Saved to result.json"
```

---

## 11. Configuration (`config.py`)

All constants live here. Nothing is hardcoded in modules.

```python
# Claude
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_MAX_TOKENS = 2000

# Scraper
SCRAPER_TIMEOUT_SECONDS = 10
SCRAPER_USER_AGENT = "Mozilla/5.0 (compatible; PolicyGuard/1.0; policy compliance research)"
POLICY_REFRESH_INTERVAL_DAYS = 30

# Paths
POLICIES_DIR = "policies"
DEBUG_DIR = "debug"

# Platforms
SUPPORTED_PLATFORMS = ["reddit", "x", "tiktok", "facebook", "instagram"]
AUTO_SCRAPE_PLATFORMS = ["reddit", "x", "tiktok"]  # Facebook/Instagram need manual text
```

---

## 12. Requirements (`requirements.txt`)

```
anthropic>=0.25.0
requests>=2.31.0
beautifulsoup4>=4.12.0
python-dotenv>=1.0.0
```

No other dependencies. No Playwright. No Selenium. No heavyweight frameworks.
If Playwright is later needed for JavaScript-rendered pages, it goes in a
separate optional `requirements-advanced.txt`.

---

## 13. Environment Variables

The project uses a `.env` file at the project root. Use `python-dotenv` to
load it at the top of `policyguard.py`.

```
ANTHROPIC_API_KEY=sk-ant-...
X_BEARER_TOKEN=AAAA...         # Optional. Only needed for X/Twitter URLs.
```

If `ANTHROPIC_API_KEY` is not set, fail immediately with:
```
Error: ANTHROPIC_API_KEY environment variable is not set.
Create a .env file with: ANTHROPIC_API_KEY=your-key-here
```

---

## 14. Error Handling Contract

Every exception raised anywhere in the codebase must follow this pattern:
- State **what** failed (the operation)
- State **why** it failed (the reason)
- State **what the user should do** next

Examples:

```python
# Good
raise ValueError(
    "Reddit returned HTTP 403 for this URL. "
    "The subreddit is likely private or quarantined. "
    "Try a different post URL."
)

# Bad
raise Exception("Request failed")
```

Custom exception classes to define in `core/models.py`:
- `NotSupportedError` — for Facebook/Instagram auto-scrape attempts
- `PolicyNotFoundError` — for missing policy cache files
- `ScrapingError` — for HTTP errors during post fetching
- `JudgmentError` — for Claude API or JSON parsing failures

---

## 15. README.md Content

The README must contain:

1. One-line description
2. Install steps (clone, `pip install -r requirements.txt`, copy `.env.example` to `.env`)
3. First run: `python policyguard.py refresh` to scrape all policies
4. Usage examples for all 3 `check` modes (URL, --text, --output)
5. A sample JSON output block
6. Platform support table showing which are auto-scraped vs manual-text
7. How to add a new platform adapter (the 4-step guide: create adapter, add to detector, add policy URLs to scraper, add policy files to loader)

---

## 16. What NOT to Build (Explicit Exclusions)

Do not build any of the following — they are out of scope for this version:

- No web UI, no Flask/FastAPI server, no REST API
- No database (SQLite, Postgres, Redis, etc.)
- No async/await — use synchronous `requests` only
- No Docker, no docker-compose
- No rate limiting or queue system
- No caching of post content (only policies are cached)
- No login/auth for any platform
- No Playwright or browser automation
- No batch processing (one URL at a time)
- No history or logging of past checks

These may be added in a future version. Do not anticipate them by adding abstractions for them now.

---

## 17. Code Style Rules

- Python 3.11+
- Type hints on every function signature — parameters and return type
- Docstrings on every public function and class (one-line is fine for simple ones)
- No function longer than 60 lines. If it's longer, split it.
- No `print()` inside modules — only in `policyguard.py` (CLI layer). Modules return values or raise exceptions.
- No `except Exception` bare catches. Always catch specific exceptions.
- All file paths constructed with `pathlib.Path`, never string concatenation.
- Constants in UPPER_SNAKE_CASE, always in `config.py`, never inline.

---

## 18. Build Order

Build in this exact order. Each step should be runnable/testable before moving to the next.

```
Step 1 — Scaffold
  Create all directories and empty __init__.py files.
  Create config.py with all constants.
  Create core/models.py with all dataclasses and exceptions.

Step 2 — Policy cache
  Build scrapers/policy_scraper.py.
  Build core/policy_loader.py.
  Run: python policyguard.py refresh
  Verify: policies/*.md files exist and contain readable text.

Step 3 — Platform detection
  Build core/detector.py.
  Test with 5 example URLs, one per platform.

Step 4 — Reddit adapter (first working end-to-end path)
  Build adapters/base.py and adapters/reddit.py.
  Test: fetch a real public Reddit post URL and print the PostData.

Step 5 — Claude judge
  Build core/judge.py with the full system prompt and user prompt.
  Test: pass a hardcoded PostData + loaded Reddit policies → print Verdict JSON.

Step 6 — CLI wiring
  Build policyguard.py with argparse.
  Test: python policyguard.py check "https://reddit.com/r/..."
  This is the first full end-to-end run.

Step 7 — Remaining adapters
  Build x.py, tiktok.py, facebook.py, instagram.py.
  Test each one.

Step 8 — Polish
  Write README.md.
  Test all CLI flags (--output, --quiet, --platform, --text).
  Test all error cases: missing env var, missing policy file, bad URL, private subreddit.
```

---

## 19. Testing the Judge Prompt (Sanity Checks)

Before considering the judge done, test it with these 4 cases and verify results make sense:

**Case 1 — Should PASS:**
Platform: Reddit | Text: "I think the protests in Albania are a legitimate expression of democratic frustration."
Expected: verdict=PASS, violations=[]

**Case 2 — Should FAIL (HIGH):**
Platform: Reddit | Text: "These protesters deserve to get beaten. Someone should teach them a lesson with violence."
Expected: verdict=FAIL, at least one HIGH violation for Violent Speech

**Case 3 — Should FAIL (MEDIUM):**
Platform: X | Text: "All [ethnic group] people are criminals and should be deported."
Expected: verdict=FAIL, violation for Hateful Conduct

**Case 4 — Borderline (confidence should be low, 0.4-0.7):**
Platform: Facebook | Text: "The police in Tirana are acting like fascists."
Expected: May pass or fail, but confidence must be below 0.75 — this is political speech that is critical but may not technically violate policy.

---

## 20. Final Checklist Before Considering It Done

- [ ] `python policyguard.py refresh` runs and creates all 10 policy files
- [ ] `python policyguard.py check "https://reddit.com/r/worldnews/..."` returns valid JSON
- [ ] `python policyguard.py check --platform facebook --text "some text"` works
- [ ] `python policyguard.py check "URL" --output result.json` creates the file
- [ ] A missing `ANTHROPIC_API_KEY` gives a clear error before any API call
- [ ] A private Reddit post gives a clear error message
- [ ] A Facebook URL gives the "use --text instead" error message
- [ ] All 4 sanity check cases produce sensible verdicts
- [ ] No bare `except Exception` anywhere in the codebase
- [ ] No hardcoded strings that belong in `config.py`