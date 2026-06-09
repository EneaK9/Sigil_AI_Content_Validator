"""
Policy scraper for fetching and caching platform community guidelines and ToS.
Called by the `refresh` CLI command. Never called during a normal `check` run.
"""
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from config import (
    POLICY_SOURCES,
    POLICIES_DIR,
    SCRAPER_TIMEOUT_SECONDS,
    SCRAPER_USER_AGENT,
)


def html_to_markdown(soup: BeautifulSoup) -> str:
    """
    Convert parsed HTML to clean Markdown format.
    Extracts h1-h4, p, and li tags in document order.
    """
    markdown_lines: list[str] = []
    
    for element in soup.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        text = element.get_text(strip=True)
        if not text:
            continue
            
        if element.name == "h1":
            markdown_lines.append(f"# {text}")
        elif element.name == "h2":
            markdown_lines.append(f"## {text}")
        elif element.name == "h3":
            markdown_lines.append(f"### {text}")
        elif element.name == "h4":
            markdown_lines.append(f"#### {text}")
        elif element.name == "li":
            markdown_lines.append(f"- {text}")
        else:  # p tag
            markdown_lines.append(text)
        
        markdown_lines.append("")  # Add blank line after each element
    
    # Remove consecutive blank lines (max 1 blank line between paragraphs)
    result: list[str] = []
    prev_blank = False
    for line in markdown_lines:
        if line == "":
            if not prev_blank:
                result.append(line)
            prev_blank = True
        else:
            result.append(line)
            prev_blank = False
    
    return "\n".join(result).strip()


def scrape_policy(key: str, url: str) -> tuple[bool, str, int]:
    """
    Scrape a single policy page and save as Markdown.
    
    Args:
        key: Policy identifier (e.g., "reddit_content_policy")
        url: URL to scrape
        
    Returns:
        Tuple of (success: bool, message: str, char_count: int)
    """
    headers = {"User-Agent": SCRAPER_USER_AGENT}
    output_path = POLICIES_DIR / f"{key}.md"
    
    try:
        response = requests.get(url, headers=headers, timeout=SCRAPER_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.Timeout:
        return (False, f"Timeout after {SCRAPER_TIMEOUT_SECONDS}s", 0)
    except requests.HTTPError as e:
        return (False, f"HTTP {e.response.status_code}", 0)
    except requests.RequestException as e:
        return (False, str(e), 0)
    
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Remove script, style, nav, footer elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    
    markdown = html_to_markdown(soup)
    
    if not markdown or len(markdown) < 100:
        return (False, "Content too short or empty", 0)
    
    # Ensure policies directory exists
    POLICIES_DIR.mkdir(exist_ok=True)
    
    # Write to file
    output_path.write_text(markdown, encoding="utf-8")
    
    return (True, f"policies/{key}.md", len(markdown))


def scrape_all_policies(platform_filter: Optional[str] = None) -> tuple[int, int, list[str]]:
    """
    Scrape all policy pages or filter by platform.
    
    Args:
        platform_filter: If provided, only scrape policies for this platform
        
    Returns:
        Tuple of (succeeded: int, failed: int, failed_keys: list[str])
    """
    succeeded = 0
    failed = 0
    failed_keys: list[str] = []
    
    # Filter sources if platform specified
    sources = POLICY_SOURCES
    if platform_filter:
        sources = {
            k: v for k, v in POLICY_SOURCES.items() 
            if k.startswith(platform_filter)
        }
        if not sources:
            print(f"No policy sources found for platform: {platform_filter}")
            return (0, 0, [])
    
    for key, url in sources.items():
        success, message, char_count = scrape_policy(key, url)
        
        if success:
            print(f"✓ Scraped {key} → {message} ({char_count:,} chars)")
            succeeded += 1
        else:
            print(f"✗ FAILED {key} — {message}. Skipping. Existing file preserved.")
            failed += 1
            failed_keys.append(key)
    
    return (succeeded, failed, failed_keys)


def print_summary(succeeded: int, failed: int, failed_keys: list[str]) -> None:
    """Print a summary of the scrape operation."""
    total = succeeded + failed
    print()
    print(f"Policy refresh complete: {succeeded}/{total} succeeded, {failed} failed.")
    if failed_keys:
        print(f"Failed: {', '.join(failed_keys)}")
        print("Run `python policyguard.py check` will use cached versions for failed pages.")
