"""One-off bulk scraper that saves results to local JSON files.

This script runs Apify scrapes immediately and saves results locally.
No database setup required - perfect for one-time bulk data collection.

Usage:
    python -m scraper.bulk_scrape_local
    python -m scraper.bulk_scrape_local --platform tiktok --limit 500
    
Output:
    Results are saved to scraper_results/
    - tiktok_albania_political_YYYYMMDD_HHMMSS.json
    - instagram_albania_political_YYYYMMDD_HHMMSS.json
    - facebook_albania_political_YYYYMMDD_HHMMSS.json
    - twitter_albania_political_YYYYMMDD_HHMMSS.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scraper.apify.client import ApifyRunStatus, ApifyService
from scraper.config import get_settings, load_campaigns
from scraper.logging_setup import configure_logging, get_logger
from scraper.models import Campaign, Platform
from scraper.platforms.base import get_scraper
from scraper.relevance import filter_and_dedupe_posts

import scraper.platforms  # noqa: F401 - register adapters

log = get_logger(__name__)

RESULTS_DIR = Path(__file__).parent.parent / "scraper_results"


def save_results(
    platform: str,
    topic: str,
    posts: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> Path:
    """Save scrape results to a JSON file."""
    RESULTS_DIR.mkdir(exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{platform}_{topic}_{timestamp}.json"
    filepath = RESULTS_DIR / filename
    
    output = {
        "metadata": {
            "platform": platform,
            "topic": topic,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "total_posts": len(posts),
            **metadata,
        },
        "posts": posts,
    }
    
    filepath.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    return filepath


async def run_single_campaign(
    apify: ApifyService,
    campaign: Campaign,
    results_limit: int,
    relevance_filter: bool,
) -> dict[str, Any]:
    """Run a single campaign and return results summary."""
    settings = get_settings()
    adapter = get_scraper(campaign.platform)
    
    if not adapter:
        return {
            "campaign_id": str(campaign.id),
            "platform": campaign.platform.value,
            "status": "error",
            "error": f"No adapter for platform {campaign.platform.value}",
        }
    
    actor_id = settings.actor_id_for(campaign.platform)
    
    run_input = adapter.build_input(campaign)
    run_input["resultsLimit"] = results_limit
    
    print(f"\n{'='*60}")
    print(f"Starting {campaign.platform.value.upper()} scrape")
    print(f"Topic: {campaign.topic}")
    print(f"Seeds: {', '.join(campaign.seeds[:5])}{'...' if len(campaign.seeds) > 5 else ''}")
    print(f"Target: {results_limit} posts")
    print(f"{'='*60}")
    
    try:
        print(f"Starting Apify actor: {actor_id}")
        info = await apify.start_run(actor_id, run_input)
        
        print(f"Apify run started: {info.run_id}")
        print(f"Dataset ID: {info.dataset_id}")
        print("Waiting for completion (this may take several minutes)...")
        
        poll_count = 0
        while True:
            await asyncio.sleep(30)
            poll_count += 1
            status_info = await apify.get_run(info.run_id)
            
            if status_info.status.is_terminal:
                break
            
            print(f"  [{poll_count * 30}s] Status: {status_info.status.value}...")
        
        print(f"Run completed with status: {status_info.status.value}")
        
        if status_info.status != ApifyRunStatus.SUCCEEDED:
            return {
                "campaign_id": str(campaign.id),
                "platform": campaign.platform.value,
                "status": "failed",
                "error": f"Apify run failed: {status_info.status.value}",
            }
        
        print("Fetching and normalizing results...")
        posts: list[dict[str, Any]] = []
        raw_items: list[dict[str, Any]] = []
        failed_count = 0
        
        async for raw_item in apify.iter_dataset_items(info.dataset_id):
            raw_items.append(raw_item)
            try:
                normalized = adapter.normalize(raw_item, campaign)
                if normalized:
                    post_dict = {
                        "platform": normalized.platform.value,
                        "platform_post_id": normalized.platform_post_id,
                        "url": normalized.url,
                        "author_handle": normalized.author_handle,
                        "author_id": normalized.author_id,
                        "content_text": normalized.content_text,
                        "posted_at": normalized.posted_at.isoformat() if normalized.posted_at else None,
                        "like_count": normalized.like_count,
                        "comment_count": normalized.comment_count,
                        "share_count": normalized.share_count,
                        "view_count": normalized.view_count,
                        "media_type": normalized.media_type,
                        "has_video": normalized.has_video,
                        "video_url": normalized.video_url,
                        "thumbnail_url": normalized.thumbnail_url,
                        "hashtags": normalized.hashtags,
                        "mentions": normalized.mentions,
                        "country": normalized.country,
                        "topic": normalized.topic,
                    }
                    posts.append(post_dict)
            except Exception as e:
                failed_count += 1
                if failed_count <= 5:
                    log.warning("normalize_failed", error=str(e))

        filter_stats = {
            "input_count": len(posts),
            "irrelevant_count": 0,
            "duplicate_count": 0,
            "kept_count": len(posts),
        }
        if relevance_filter:
            posts, filter_stats = filter_and_dedupe_posts(posts)
            print(
                "Relevance/dedupe filter: "
                f"{filter_stats['kept_count']} kept, "
                f"{filter_stats['irrelevant_count']} irrelevant, "
                f"{filter_stats['duplicate_count']} duplicates"
            )
        
        filepath = save_results(
            platform=campaign.platform.value,
            topic=campaign.topic,
            posts=posts,
            metadata={
                "seeds": campaign.seeds,
                "country": campaign.country,
                "apify_run_id": info.run_id,
                "apify_dataset_id": info.dataset_id,
                "cost_usd": status_info.cost_usd,
                "raw_items_count": len(raw_items),
                "normalized_count": filter_stats["input_count"],
                "saved_count": len(posts),
                "failed_count": failed_count,
                **filter_stats,
            },
        )
        
        print(f"Saved {len(posts)} posts to: {filepath}")
        print(f"Cost: ${status_info.cost_usd:.2f}" if status_info.cost_usd else "Cost: N/A")
        
        return {
            "campaign_id": str(campaign.id),
            "platform": campaign.platform.value,
            "status": "success",
            "items_fetched": len(raw_items),
            "items_saved": len(posts),
            "items_failed": failed_count,
            "cost_usd": status_info.cost_usd,
            "output_file": str(filepath),
        }
        
    except Exception as e:
        log.error("bulk_scrape_error", platform=campaign.platform.value, error=str(e), exc_info=True)
        return {
            "campaign_id": str(campaign.id),
            "platform": campaign.platform.value,
            "status": "error",
            "error": str(e),
        }


async def run_bulk_scrape(
    platform_filter: str | None = None,
    results_limit: int = 2000,
    relevance_filter: bool = True,
) -> list[dict[str, Any]]:
    """Run bulk scrapes for all enabled campaigns.
    
    Args:
        platform_filter: Optional platform to filter (tiktok, instagram, facebook, twitter)
        results_limit: Maximum results per campaign (default: 2000)
        
    Returns:
        List of result summaries per campaign
    """
    settings = get_settings()
    configure_logging(settings.log_level)
    
    apify = ApifyService(token=settings.apify_token)
    campaigns = load_campaigns()
    
    enabled_campaigns = [c for c in campaigns if c.enabled]
    
    if platform_filter:
        enabled_campaigns = [
            c for c in enabled_campaigns 
            if c.platform.value == platform_filter
        ]
    
    if not enabled_campaigns:
        print("No enabled campaigns found matching criteria.")
        return []
    
    print(f"\n{'#'*60}")
    print(f"# BULK SCRAPE (Local Storage)")
    print(f"# {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"# Campaigns: {len(enabled_campaigns)}")
    print(f"# Results limit per campaign: {results_limit}")
    print(f"# Relevance filter: {'on' if relevance_filter else 'off'}")
    print(f"# Output directory: {RESULTS_DIR}")
    print(f"{'#'*60}")
    
    results = []
    
    for campaign in enabled_campaigns:
        result = await run_single_campaign(
            apify,
            campaign,
            results_limit,
            relevance_filter=relevance_filter,
        )
        results.append(result)
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    total_saved = 0
    total_cost = 0.0
    
    for r in results:
        status_icon = "✓" if r["status"] == "success" else "✗"
        print(f"{status_icon} {r['platform'].upper()}: ", end="")
        
        if r["status"] == "success":
            print(f"{r['items_saved']} posts saved to {r.get('output_file', 'N/A')}")
            total_saved += r.get("items_saved", 0)
            if r.get("cost_usd"):
                total_cost += r["cost_usd"]
        else:
            print(f"FAILED - {r.get('error', 'Unknown error')}")
    
    print(f"\nTotal posts saved: {total_saved}")
    print(f"Total cost: ${total_cost:.2f}")
    print(f"Results directory: {RESULTS_DIR}")
    
    return results


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="bulk_scrape_local",
        description="Run one-off bulk scrapes and save to local JSON files",
    )
    parser.add_argument(
        "--platform",
        choices=["tiktok", "instagram", "facebook", "twitter", "linkedin", "reddit"],
        help="Filter by platform (run all if not specified)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=2000,
        help="Maximum results per campaign (default: 2000)",
    )
    parser.add_argument(
        "--no-relevance-filter",
        action="store_true",
        help="Save all normalized posts without Albania/Kushner/Trump filtering",
    )
    
    args = parser.parse_args()
    
    print("\n" + "!"*60)
    print("! WARNING: This will run Apify scrapes which cost money!")
    print(f"! Estimated cost: ~$3-15 for {args.limit * 3} posts")
    print("!"*60)
    
    try:
        input("\nPress Enter to continue or Ctrl+C to cancel...")
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 0
    
    try:
        results = asyncio.run(run_bulk_scrape(
            platform_filter=args.platform,
            results_limit=args.limit,
            relevance_filter=not args.no_relevance_filter,
        ))
        
        failed = [r for r in results if r["status"] != "success"]
        return 1 if failed else 0
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 130
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
