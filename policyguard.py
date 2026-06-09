#!/usr/bin/env python3
"""
PolicyGuard CLI - Social media policy compliance checker.

Usage:
    python policyguard.py check "https://reddit.com/r/..."
    python policyguard.py check --platform facebook --text "post text here"
    python policyguard.py check --json '{"url": "...", "message": "..."}'
    python policyguard.py check --json-file posts.json
    cat posts.json | python policyguard.py check --stdin
    python policyguard.py refresh
    python policyguard.py show-policy reddit
"""
import argparse
import json
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
from core.json_input import parse_json_input, load_json_file, load_json_stdin, JsonInputError
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


def process_single_post(
    post: PostData, 
    video_transcript: str,
    quiet: bool
) -> dict:
    """
    Process a single post and return the verdict dict.
    
    Args:
        post: PostData object
        video_transcript: Optional pre-transcribed video text
        quiet: Whether to suppress status messages
        
    Returns:
        Verdict as a dict
        
    Raises:
        PolicyNotFoundError, JudgmentError
    """
    def status(msg: str) -> None:
        if not quiet:
            print(msg, file=sys.stderr)
    
    # Load policies
    policies_text = load_policies(post.platform)
    status(f"✓ Policies loaded for {post.platform} ({len(policies_text):,} chars)")
    
    # Send to Claude
    status("⚡ Sending to Claude for analysis...")
    verdict = judge(post, policies_text, video_transcript)
    
    return verdict.to_dict()


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
    
    # Count how many input modes are specified
    input_modes = sum([
        bool(args.url),
        bool(args.text),
        bool(args.json),
        bool(args.json_file),
        bool(args.stdin)
    ])
    
    if input_modes == 0:
        print("Error: Must specify an input: URL, --text, --json, --json-file, or --stdin", file=sys.stderr)
        return 1
    
    if input_modes > 1:
        print("Error: Cannot combine multiple input modes. Use only one of: URL, --text, --json, --json-file, --stdin", file=sys.stderr)
        return 1
    
    if args.text and not args.platform:
        print("Error: --platform is required when using --text.", file=sys.stderr)
        return 1
    
    # Check API key upfront
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "Error: ANTHROPIC_API_KEY environment variable is not set.\n"
            "Create a .env file with: ANTHROPIC_API_KEY=your-key-here",
            file=sys.stderr
        )
        return 1
    
    # Handle JSON input modes (supports batch)
    if args.json or args.json_file or args.stdin:
        try:
            if args.json:
                posts_with_transcripts = parse_json_input(args.json)
                status(f"✓ Parsed {len(posts_with_transcripts)} post(s) from JSON")
            elif args.json_file:
                posts_with_transcripts = load_json_file(args.json_file)
                status(f"✓ Loaded {len(posts_with_transcripts)} post(s) from {args.json_file}")
            else:  # args.stdin
                posts_with_transcripts = load_json_stdin()
                status(f"✓ Read {len(posts_with_transcripts)} post(s) from stdin")
        except JsonInputError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        
        # Process each post
        verdicts = []
        for i, (post, video_transcript) in enumerate(posts_with_transcripts, 1):
            if len(posts_with_transcripts) > 1:
                status(f"\n--- Processing post {i}/{len(posts_with_transcripts)} ---")
            
            try:
                verdict_dict = process_single_post(post, video_transcript, quiet)
                verdicts.append(verdict_dict)
            except (PolicyNotFoundError, JudgmentError) as e:
                print(f"Error processing post {i}: {e}", file=sys.stderr)
                return 1
        
        # Output results
        if len(verdicts) == 1:
            json_output = json.dumps(verdicts[0], indent=2)
        else:
            json_output = json.dumps(verdicts, indent=2)
        
        print(json_output)
        
        if args.output:
            Path(args.output).write_text(json_output, encoding="utf-8")
            status(f"✓ Saved to {args.output}")
        
        return 0
    
    # Handle URL or --text input (single post, no batch)
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
    
    # Process the single post (no pre-provided transcript for URL/text mode)
    try:
        verdict_dict = process_single_post(post, None, quiet)
    except PolicyNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except JudgmentError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    # Output result
    json_output = json.dumps(verdict_dict, indent=2)
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
  # URL input (auto-detect platform)
  python policyguard.py check "https://reddit.com/r/example/comments/xyz/title"
  
  # Manual text input
  python policyguard.py check --platform facebook --text "The post text here"
  
  # JSON input (single post or batch array)
  python policyguard.py check --json '{"url": "https://facebook.com/...", "message": "post text"}'
  python policyguard.py check --json-file posts.json
  cat posts.json | python policyguard.py check --stdin
  
  # Options
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
    check_parser.add_argument("--text", "-t", help="Post text (for manual input, requires --platform)")
    check_parser.add_argument("--platform", "-p", help="Platform name (required with --text)")
    check_parser.add_argument("--json", "-j", help="JSON string with post data (single object or array)")
    check_parser.add_argument("--json-file", "-f", help="Path to JSON file with post data")
    check_parser.add_argument("--stdin", "-s", action="store_true", help="Read JSON from stdin")
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
