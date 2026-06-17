"""Validate scraped posts and export results to Excel.

Reads JSON files from scraper_results/, runs each post through the validator,
and exports comprehensive results to an Excel file.

Usage:
    cd /path/to/project && python scraper/validate_to_excel.py --skip-video --workers 8
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import concurrent.futures
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure we can find the core modules
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from core.judge import judge
from core.models import PostData, JudgmentError, PolicyNotFoundError, Verdict
from core.policy_loader import load_policies

RESULTS_DIR = Path(__file__).parent.parent / "scraper_results"
OUTPUT_DIR = Path(__file__).parent.parent / "validation_results"

# Thread-safe counter
progress_lock = threading.Lock()
progress_counter = {"processed": 0, "violations": 0, "errors": 0}

EXCEL_ILLEGAL_CHAR_RE = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]")

ANTI_OLEARY_SUBJECT_RE = re.compile(
    r"\b(kevin\s*o['’]leary|o['’]leary|oleary|mr\.?\s*wonderful|stratos|o['’]leary\s*digital)\b",
    re.IGNORECASE,
)
ANTI_DATACENTER_RE = re.compile(
    r"\b(data\s*cent(?:er|re)|datacenter|hyperscale|server\s*farm|ai\s*hub|ai\s*data\s*cent(?:er|re))\b",
    re.IGNORECASE,
)
ANTI_SIGNAL_RE = re.compile(
    r"\b(stop|oppose|against|boycott|petition|protest|backlash|outrage|reject|block|ban|no\s+data\s*cent(?:er|re)|"
    r"scam|grift|fraud|corrupt|dark\s*money|disinfo|misinfo|china|ccp|steal|water\s*grab|drain|pollute|destroy|ruin)\b",
    re.IGNORECASE,
)
PRO_SIGNAL_RE = re.compile(
    r"\b(support|back(s|ing)?|good\s+for\s+utah|jobs|investment|economic\s+growth|great\s+project|welcome|excited)\b",
    re.IGNORECASE,
)


def _is_anti_oleary_datacenter_post(post: dict[str, Any]) -> bool:
    """Heuristic stance filter: keep posts that are plausibly *against* the project."""
    text = " ".join(
        str(v)
        for v in [
            post.get("content_text") or "",
            post.get("url") or "",
            " ".join(post.get("hashtags") or []),
        ]
        if v
    )
    if not ANTI_OLEARY_SUBJECT_RE.search(text):
        return False
    if not ANTI_DATACENTER_RE.search(text):
        return False
    if not ANTI_SIGNAL_RE.search(text):
        return False
    # If it's explicitly supportive, exclude it (even if it mentions backlash).
    if PRO_SIGNAL_RE.search(text):
        return False
    return True


def load_scraped_posts(
    platform_filters: list[str] | None = None,
    input_files: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Load all scraped posts from JSON files."""
    posts = []

    files = [Path(path) for path in input_files] if input_files else sorted(RESULTS_DIR.glob("*.json"))

    for file in files:
        with open(file, encoding="utf-8") as f:
            data = json.load(f)
        
        file_posts = data.get("posts", [])
        if not file_posts:
            continue
        
        platform = data.get("metadata", {}).get("platform", "unknown")
        
        if platform_filters and platform not in platform_filters:
            continue
        
        for post in file_posts:
            post["_source_file"] = file.name
            post["_platform"] = platform
        
        posts.extend(file_posts)
        print(f"Loaded {len(file_posts)} posts from {file.name}")
    
    return posts


def post_to_postdata(post: dict[str, Any], skip_video: bool = False) -> PostData:
    """Convert scraped post dict to PostData for the validator."""
    platform = post.get("_platform") or post.get("platform", "tiktok")
    
    # Map platform names (twitter -> x for policy lookup)
    platform_map = {"twitter": "x"}
    platform = platform_map.get(platform, platform)
    
    url = post.get("url") or f"https://{platform}.com/p/{post.get('platform_post_id', 'unknown')}"
    
    image_urls = []
    if post.get("thumbnail_url"):
        image_urls.append(post["thumbnail_url"])
    
    # Skip video transcription if requested (saves ~90% of time)
    video_urls = []
    if not skip_video and post.get("video_url"):
        video_urls.append(post["video_url"])
    
    return PostData(
        url=url,
        platform=platform,
        text=post.get("content_text") or "",
        author=post.get("author_handle") or "",
        title="",
        image_urls=image_urls,
        video_urls=video_urls,
    )


# Global flag for skip_video option
SKIP_VIDEO = False


def validate_post(post: dict[str, Any], policies_cache: dict[str, str], total: int, skip_video: bool = False) -> dict[str, Any]:
    """Validate a single post and return results."""
    raw_platform = post.get("_platform") or post.get("platform", "tiktok")
    # Map twitter -> x for policy lookup and PostData validation
    platform_map = {"twitter": "x"}
    platform = platform_map.get(raw_platform, raw_platform)
    
    result = {
        "platform": platform,
        "post_id": post.get("platform_post_id"),
        "url": post.get("url"),
        "author": post.get("author_handle"),
        "content_text": (post.get("content_text") or "")[:500],  # Truncate for Excel
        "full_text": post.get("content_text") or "",  # Keep full for analysis
        "posted_at": post.get("posted_at"),
        "like_count": post.get("like_count"),
        "comment_count": post.get("comment_count"),
        "view_count": post.get("view_count"),
        "hashtags": ", ".join(post.get("hashtags", [])),
        "source_file": post.get("_source_file"),
    }
    
    try:
        # Get or load policies (thread-safe access)
        if platform not in policies_cache:
            with progress_lock:
                if platform not in policies_cache:  # Double-check after lock
                    policies_cache[platform] = load_policies(platform)
        
        post_data = post_to_postdata(post, skip_video=skip_video)
        verdict = judge(post_data, policies_cache[platform])
        
        unified_violations = list(verdict.violations)
        for warning in verdict.warnings:
            unified_violations.append(
                type("UnifiedViolation", (), {
                    "rule": warning.rule or warning.category,
                    "severity": warning.severity,
                    "explanation": warning.explanation,
                    "policy_reference": warning.policy_reference,
                    "quote": warning.quote or warning.problematic_element,
                })()
            )

        result["verdict"] = "FLAGGED" if unified_violations else "PASS"
        result["confidence"] = verdict.confidence
        result["recommendation"] = verdict.recommendation
        result["checked_at"] = verdict.checked_at
        result["violations_count"] = len(unified_violations)
        
        # Flatten every flagged finding as a violation for the Excel deliverable.
        if unified_violations:
            result["violation_rules"] = "; ".join(v.rule for v in unified_violations)
            result["violation_severities"] = "; ".join(v.severity for v in unified_violations)
            result["violation_explanations"] = "; ".join(v.explanation[:300] for v in unified_violations)
            result["violation_quotes"] = "; ".join(v.quote[:150] for v in unified_violations)
            result["violation_policy_refs"] = "; ".join(v.policy_reference for v in unified_violations)
        else:
            result["violation_rules"] = ""
            result["violation_severities"] = ""
            result["violation_explanations"] = ""
            result["violation_quotes"] = ""
            result["violation_policy_refs"] = ""
        
        # Flatten warnings (key for POSSIBLE_VIOLATION)
        if verdict.warnings:
            result["warnings_count"] = len(verdict.warnings)
            result["warning_categories"] = "; ".join(w.category for w in verdict.warnings)
            result["warning_risk_levels"] = "; ".join(w.risk_level for w in verdict.warnings)
            result["warning_rules"] = "; ".join(w.rule for w in verdict.warnings)
            result["warning_severities"] = "; ".join(w.severity for w in verdict.warnings)
            result["warning_policy_refs"] = "; ".join(w.policy_reference for w in verdict.warnings)
            result["warning_quotes"] = "; ".join((w.quote or w.problematic_element)[:100] for w in verdict.warnings)
            result["warning_explanations"] = "; ".join(w.explanation[:200] for w in verdict.warnings)
            result["warning_elements"] = "; ".join(w.problematic_element[:100] for w in verdict.warnings)
            result["warning_affected_groups"] = "; ".join(
                ", ".join(w.affected_groups) if w.affected_groups else "N/A" 
                for w in verdict.warnings
            )
            result["warning_why_matters"] = "; ".join(
                (w.why_it_matters[:150] if w.why_it_matters else "N/A") 
                for w in verdict.warnings
            )
        else:
            result["warnings_count"] = 0
            result["warning_categories"] = ""
            result["warning_risk_levels"] = ""
            result["warning_rules"] = ""
            result["warning_severities"] = ""
            result["warning_policy_refs"] = ""
            result["warning_quotes"] = ""
            result["warning_explanations"] = ""
            result["warning_elements"] = ""
            result["warning_affected_groups"] = ""
            result["warning_why_matters"] = ""

        result["passed_checks"] = ", ".join(verdict.passed_checks)
        result["report_message"] = verdict.generate_report_message()[:5000] if verdict.verdict != "PASS" else ""
        result["error"] = ""

        # Always prefer the constructed URL used for validation (fills gaps).
        result["url"] = post_data.url
        
        # Update progress
        with progress_lock:
            progress_counter["processed"] += 1
            if verdict.violations or verdict.warnings:
                progress_counter["violations"] += 1
            if progress_counter["processed"] % 50 == 0:
                print(f"  Progress: {progress_counter['processed']}/{total} "
                      f"({progress_counter['violations']} flagged, {progress_counter['errors']} errors)")
        
    except PolicyNotFoundError as e:
        result["verdict"] = "ERROR"
        result["model_verdict"] = "ERROR"
        result["error"] = f"Policy not found: {e}"
        result["confidence"] = 0
        result["findings_count"] = 0
        result["violations_count"] = 0
        result["warnings_count"] = 0
        with progress_lock:
            progress_counter["processed"] += 1
            progress_counter["errors"] += 1
        
    except JudgmentError as e:
        result["verdict"] = "ERROR"
        result["model_verdict"] = "ERROR"
        result["error"] = f"Judgment error: {str(e)[:300]}"
        result["confidence"] = 0
        result["findings_count"] = 0
        result["violations_count"] = 0
        result["warnings_count"] = 0
        with progress_lock:
            progress_counter["processed"] += 1
            progress_counter["errors"] += 1
        
    except Exception as e:
        result["verdict"] = "ERROR"
        result["model_verdict"] = "ERROR"
        result["error"] = f"Unexpected: {str(e)[:300]}"
        result["confidence"] = 0
        result["findings_count"] = 0
        result["violations_count"] = 0
        result["warnings_count"] = 0
        with progress_lock:
            progress_counter["processed"] += 1
            progress_counter["errors"] += 1
    
    return result


def export_to_excel(results: list[dict[str, Any]], output_path: Path) -> None:
    """Export flagged validation results to Excel file."""
    try:
        import pandas as pd
    except ImportError:
        print("pandas not installed. Installing...")
        os.system("pip3 install pandas openpyxl")
        import pandas as pd
    
    df = pd.DataFrame(results)
    total_results = len(df)

    # Deliverable files should contain only posts that need review/reporting.
    if "verdict" in df.columns:
        df = df[df["verdict"] == "FLAGGED"].copy()
    
    # Keep all current columns except the ones the user explicitly excluded:
    # platform, verdict, confidence, violation_severities, passed_checks,
    # checked_at, report_message, error, source_file
    column_order = [
        # Unified violation detail. Warning-level findings are included here.
        "violations_count",
        "violation_rules",
        "violation_explanations",
        "violation_quotes",
        "violation_policy_refs",
        # Post metadata
        "post_id",
        "url",
        "author",
        "content_text",
        "posted_at",
        "like_count",
        "comment_count",
        "view_count",
        "hashtags",
        # Other
        "recommendation",
    ]
    
    # Only include columns that exist
    columns = [c for c in column_order if c in df.columns]
    df = df[columns]

    # openpyxl rejects ASCII control characters that can appear in scraped text.
    df = df.map(
        lambda value: EXCEL_ILLEGAL_CHAR_RE.sub("", value)
        if isinstance(value, str)
        else value
    )
    
    # Save to Excel
    df.to_excel(output_path, index=False, engine="openpyxl")
    print(f"\nExported {len(df)} flagged results to: {output_path} ({total_results} processed)")
    
    # Also export a summary CSV for quick viewing
    summary_path = output_path.with_suffix(".summary.csv")
    summary_cols = [
        "violations_count",
        "violation_rules",
        "violation_policy_refs",
        "author",
        "content_text",
        "url",
    ]
    summary_cols = [c for c in summary_cols if c in df.columns]
    df[summary_cols].to_csv(summary_path, index=False)
    print(f"Exported summary to: {summary_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate scraped posts and export to Excel")
    parser.add_argument("--platform", action="append", choices=["tiktok", "instagram", "facebook", "twitter", "linkedin", "reddit"], 
                        help="Filter by platform (can specify multiple)")
    parser.add_argument("--limit", type=int, help="Limit number of posts to process")
    parser.add_argument("--output", type=str, help="Output Excel file path")
    parser.add_argument(
        "--input-file",
        action="append",
        help="Validate only this scraped JSON file (can specify multiple)",
    )
    parser.add_argument("--workers", type=int, default=5, help="Number of parallel workers (default: 5)")
    parser.add_argument("--skip-video", action="store_true", help="Skip video transcription (much faster)")
    parser.add_argument(
        "--anti-only",
        action="store_true",
        help="Only validate posts that are against Kevin O'Leary's Utah data center (heuristic stance filter).",
    )
    parser.add_argument(
        "--anti-mode",
        choices=["heuristic", "llm"],
        default="llm",
        help="How to detect anti-project stance when --anti-only is set (default: llm).",
    )
    parser.add_argument(
        "--anti-strength",
        choices=["exact", "strict"],
        default="exact",
        help="How strict the stance must be when using --anti-only with --anti-mode llm (default: exact).",
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("SIGIL CONTENT VALIDATOR - Batch Processing")
    print("=" * 70)
    
    # Load posts
    posts = load_scraped_posts(args.platform, args.input_file)
    
    if not posts:
        print("No posts found to validate.")
        return 1
    
    if args.anti_only:
        if args.anti_mode == "heuristic":
            before = len(posts)
            posts = [p for p in posts if _is_anti_oleary_datacenter_post(p)]
            print(f"Anti-only filter (heuristic): {len(posts)}/{before} kept")
        else:
            # LLM stance filter for higher recall.
            from openai import OpenAI, OpenAIError

            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                print("OPENAI_API_KEY missing; falling back to heuristic anti filter.")
                before = len(posts)
                posts = [p for p in posts if _is_anti_oleary_datacenter_post(p)]
                print(f"Anti-only filter (heuristic): {len(posts)}/{before} kept")
            else:
                client = OpenAI(api_key=api_key)

                def classify_against(post: dict[str, Any]) -> bool:
                    text = (post.get("content_text") or "")[:4000]
                    url = post.get("url") or ""
                    if args.anti_strength == "strict":
                        criteria = (
                            "AGAINST must be explicit (calls to stop/block/oppose, supports protests/backlash, or allegations tied to the project)."
                        )
                    else:
                        criteria = (
                            "AGAINST can be subtle (negative framing/tone, skepticism, concerns about water/power/environment), "
                            "but it must still be opposing/negative about the project."
                        )
                    prompt = (
                        "Classify whether this post is AGAINST Kevin O'Leary building the Utah/Stratos AI data center project "
                        f"(must be about Kevin/O'Leary and the Utah/Stratos data center; {criteria}).\n\n"
                        "Return ONLY JSON: {\"against\": true|false}.\n\n"
                        f"URL: {url}\n"
                        f"TEXT: {text}\n"
                    )
                    try:
                        resp = client.chat.completions.create(
                            model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
                            max_tokens=50,
                            response_format={"type": "json_object"},
                            messages=[
                                {"role": "system", "content": "You are a strict stance classifier. Output JSON only."},
                                {"role": "user", "content": prompt},
                            ],
                        )
                        raw = (resp.choices[0].message.content or "").strip()
                        data = json.loads(raw)
                        return bool(data.get("against"))
                    except (OpenAIError, json.JSONDecodeError, Exception):
                        return False

                before = len(posts)
                kept: list[dict[str, Any]] = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, args.workers * 2)) as ex:
                    futs = [ex.submit(classify_against, p) for p in posts]
                    for p, fut in zip(posts, futs):
                        if fut.result():
                            kept.append(p)
                posts = kept
                print(f"Anti-only filter (llm): {len(posts)}/{before} kept")

    if args.limit:
        posts = posts[:args.limit]
    
    total = len(posts)
    print(f"\nTotal posts to validate: {total}")
    print(f"Using {args.workers} parallel workers")
    if args.skip_video:
        print("Video transcription: DISABLED (text/image analysis only)")
    
    # Estimate: ~3 sec/post without video, ~15 sec/post with video
    sec_per_post = 3 if args.skip_video else 15
    estimated_minutes = (total * sec_per_post) / 60 / args.workers
    print(f"Estimated time: ~{estimated_minutes:.0f} minutes")
    print("=" * 70)
    
    # Validate with parallel processing
    results = []
    policies_cache: dict[str, str] = {}
    
    skip_video = args.skip_video
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(validate_post, post, policies_cache, total, skip_video): post 
            for post in posts
        }
        
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                print(f"Worker error: {e}")
    
    # Sort by source file to maintain original order
    results.sort(key=lambda x: (x.get("source_file", ""), x.get("post_id", "")))
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    total_processed = len(results)
    passes = sum(1 for r in results if r.get("verdict") == "PASS")
    flagged = sum(1 for r in results if r.get("verdict") == "FLAGGED")
    errors = sum(1 for r in results if r.get("verdict") == "ERROR")
    
    print(f"Total processed: {total_processed}")
    print(f"  PASS: {passes} ({100*passes/total_processed:.1f}%)")
    print(f"  FLAGGED: {flagged} ({100*flagged/total_processed:.1f}%)")
    print(f"  ERROR: {errors} ({100*errors/total_processed:.1f}%)")
    
    # Export
    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    
    if args.output:
        output_path = Path(args.output)
    else:
        if args.input_file:
            platform_suffix = Path(args.input_file[0]).stem
        else:
            platform_suffix = "_".join(args.platform) if args.platform else "all"
        output_path = OUTPUT_DIR / f"validation_{platform_suffix}_{timestamp}.xlsx"
    
    export_to_excel(results, output_path)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
