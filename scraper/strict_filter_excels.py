"""Filter ANTI excels to only posts against Kevin O'Leary Utah data center.

Reads one or more validation_result .xlsx files and writes filtered copies
containing only rows that match the requested stance criteria.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError


def _hash_key(url: str, text: str) -> str:
    h = hashlib.sha256()
    h.update(url.strip().encode("utf-8", errors="ignore"))
    h.update(b"\n")
    h.update(text.strip().encode("utf-8", errors="ignore"))
    return h.hexdigest()


def _against_classifier(
    client: OpenAI,
    model: str,
    *,
    mode: str,
    url: str,
    text: str,
) -> bool:
    if mode == "strict":
        criteria = (
            "KEEP=true ONLY IF ALL are true:\n"
            "1) The post is about Kevin O'Leary (or O'Leary Digital / Mr. Wonderful).\n"
            "2) The post is about the Utah/Stratos data center project (data center, hyperscale, AI hub in Utah/Box Elder/Hansel Valley).\n"
            "3) The stance is clearly negative/opposed (calls to stop/block/oppose, protests/backlash support, allegations of wrongdoing tied to the project).\n"
        )
    else:
        # "Exact against" but high recall: even subtle negative tone counts.
        criteria = (
            "KEEP=true ONLY IF ALL are true:\n"
            "1) The post is about Kevin O'Leary (or O'Leary Digital / Mr. Wonderful).\n"
            "2) The post is about the Utah/Stratos data center project (data center, hyperscale, AI hub in Utah/Box Elder/Hansel Valley).\n"
            "3) The stance is against / negative / skeptical about the project, even if subtle "
            "(e.g., concerns about water/power/environment, criticism, doubt, sarcasm, negative framing).\n"
        )

    prompt = (
        "Decide if this post is about and AGAINST Kevin O'Leary building the Utah/Stratos AI data center.\n"
        "\n"
        "Return ONLY JSON: {\"keep\": true|false}.\n"
        "\n"
        f"{criteria}\n"
        "\n"
        "KEEP=false if any are missing, including:\n"
        "- Neutral news/info without negative stance\n"
        "- General anti-data-center content not tied to Kevin O'Leary\n"
        "- Pro/neutral stance\n"
        "\n"
        f"URL: {url}\n"
        f"TEXT: {text[:6000]}\n"
    )
    response = client.chat.completions.create(
        model=model,
        max_tokens=60,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "You are a strict stance classifier. Output JSON only."},
            {"role": "user", "content": prompt},
        ],
    )
    raw = (response.choices[0].message.content or "").strip()
    data = json.loads(raw)
    return bool(data.get("keep"))


def filter_excel(path: Path, *, model: str, workers: int, mode: str) -> Path:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set; cannot run strict filter.")

    client = OpenAI(api_key=api_key)

    df = pd.read_excel(path)
    if df.empty:
        out = path.with_name(path.stem + "_ANTI_STRICT" + path.suffix)
        df.to_excel(out, index=False, engine="openpyxl")
        return out

    cache: dict[str, bool] = {}

    def decide(row: dict[str, Any]) -> bool:
        url = str(row.get("url") or "")
        text = str(row.get("content_text") or "")
        key = _hash_key(url, text)
        if key in cache:
            return cache[key]
        keep = _against_classifier(client, model, mode=mode, url=url, text=text)
        cache[key] = keep
        return keep

    # Threading: OpenAI client is thread-safe for simple request/response usage.
    import concurrent.futures

    rows = df.to_dict(orient="records")
    kept_mask: list[bool] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(decide, r) for r in rows]
        for i, fut in enumerate(futures, 1):
            try:
                kept_mask.append(bool(fut.result()))
            except (OpenAIError, json.JSONDecodeError, Exception):
                kept_mask.append(False)
            if i % 50 == 0:
                print(f"{path.name}: classified {i}/{len(rows)}")

    filtered = df[kept_mask].copy()
    suffix = "_ANTI_EXACT" if mode == "exact" else "_ANTI_STRICT"
    out = path.with_name(path.stem + suffix + path.suffix)
    filtered.to_excel(out, index=False, engine="openpyxl")

    # Also write summary CSV next to it (mirrors validate_to_excel.py)
    summary_cols = [
        "violations_count",
        "violation_rules",
        "violation_policy_refs",
        "author",
        "content_text",
        "url",
    ]
    summary_cols = [c for c in summary_cols if c in filtered.columns]
    filtered[summary_cols].to_csv(out.with_suffix(".summary.csv"), index=False)

    print(f"{path.name}: kept {len(filtered)}/{len(df)} → {out.name}")
    return out


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Stance filter for Kevin anti-project excels")
    parser.add_argument("files", nargs="+", help="Input .xlsx files to filter")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o"))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--mode", choices=["exact", "strict"], default="exact")
    args = parser.parse_args()

    for f in args.files:
        p = Path(f)
        if not p.exists():
            raise FileNotFoundError(p)
        filter_excel(p, model=args.model, workers=args.workers, mode=args.mode)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

