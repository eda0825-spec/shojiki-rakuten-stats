#!/usr/bin/env python3
"""
Fetch the latest Rakuten review average / count for SHOJIKI products
(SH-J001 and SH-J002) and write to rakuten-stats.json.

Required env vars:
  RAKUTEN_APP_ID      Application ID (UUID)
  RAKUTEN_ACCESS_KEY  Access Key (pk_...)

Optional:
  RAKUTEN_ITEM_CODE     SH-J001 itemCode. defaults to "shojiki-official:10000000"
  RAKUTEN_ITEM_CODE_2   SH-J002 itemCode. e.g. "shojiki-official:XXXXXXXX"
                        (if unset, SH-J002 is skipped)
  RAKUTEN_ORIGIN        defaults to "https://shojiki-store.com"

Output JSON shape (backward compatible):
  {
    "rating": <SH-J001 rating>,        # top-level kept for existing LP fetch
    "count":  <SH-J001 count>,
    "itemCode": <SH-J001 itemCode>,
    "products": {
      "sh-j001": { "rating":.., "count":.., "itemCode":".." },
      "sh-j002": { "rating":.., "count":.., "itemCode":".." }
    },
    "updatedAt": "..."
  }
"""
import os
import re
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

API_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"

# Public review pages carry the same review count/average a shopper sees.
# The Item Search API's reviewCount caches and lags by days, so we prefer
# the review page and only fall back to the API when scraping fails.
SHOP_ID = os.environ.get("RAKUTEN_SHOP_ID", "437323")
REVIEW_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _http_get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": REVIEW_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.rakuten.co.jp/",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _extract_state(raw):
    """Extract the first window.__XXX__ = {...} JSON object from the page."""
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


def fetch_summary_review_page(item_number):
    """Accurate review summary (rating/count) from the public review page."""
    url = f"https://review.rakuten.co.jp/item/1/{SHOP_ID}_{item_number}/1.1/"
    state = _extract_state(_http_get(url))
    ratings = (state.get("itemInfo") or {}).get("reviewRatings") or {}
    avg = ratings.get("average")
    cnt = ratings.get("totalCount")
    return {
        "rating": round(float(avg), 2) if avg is not None else None,
        "count": int(cnt) if cnt is not None else None,
    }


def fetch_one(app_id, access_key, item_code, origin):
    params = urllib.parse.urlencode({
        "applicationId": app_id,
        "accessKey": access_key,
        "itemCode": item_code,
        "format": "json",
    })
    req = urllib.request.Request(f"{API_URL}?{params}", headers={"Origin": origin})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())
    items = data.get("Items", [])
    if not items:
        raise RuntimeError(f"no items returned for itemCode={item_code}")
    item = items[0].get("Item", items[0])
    return {
        "rating": item.get("reviewAverage"),
        "count": item.get("reviewCount"),
        "itemCode": item.get("itemCode"),
    }


def main() -> int:
    app_id = os.environ.get("RAKUTEN_APP_ID")
    access_key = os.environ.get("RAKUTEN_ACCESS_KEY")
    if not app_id or not access_key:
        print("ERROR: RAKUTEN_APP_ID and RAKUTEN_ACCESS_KEY must be set", file=sys.stderr)
        return 1

    origin = os.environ.get("RAKUTEN_ORIGIN", "https://shojiki-store.com")

    # product key -> itemCode
    targets = {
        "sh-j001": os.environ.get("RAKUTEN_ITEM_CODE", "shojiki-official:10000000"),
    }
    code2 = os.environ.get("RAKUTEN_ITEM_CODE_2")
    if code2:
        targets["sh-j002"] = code2

    products = {}
    for key, code in targets.items():
        item_number = code.split(":")[-1]
        rec = None
        # 1) Prefer the public review page (matches shopper-visible count; no API lag)
        try:
            s = fetch_summary_review_page(item_number)
            if s.get("rating") is not None and s.get("count") is not None:
                rec = {"rating": s["rating"], "count": s["count"], "itemCode": code}
                print(f"OK {key} (review page): {rec}")
        except Exception as e:  # noqa: BLE001
            print(f"WARN review-page fetch failed for {key} ({item_number}): {e}", file=sys.stderr)
        # 2) Fall back to the Item Search API
        if rec is None:
            try:
                rec = fetch_one(app_id, access_key, code, origin)
                print(f"OK {key} (item API fallback): {rec}")
            except Exception as e:  # noqa: BLE001
                print(f"ERROR fetching {key} ({code}): {e}", file=sys.stderr)
                # keep previous value (merged below); do not abort the whole run
        if rec is not None:
            products[key] = rec

    out_path = Path(__file__).resolve().parent / "rakuten-stats.json"

    # merge with existing file so a transient failure for one product
    # does not erase its last-known-good value
    existing = {}
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            existing = {}

    merged_products = dict(existing.get("products", {}))
    # seed sh-j001 from legacy top-level if products map was absent
    if "sh-j001" not in merged_products and existing.get("rating") is not None:
        merged_products["sh-j001"] = {
            "rating": existing.get("rating"),
            "count": existing.get("count"),
            "itemCode": existing.get("itemCode"),
        }
    merged_products.update(products)

    if not merged_products:
        print("ERROR: no products fetched and no existing data", file=sys.stderr)
        return 2

    sh1 = merged_products.get("sh-j001", {})
    out = {
        "rating": sh1.get("rating"),
        "count": sh1.get("count"),
        "itemCode": sh1.get("itemCode"),
        "products": merged_products,
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
