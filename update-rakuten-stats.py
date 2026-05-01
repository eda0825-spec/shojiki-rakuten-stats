#!/usr/bin/env python3
"""
Fetch the latest Rakuten review average / count for SH-J001
and write to rakuten-stats.json.

Required env vars:
  RAKUTEN_APP_ID      Application ID (UUID)
  RAKUTEN_ACCESS_KEY  Access Key (pk_...)

Optional:
  RAKUTEN_ITEM_CODE   defaults to "shojiki-official:10000000"
  RAKUTEN_ORIGIN      defaults to "https://shojiki-store.com"
"""
import os
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

API_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"


def main() -> int:
    app_id = os.environ.get("RAKUTEN_APP_ID")
    access_key = os.environ.get("RAKUTEN_ACCESS_KEY")
    if not app_id or not access_key:
        print("ERROR: RAKUTEN_APP_ID and RAKUTEN_ACCESS_KEY must be set", file=sys.stderr)
        return 1

    item_code = os.environ.get("RAKUTEN_ITEM_CODE", "shojiki-official:10000000")
    origin = os.environ.get("RAKUTEN_ORIGIN", "https://shojiki-store.com")

    params = urllib.parse.urlencode({
        "applicationId": app_id,
        "accessKey": access_key,
        "itemCode": item_code,
        "format": "json",
    })
    url = f"{API_URL}?{params}"
    req = urllib.request.Request(url, headers={"Origin": origin})

    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())

    items = data.get("Items", [])
    if not items:
        print(f"ERROR: no items returned for itemCode={item_code}", file=sys.stderr)
        print(json.dumps(data, ensure_ascii=False)[:500], file=sys.stderr)
        return 2

    item = items[0].get("Item", items[0])
    out = {
        "rating": item.get("reviewAverage"),
        "count": item.get("reviewCount"),
        "itemCode": item.get("itemCode"),
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    out_path = Path(__file__).resolve().parent / "rakuten-stats.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {out_path}: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
