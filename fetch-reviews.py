#!/usr/bin/env python3
"""
Fetch all Rakuten reviews for SHOJIKI products (SH-J001 / SH-J002) by walking
the public review pages on review.rakuten.co.jp.

Uses the embedded `window.__INITIAL_STATE__` JSON (same approach as
rakuten-gold/build-reviews.py) which is far more reliable than HTML regex.

Output (one file per product, next to this script):
  reviews-sh-j001.json
  reviews-sh-j002.json

Each file:
  {
    "updatedAt": "...",
    "product": "sh-j001",
    "itemNumber": "10000000",
    "summary": { "rating": 4.55, "count": 896 },
    "reviews": [
      {
        "id": "..."             # stable: itemNumber + nickname + postDate + first 40 chars of body
        "rating": 5,
        "postDate": "2026-05-20",
        "title": "...",
        "body": "...",
        "nickname": "...",
        "age": "30代" | null,
        "gender": "男性" | "女性" | null
      },
      ...
    ]
  }

Incremental: existing file's reviews are preserved; only new ones are appended.
Polite: REVIEW_SLEEP_SEC delay between page fetches.

Env:
  REVIEW_MAX_PAGES   safety cap per product, default 200
  REVIEW_SLEEP_SEC   delay between page fetches, default 1.5
  REVIEW_FULL_RESCAN if "1", ignores existing file and re-fetches everything
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SHOP_ID = "437323"
PRODUCTS = {
    "sh-j001": "10000000",
    "sh-j002": "10000004",
}

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Referer": "https://www.rakuten.co.jp/",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_state(raw: str) -> dict:
    """Extract the first window.__XXX__ = {...} JSON object."""
    m = re.search(r"window\.__\w+__\s*=\s*", raw)
    if not m:
        raise RuntimeError("__INITIAL_STATE__ not found")
    i = raw.find("{", m.end())
    depth = 0
    in_str = False
    esc = False
    end = None
    for k in range(i, len(raw)):
        c = raw[k]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = k + 1
                    break
    if end is None:
        raise RuntimeError("__INITIAL_STATE__ JSON not closed")
    return json.loads(raw[i:end])


def normalize_date(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip()
    # "2026/05/20" -> "2026-05-20"
    m = re.match(r"(\d{4})[/\-年](\d{1,2})[/\-月](\d{1,2})", s)
    if not m:
        return None
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def review_id(item_number: str, r: dict) -> str:
    """Stable ID across runs without relying on Rakuten's internal review keys."""
    body = (r.get("body") or "").strip().replace("\n", " ")[:80]
    seed = "|".join(
        [
            item_number,
            (r.get("nickname") or "").strip(),
            normalize_date(r.get("postDate")) or "",
            body,
        ]
    )
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def parse_state_reviews(state: dict, item_number: str) -> list[dict]:
    """Pull the ITEM (not shop) reviews from an INITIAL_STATE blob."""
    reviews_blk = state.get("reviews", {}) or {}
    rdata = reviews_blk.get("data") or {}
    keys = (reviews_blk.get("itemReviews") or {}).get("keys") or []
    if keys and rdata:
        raw_list = [rdata[k] for k in keys if k in rdata]
    elif rdata:
        raw_list = list(rdata.values())
    else:
        raw_list = (state.get("seo") or {}).get("itemReviewList") or []

    out: list[dict] = []
    for r in raw_list:
        body = (r.get("body") or "").strip()
        if not body:
            continue
        post_date = normalize_date(r.get("postDate"))
        nickname = (r.get("nickname") or "").strip() or "購入者"
        # rakuten sometimes pollutes emoji w/ � or "?"
        body_clean = body.replace("�", "")
        rec = {
            "id": review_id(item_number, {**r, "body": body, "nickname": nickname}),
            "rating": int(r.get("rating") or 0),
            "postDate": post_date,
            "title": (r.get("title") or "").strip() or None,
            "body": body_clean,
            "nickname": re.sub(r"さん$", "", nickname).strip() or "購入者",
            "age": (r.get("age") or "").strip() or None,
            "gender": (r.get("gender") or "").strip() or None,
        }
        out.append(rec)
    return out


def parse_state_summary(state: dict) -> dict:
    ratings = (state.get("itemInfo") or {}).get("reviewRatings") or {}
    avg = ratings.get("average")
    cnt = ratings.get("totalCount")
    return {
        "rating": round(float(avg), 2) if avg is not None else None,
        "count": int(cnt) if cnt is not None else None,
    }


def load_existing(path: Path) -> tuple[list[dict], set[str]]:
    if not path.exists():
        return [], set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return [], set()
    reviews = data.get("reviews") or []
    return reviews, {r.get("id") for r in reviews if r.get("id")}


def fetch_product(product: str, item_number: str, max_pages: int, sleep_sec: float, full_rescan: bool) -> dict:
    here = Path(__file__).resolve().parent
    out_path = here / f"reviews-{product}.json"
    existing, existing_ids = ([], set()) if full_rescan else load_existing(out_path)

    new_reviews: list[dict] = []
    summary: dict = {"rating": None, "count": None}
    stop_after_this_page = False
    consecutive_known_pages = 0  # incremental cutoff

    for page in range(1, max_pages + 1):
        url = f"https://review.rakuten.co.jp/item/1/{SHOP_ID}_{item_number}/{page}.1/"
        try:
            html = fetch(url)
            state = extract_state(html)
        except Exception as e:  # noqa: BLE001
            print(f"WARN [{product}] page {page} fetch/parse failed: {e}", file=sys.stderr)
            break

        if page == 1:
            summary = parse_state_summary(state)

        page_reviews = parse_state_reviews(state, item_number)
        if not page_reviews:
            print(f"INFO [{product}] page {page} empty, stopping", file=sys.stderr)
            break

        page_new = [r for r in page_reviews if r["id"] not in existing_ids]
        new_reviews.extend(page_new)
        existing_ids.update(r["id"] for r in page_new)

        print(
            f"[{product}] page {page}: {len(page_reviews)} found, {len(page_new)} new "
            f"(running total new={len(new_reviews)})",
            file=sys.stderr,
        )

        # Incremental stop: if NOT a full rescan and this page had zero new reviews,
        # accept after one full page of known reviews (Rakuten orders newest first).
        if not full_rescan and len(page_new) == 0:
            consecutive_known_pages += 1
            if consecutive_known_pages >= 1:
                print(
                    f"INFO [{product}] page {page} had no new reviews, stopping incremental scan",
                    file=sys.stderr,
                )
                break

        if page < max_pages:
            time.sleep(sleep_sec)

    # Merge: new reviews go first (they're newest), then existing.
    merged = new_reviews + existing
    # Dedupe by id, preserve order
    seen: set[str] = set()
    deduped: list[dict] = []
    for r in merged:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        deduped.append(r)
    # Sort newest-first by postDate (None last)
    deduped.sort(key=lambda r: (r.get("postDate") or "0000-00-00"), reverse=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "updatedAt": now,
        "product": product,
        "itemNumber": item_number,
        "summary": summary,
        "reviewsCount": len(deduped),
        "newReviewsThisRun": len(new_reviews),
        "reviews": deduped,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[{product}] wrote {out_path.name}: total={len(deduped)} (+{len(new_reviews)} new) "
        f"avg={summary.get('rating')} count={summary.get('count')}"
    )
    return payload


def main() -> int:
    max_pages = int(os.environ.get("REVIEW_MAX_PAGES", "200"))
    sleep_sec = float(os.environ.get("REVIEW_SLEEP_SEC", "1.5"))
    full_rescan = os.environ.get("REVIEW_FULL_RESCAN") == "1"

    only = os.environ.get("REVIEW_ONLY_PRODUCT")  # e.g. "sh-j002"
    targets = {only: PRODUCTS[only]} if only and only in PRODUCTS else PRODUCTS

    rc = 0
    for product, item_number in targets.items():
        try:
            fetch_product(product, item_number, max_pages, sleep_sec, full_rescan)
        except Exception as e:  # noqa: BLE001
            print(f"ERROR [{product}]: {e}", file=sys.stderr)
            rc = max(rc, 1)
    return rc


if __name__ == "__main__":
    sys.exit(main())
