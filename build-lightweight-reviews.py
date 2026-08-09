#!/usr/bin/env python3
"""
Build the lightweight per-product review JSON that the Shopify LP fetches.

Reads the full pipeline output (reviews-sh-j00*.json, written by
fetch-reviews.py) and distills it into the small files the storefront
loads on every product-page view:

  rakuten-reviews-sh-j001.json
  rakuten-reviews-sh-j002.json

Schema (must stay EXACTLY as below — the live theme section
sections/shj002-lp-rest.liquid parses these keys; changing them would
require a production theme push):

  {
    "updatedAt": "2026-08-09T11:33:47Z",
    "product": "sh-j002",
    "summary": { "rating": 4.61, "count": 558 },   # Rakuten page totals
    "breakdown": { "5": n, "4": n, "3": n, "2": n, "1": n },
    "totalRated": n,                               # == sum(breakdown)
    "reviews": [                                   # newest 6 with a body
      { "rating": 5, "title": "", "body": "...",
        "author": "... さん", "date": "2026-08-07" }
    ]
  }

Deterministic transform: no network, no secrets. Skips (keeps the old
file) instead of writing implausible data — the numbers are shown to
customers, so a bad scrape must never overwrite a good file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRODUCTS = ("sh-j001", "sh-j002")
REVIEW_LIMIT = 6


def build(product: str) -> bool:
    src_path = HERE / f"reviews-{product}.json"
    out_path = HERE / f"rakuten-reviews-{product}.json"
    if not src_path.exists():
        print(f"[{product}] SKIP: {src_path.name} not found")
        return False

    src = json.loads(src_path.read_text(encoding="utf-8"))
    active = [r for r in src.get("reviews", []) if "removed_at" not in r]
    summary = src.get("summary") or {}

    # Never overwrite a good file with an empty/implausible scrape.
    if not active:
        print(f"[{product}] SKIP: no active reviews in {src_path.name}")
        return False
    if not isinstance(summary.get("rating"), (int, float)) or not isinstance(
        summary.get("count"), int
    ):
        print(f"[{product}] SKIP: summary missing/invalid in {src_path.name}")
        return False

    breakdown = {str(star): 0 for star in (5, 4, 3, 2, 1)}
    for r in active:
        key = str(int(r["rating"]))
        if key in breakdown:
            breakdown[key] += 1

    # Source is already newest-first, but don't rely on it (stable sort).
    newest = sorted(active, key=lambda r: r.get("postDate") or "", reverse=True)
    excerpts = [
        {
            "rating": int(r["rating"]),
            "title": (r.get("title") or "").strip(),
            "body": (r.get("body") or "").strip(),
            "author": ((r.get("nickname") or "購入者").strip() or "購入者") + " さん",
            "date": r.get("postDate") or "",
        }
        for r in newest
        if (r.get("body") or "").strip()
    ][:REVIEW_LIMIT]

    out = {
        "updatedAt": src.get("updatedAt"),
        "product": product,
        "summary": {"rating": summary["rating"], "count": summary["count"]},
        "breakdown": breakdown,
        "totalRated": sum(breakdown.values()),
        "reviews": excerpts,
    }
    out_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"[{product}] wrote {out_path.name}: "
        f"totalRated={out['totalRated']} summary={out['summary']} "
        f"excerpts={len(excerpts)}"
    )
    return True


def main() -> int:
    wrote = [p for p in PRODUCTS if build(p)]
    if not wrote:
        print("ERROR: no lightweight review JSON could be built", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
