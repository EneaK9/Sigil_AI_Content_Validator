"""One-off bulk scraper for immediate execution.

This script runs Apify scrapes immediately without waiting for the scheduler.
It's designed for one-time bulk data collection.

Usage:
    python -m scraper.bulk_scrape
    python -m scraper.bulk_scrape --platform tiktok --limit 500
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from scraper.apify.client import ApifyRunStatus, ApifyService
from scraper.config import get_settings, load_campaigns
from scraper.db import repository
from scraper.db.engine import dispose_engine
from scraper.logging_setup import configure_logging, get_logger
from scraper.models import Campaign, Platform, RunStatus
from scraper.platforms.base import get_scraper

import scraper.platforms  # noqa: F401 - register adapters

log = get_logger(__name__)


async def run_single_campaign(
    apify: ApifyService,
    campaign: Campaign,
    results_limit: int,
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
    
    run_id = uuid4()
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
        await repository.upsert_campaigns([campaign])
        
        await repository.create_run(
            run_id=run_id,
            campaign_id=campaign.id,
            platform=campaign.platform,
            status=RunStatus.requested,
        )
        
        print(f"Starting Apify actor: {actor_id}")
        info = await apify.start_run(actor_id, run_input)
        
        await repository.mark_run_running(
            run_id=run_id,
            apify_run_id=info.run_id,
            apify_dataset_id=info.dataset_id,
        )
        
        print(f"Apify run started: {info.run_id}")
        print(f"Dataset ID: {info.dataset_id}")
        print("Waiting for completion (this may take several minutes)...")
        
        while True:
            await asyncio.sleep(30)
            status_info = await apify.get_run(info.run_id)
            
            if status_info.status.is_terminal:
                break
            
            print(f"  Status: {status_info.status.value}...")
        
        print(f"Run completed with status: {status_info.status.value}")
        
        if status_info.status != ApifyRunStatus.SUCCEEDED:
            await repository.finish_run(
                run_id=run_id,
                status=RunStatus.failed,
                error=f"Apify status: {status_info.status.value}",
            )
            return {
                "campaign_id": str(campaign.id),
                "platform": campaign.platform.value,
                "status": "failed",
                "error": f"Apify run failed: {status_info.status.value}",
            }
        
        print("Ingesting results to database...")
        posts = []
        item_count = 0
        failed_count = 0
        
        async for raw_item in apify.iter_dataset_items(info.dataset_id):
            item_count += 1
            try:
                normalized = adapter.normalize(raw_item, campaign)
                if normalized:
                    posts.append(normalized)
            except Exception as e:
                failed_count += 1
                if failed_count <= 5:
                    log.warning("normalize_failed", error=str(e))
        
        if posts:
            await repository.upsert_posts(posts)
        
        await repository.finish_run(
            run_id=run_id,
            status=RunStatus.succeeded,
            items_ingested=len(posts),
            items_failed=failed_count,
            cost_usd=status_info.cost_usd,
        )
        
        print(f"Ingested {len(posts)} posts ({failed_count} failed to normalize)")
        print(f"Cost: ${status_info.cost_usd:.2f}" if status_info.cost_usd else "Cost: N/A")
        
        return {
            "campaign_id": str(campaign.id),
            "platform": campaign.platform.value,
            "status": "success",
            "items_fetched": item_count,
            "items_ingested": len(posts),
            "items_failed": failed_count,
            "cost_usd": status_info.cost_usd,
        }
        
    except Exception as e:
        log.error("bulk_scrape_error", platform=campaign.platform.value, error=str(e), exc_info=True)
        await repository.finish_run(
            run_id=run_id,
            status=RunStatus.failed,
            error=str(e),
        )
        return {
            "campaign_id": str(campaign.id),
            "platform": campaign.platform.value,
            "status": "error",
            "error": str(e),
        }


async def run_bulk_scrape(
    platform_filter: str | None = None,
    results_limit: int = 2000,
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
    print(f"# BULK SCRAPE - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"# Campaigns: {len(enabled_campaigns)}")
    print(f"# Results limit per campaign: {results_limit}")
    print(f"{'#'*60}")
    
    results = []
    
    for campaign in enabled_campaigns:
        result = await run_single_campaign(apify, campaign, results_limit)
        results.append(result)
    
    await dispose_engine()
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    total_ingested = 0
    total_cost = 0.0
    
    for r in results:
        status_icon = "✓" if r["status"] == "success" else "✗"
        print(f"{status_icon} {r['platform'].upper()}: ", end="")
        
        if r["status"] == "success":
            print(f"{r['items_ingested']} posts ingested")
            total_ingested += r.get("items_ingested", 0)
            if r.get("cost_usd"):
                total_cost += r["cost_usd"]
        else:
            print(f"FAILED - {r.get('error', 'Unknown error')}")
    
    print(f"\nTotal posts ingested: {total_ingested}")
    print(f"Total cost: ${total_cost:.2f}")
    
    return results


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="bulk_scrape",
        description="Run one-off bulk scrapes immediately",
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
    
    args = parser.parse_args()
    
    try:
        results = asyncio.run(run_bulk_scrape(
            platform_filter=args.platform,
            results_limit=args.limit,
        ))
        
        failed = [r for r in results if r["status"] != "success"]
        return 1 if failed else 0
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 130
    except Exception as e:
        print(f"\nFatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
