#!/usr/bin/env python3
"""
PolicyGuard CLI - Social media policy compliance checker.

Usage:
    python policyguard.py check "https://reddit.com/r/..."
    python policyguard.py check --platform facebook --text "post text here"
    python policyguard.py refresh
    python policyguard.py show-policy reddit
"""
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(Path(__file__).parent / ".env")

from config import SUPPORTED_PLATFORMS, AUTO_SCRAPE_PLATFORMS, POLICIES_DIR
from core.models import PostData, NotSupportedError, PolicyNotFoundError, ScrapingError, JudgmentError
from core.detector import detect_platform
from core.policy_loader import load_policies
from core.judge import judge
from scrapers.policy_scraper import scrape_all_policies, print_summary


def get_adapter(platform: str):
    """
    Factory function to get the appropriate adapter for a platform.
    
    Args:
        platform: Platform name
        
    Returns:
        Adapter instance for the platform
        
    Raises:
        ValueError: If platform is not supported
    """
    if platform == "reddit":
        from adapters.reddit import RedditAdapter
        return RedditAdapter()
    elif platform == "x":
        from adapters.x import XAdapter
        return XAdapter()
    elif platform == "tiktok":
        from adapters.tiktok import TikTokAdapter
        return TikTokAdapter()
    elif platform == "facebook":
        from adapters.facebook import FacebookAdapter
        return FacebookAdapter()
    elif platform == "instagram":
        from adapters.instagram import InstagramAdapter
        return InstagramAdapter()
    else:
        raise ValueError(
            f"Unknown platform '{platform}'. "
            f"Supported platforms: {', '.join(SUPPORTED_PLATFORMS)}"
        )


def cmd_check(args) -> int:
    """
    Handle the 'check' command.
    
    Returns:
        Exit code (0 for success, 1 for error)
    """
    quiet = args.quiet
    
    def status(msg: str) -> None:
        if not quiet:
            print(msg, file=sys.stderr)
    
    # Validate inputs
    if args.url and args.text:
        print("Error: Cannot specify both URL and --text. Use one or the other.", file=sys.stderr)
        return 1
    
    if not args.url and not args.text:
        print("Error: Must specify either a URL or --text with post content.", file=sys.stderr)
        return 1
    
    if args.text and not args.platform:
        print("Error: --platform is required when using --text.", file=sys.stderr)
        return 1
    
    # Build PostData
    try:
        if args.url:
            # Auto-detect platform and fetch post
            platform = detect_platform(args.url)
            status(f"✓ Detected platform: {platform}")
            
            adapter = get_adapter(platform)
            post = adapter.fetch(args.url)
            status(f"✓ Post scraped from {platform.title()} (author: {post.author})")
        else:
            # Manual text input
            platform = args.platform.lower()
            if platform not in SUPPORTED_PLATFORMS:
                print(
                    f"Error: Unknown platform '{platform}'. "
                    f"Supported: {', '.join(SUPPORTED_PLATFORMS)}",
                    file=sys.stderr
                )
                return 1
            
            post = PostData(
                url="manual-input",
                platform=platform,
                text=args.text,
                author="",
                title="",
                scraped_at=datetime.now(timezone.utc).isoformat()
            )
            status(f"✓ Using manual text input for {platform}")
    
    except NotSupportedError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ScrapingError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    # Load policies
    try:
        policies_text = load_policies(post.platform)
        status(f"✓ Policies loaded for {post.platform} ({len(policies_text):,} chars)")
    except PolicyNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    # Check API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "Error: ANTHROPIC_API_KEY environment variable is not set.\n"
            "Create a .env file with: ANTHROPIC_API_KEY=your-key-here",
            file=sys.stderr
        )
        return 1
    
    # Send to Claude
    status("⚡ Sending to Claude for analysis...")
    
    try:
        verdict = judge(post, policies_text)
    except JudgmentError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    # Output result
    json_output = verdict.to_json()
    print(json_output)
    
    # Save to file if requested
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json_output, encoding="utf-8")
        status(f"✓ Saved to {args.output}")
    
    return 0


def cmd_refresh(args) -> int:
    """
    Handle the 'refresh' command to re-scrape policy pages.
    
    Returns:
        Exit code (0 for success, 1 if all failed)
    """
    platform_filter = args.platform.lower() if args.platform else None
    
    if platform_filter and platform_filter not in SUPPORTED_PLATFORMS:
        print(
            f"Error: Unknown platform '{platform_filter}'. "
            f"Supported: {', '.join(SUPPORTED_PLATFORMS)}",
            file=sys.stderr
        )
        return 1
    
    print("Refreshing policy cache...\n")
    
    succeeded, failed, failed_keys = scrape_all_policies(platform_filter)
    print_summary(succeeded, failed, failed_keys)
    
    return 0 if succeeded > 0 else 1


def cmd_show_policy(args) -> int:
    """
    Handle the 'show-policy' command to display cached policies.
    
    Returns:
        Exit code (0 for success, 1 for error)
    """
    platform = args.platform.lower()
    
    if platform not in SUPPORTED_PLATFORMS:
        print(
            f"Error: Unknown platform '{platform}'. "
            f"Supported: {', '.join(SUPPORTED_PLATFORMS)}",
            file=sys.stderr
        )
        return 1
    
    try:
        policies_text = load_policies(platform)
        print(policies_text)
        return 0
    except PolicyNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="PolicyGuard - Social media policy compliance checker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python policyguard.py check "https://reddit.com/r/example/comments/xyz/title"
  python policyguard.py check --platform facebook --text "The post text here"
  python policyguard.py check "URL" --output result.json --quiet
  python policyguard.py refresh
  python policyguard.py refresh --platform reddit
  python policyguard.py show-policy reddit
"""
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # check command
    check_parser = subparsers.add_parser("check", help="Check a post for policy violations")
    check_parser.add_argument("url", nargs="?", help="URL of the post to check")
    check_parser.add_argument("--text", "-t", help="Post text (for manual input)")
    check_parser.add_argument("--platform", "-p", help="Platform name (required with --text)")
    check_parser.add_argument("--output", "-o", help="Save JSON output to file")
    check_parser.add_argument("--quiet", "-q", action="store_true", help="Only print JSON, no status messages")
    check_parser.set_defaults(func=cmd_check)
    
    # refresh command
    refresh_parser = subparsers.add_parser("refresh", help="Re-scrape policy pages")
    refresh_parser.add_argument("--platform", "-p", help="Only refresh policies for this platform")
    refresh_parser.set_defaults(func=cmd_refresh)
    
    # show-policy command
    show_parser = subparsers.add_parser("show-policy", help="Display cached policy for a platform")
    show_parser.add_argument("platform", help="Platform name (reddit, x, tiktok, facebook, instagram)")
    show_parser.set_defaults(func=cmd_show_policy)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
