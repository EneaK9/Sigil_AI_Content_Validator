"""CLI for running validation on scraped posts.

Usage:
    python -m scraper.integration.cli validate [--platform PLATFORM] [--limit N]
    python -m scraper.integration.cli report [--platform PLATFORM] [--severity SEVERITY]
    python -m scraper.integration.cli stats
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any
from uuid import UUID

from scraper.config import get_settings
from scraper.integration.pipeline import (
    ValidationStatus,
    fetch_violations,
    get_validation_stats,
    validate_scraped_posts,
)
from scraper.logging_setup import configure_logging


def print_header(text: str, char: str = "=") -> None:
    """Print a formatted header."""
    print(f"\n{char * 60}")
    print(f" {text}")
    print(f"{char * 60}\n")


def print_violation(idx: int, row: dict[str, Any]) -> None:
    """Print a single violation entry."""
    print(f"{idx}. Post: {row.get('url', 'N/A')}")
    print(f"   Author: @{row.get('author_handle', 'unknown')}")
    print(f"   Platform: {row.get('platform', 'unknown')}")
    if row.get("topic"):
        print(f"   Topic: {row['topic']}")
    
    violations = row.get("violations") or []
    for v in violations:
        severity = v.get("severity", "UNKNOWN")
        rule = v.get("rule", "Unknown rule")
        print(f"   Violation: {rule} ({severity})")
        if v.get("quote"):
            quote = v["quote"][:100] + "..." if len(v.get("quote", "")) > 100 else v.get("quote", "")
            print(f"   Quote: \"{quote}\"")
        if v.get("explanation"):
            print(f"   Explanation: {v['explanation'][:150]}...")
    
    print()


async def cmd_validate(args: argparse.Namespace) -> int:
    """Run validation on pending scraped posts."""
    print_header("VALIDATION RUN")
    
    print(f"Configuration:")
    print(f"  Platform filter: {args.platform or 'all'}")
    print(f"  Limit: {args.limit}")
    if args.campaign_id:
        print(f"  Campaign ID: {args.campaign_id}")
    print()
    
    campaign_id = UUID(args.campaign_id) if args.campaign_id else None
    
    results = await validate_scraped_posts(
        campaign_id=campaign_id,
        platform=args.platform,
        limit=args.limit,
    )
    
    if not results:
        print("No pending posts found to validate.")
        return 0
    
    passed = [r for r in results if r.get("status") == ValidationStatus.PASS]
    failed = [r for r in results if r.get("status") == ValidationStatus.FAIL]
    errors = [r for r in results if r.get("status") == ValidationStatus.ERROR]
    
    print_header("VALIDATION RESULTS")
    
    print(f"Total processed: {len(results)}")
    print(f"  Passed: {len(passed)}")
    print(f"  Failed (violations): {len(failed)}")
    print(f"  Errors: {len(errors)}")
    print()
    
    if failed:
        print_header("VIOLATIONS FOUND", "-")
        for idx, result in enumerate(failed, 1):
            print(f"{idx}. {result.get('url', 'N/A')}")
            print(f"   Author: @{result.get('author', 'unknown')}")
            for v in result.get("violations", []):
                print(f"   - {v.get('rule')} ({v.get('severity')})")
                if v.get("quote"):
                    quote = v["quote"][:80] + "..." if len(v.get("quote", "")) > 80 else v.get("quote", "")
                    print(f"     \"{quote}\"")
            print()
    
    if errors:
        print_header("ERRORS", "-")
        for result in errors:
            print(f"  - {result.get('url', 'N/A')}: {result.get('error', 'Unknown error')}")
    
    return 0


async def cmd_report(args: argparse.Namespace) -> int:
    """Generate a violations report."""
    print_header("VIOLATIONS REPORT")
    
    print(f"Filters:")
    print(f"  Platform: {args.platform or 'all'}")
    print(f"  Severity: {args.severity or 'all'}")
    print(f"  Limit: {args.limit}")
    print()
    
    violations = await fetch_violations(
        platform=args.platform,
        severity=args.severity,
        limit=args.limit,
    )
    
    if not violations:
        print("No violations found matching the criteria.")
        return 0
    
    by_platform: dict[str, list[dict[str, Any]]] = {}
    for row in violations:
        plat = row.get("platform", "unknown")
        if plat not in by_platform:
            by_platform[plat] = []
        by_platform[plat].append(row)
    
    for platform, rows in sorted(by_platform.items()):
        print_header(f"{platform.upper()} VIOLATIONS ({len(rows)} posts)", "=")
        
        for idx, row in enumerate(rows, 1):
            print_violation(idx, row)
    
    print_header("SUMMARY")
    
    total_violations = sum(len(r.get("violations", [])) for r in violations)
    
    severity_counts: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for row in violations:
        for v in row.get("violations", []):
            sev = v.get("severity", "UNKNOWN")
            if sev in severity_counts:
                severity_counts[sev] += 1
    
    print(f"Total posts with violations: {len(violations)}")
    print(f"Total violation instances: {total_violations}")
    print()
    print("By platform:")
    for plat, rows in sorted(by_platform.items()):
        print(f"  - {plat}: {len(rows)} posts")
    print()
    print("By severity:")
    for sev, count in severity_counts.items():
        print(f"  - {sev}: {count}")
    
    return 0


async def cmd_stats(args: argparse.Namespace) -> int:
    """Show validation statistics."""
    print_header("VALIDATION STATISTICS")
    
    stats = await get_validation_stats()
    
    print(f"Total posts in database: {stats['total_posts']}")
    print(f"Pending validation: {stats['pending_validation']}")
    print()
    print("Validation results:")
    print(f"  Passed: {stats['passed']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Errors: {stats['errors']}")
    print()
    
    if stats["by_platform"]:
        print("By platform:")
        for plat, counts in sorted(stats["by_platform"].items()):
            passed = counts.get("PASS", 0)
            failed = counts.get("FAIL", 0)
            total = passed + failed
            print(f"  - {plat}: {total} validated ({passed} PASS, {failed} FAIL)")
    
    return 0


def main() -> int:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="scraper-validator",
        description="Validate scraped posts against platform policies",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    validate_parser = subparsers.add_parser(
        "validate",
        help="Run validation on pending scraped posts",
    )
    validate_parser.add_argument(
        "--platform",
        choices=["tiktok", "instagram", "facebook"],
        help="Filter by platform",
    )
    validate_parser.add_argument(
        "--campaign-id",
        help="Filter by campaign UUID",
    )
    validate_parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of posts to validate (default: 100)",
    )
    
    report_parser = subparsers.add_parser(
        "report",
        help="Generate a violations report",
    )
    report_parser.add_argument(
        "--platform",
        choices=["tiktok", "instagram", "facebook"],
        help="Filter by platform",
    )
    report_parser.add_argument(
        "--severity",
        choices=["HIGH", "MEDIUM", "LOW"],
        help="Filter by violation severity",
    )
    report_parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of violations to show (default: 100)",
    )
    
    stats_parser = subparsers.add_parser(
        "stats",
        help="Show validation statistics",
    )
    
    args = parser.parse_args()
    
    settings = get_settings()
    configure_logging(settings.log_level)
    
    if args.command == "validate":
        return asyncio.run(cmd_validate(args))
    elif args.command == "report":
        return asyncio.run(cmd_report(args))
    elif args.command == "stats":
        return asyncio.run(cmd_stats(args))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
