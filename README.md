# PolicyGuard

A CLI tool that checks social media posts against platform Community Guidelines and Terms of Service using Claude AI.

```
URL in → post text out → policy rules in → Claude judges → JSON verdict out
```

## Installation

```bash
# Clone the repository
git clone https://github.com/your-username/policyguard.git
cd policyguard

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

## First Run

Before checking posts, scrape and cache the platform policies:

```bash
python policyguard.py refresh
```

This creates Markdown files in the `policies/` directory containing the Community Guidelines and Terms of Service for each supported platform.

## Usage

### Check a post by URL (auto-detect platform)

```bash
python policyguard.py check "https://www.reddit.com/r/worldnews/comments/xyz/title"
```

### Check with manual text input (for Facebook/Instagram)

```bash
python policyguard.py check --platform facebook --text "The post text to analyze"
```

### Save output to file

```bash
python policyguard.py check "URL" --output result.json
```

### Quiet mode (JSON only, no status messages)

```bash
python policyguard.py check "URL" --quiet
```

### Refresh policy cache

```bash
# Refresh all platforms
python policyguard.py refresh

# Refresh only one platform
python policyguard.py refresh --platform reddit
```

### View cached policy

```bash
python policyguard.py show-policy reddit
```

## Sample Output

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
  "recommendation": "Remove the threatening language in the third sentence.",
  "checked_at": "2024-01-15T10:30:00Z"
}
```

## Platform Support

| Platform  | Auto-Scrape | Manual Text | Notes |
|-----------|-------------|-------------|-------|
| Reddit    | ✅ Yes      | ✅ Yes      | Uses public `.json` endpoint |
| X/Twitter | ✅ Yes      | ✅ Yes      | Requires `X_BEARER_TOKEN` |
| TikTok    | ✅ Yes      | ✅ Yes      | Extracts caption from meta tags |
| Facebook  | ❌ No       | ✅ Yes      | Use `--text` flag |
| Instagram | ❌ No       | ✅ Yes      | Use `--text` flag |

## Environment Variables

Create a `.env` file in the project root:

```bash
ANTHROPIC_API_KEY=sk-ant-...     # Required
X_BEARER_TOKEN=AAAA...           # Optional, only for X/Twitter URLs
```

## Adding a New Platform Adapter

1. **Create the adapter** in `adapters/newplatform.py`:
   - Inherit from `BaseAdapter`
   - Implement the `fetch(url: str) -> PostData` method

2. **Add URL patterns** to `config.py`:
   ```python
   PLATFORM_PATTERNS = {
       ...
       "newplatform": ["newplatform.com/post/"],
   }
   ```

3. **Add policy URLs** to `config.py`:
   ```python
   POLICY_SOURCES = {
       ...
       "newplatform_community": "https://newplatform.com/guidelines",
       "newplatform_tos": "https://newplatform.com/terms",
   }
   ```

4. **Map policy files** in `config.py`:
   ```python
   PLATFORM_POLICY_FILES = {
       ...
       "newplatform": ["newplatform_community.md", "newplatform_tos.md"],
   }
   ```

5. **Register the adapter** in `policyguard.py` `get_adapter()` function.

6. **Run refresh** to scrape the new policies:
   ```bash
   python policyguard.py refresh --platform newplatform
   ```

## License

MIT
