#!/usr/bin/env python3
"""
3 つの販売チャネル (Shopify / 楽天 RMS / Amazon SP-API) から日次で
販売台数を取得し、商品別 (sh-j001 / sh-j002) に集計して JSON 出力。

設計方針:
- 各プラットフォームは credentials が無ければ skip (workflow は green のまま)
- 既存の sales-summary.json と merge し、過去データは保持
- 直近 30 日のオーダーを取得して再集計 (返品キャンセル反映)
- 31 日以前のデータは履歴 (byMonth) に残るだけで、再 fetch しない

出力: sales-summary.json
{
  "updatedAt": "2026-05-23T01:00:00Z",
  "byProduct": {
    "sh-j001": {
      "today":     { "total": 5, "rakuten": 3, "amazon": 2, "shopify": 0 },
      "thisMonth": { ... },
      "lastMonth": { ... },
      "allTime":   { ... },
      "byMonth": [
        { "month": "2026-05", "rakuten": 87, "amazon": 12, "shopify": 0, "total": 99 }
      ],
      "platformStatus": {
        "shopify": { "configured": true, "error": null, "lastSyncOrders": 12 },
        ...
      }
    },
    "sh-j002": { ... }
  }
}

ENV:
  SHOPIFY_SHOP_DOMAIN          例: shojiki-store.myshopify.com
  SHOPIFY_ADMIN_TOKEN          private app admin API token (read_orders)
  SHOPIFY_J001_SKUS            J001 と判定する SKU/handle (カンマ区切り)
  SHOPIFY_J002_SKUS            同上

  RAKUTEN_RMS_LICENSE_KEY      RMS WEB API SERVICE で発行
  RAKUTEN_RMS_SERVICE_SECRET   同上
  RAKUTEN_J001_ITEM_CODE       例: shojiki-official:10000000 (既存設定流用)
  RAKUTEN_J002_ITEM_CODE       例: shojiki-official:10000004

  AMAZON_J001_ASIN             例: B0XXXXXXX (Amazon Seller Central 商品詳細)
  AMAZON_J002_ASIN             同上
  AMAZON_SP_REFRESH_TOKEN      SP-API LWA refresh token
  AMAZON_SP_CLIENT_ID          LWA client_id
  AMAZON_SP_CLIENT_SECRET      LWA client_secret
  AMAZON_MARKETPLACE_ID        日本: A1VC38T7YXB528
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
HERE = Path(__file__).resolve().parent
OUT_PATH = HERE / "sales-summary.json"

# ===== helpers =====

def jst_today_str() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")

def jst_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def lookback_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

def http_json(url: str, headers: dict, *, method: str = "GET", body: bytes | None = None, timeout: int = 30) -> dict | list:
    req = urllib.request.Request(url, method=method, headers=headers, data=body)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        # Some APIs return empty body
        if not raw:
            return {}
        return json.loads(raw)


# ===== Shopify =====
# 直近 30 日の orders を全て取得 → SKU/handle で商品判定 → 日別カウント

def fetch_shopify(days: int = 30) -> dict:
    domain = os.environ.get("SHOPIFY_SHOP_DOMAIN")
    token = os.environ.get("SHOPIFY_ADMIN_TOKEN")
    if not domain or not token:
        return {"configured": False, "error": "SHOPIFY_SHOP_DOMAIN / SHOPIFY_ADMIN_TOKEN not set", "orders": []}

    j001 = set(s.strip().lower() for s in (os.environ.get("SHOPIFY_J001_SKUS", "sh-j001").split(",")) if s.strip())
    j002 = set(s.strip().lower() for s in (os.environ.get("SHOPIFY_J002_SKUS", "sh-j002").split(",")) if s.strip())

    created_min = lookback_iso(days)
    url = (
        f"https://{domain}/admin/api/2024-10/orders.json"
        f"?status=any&financial_status=paid&limit=250&created_at_min={created_min}"
    )
    headers = {"X-Shopify-Access-Token": token, "Accept": "application/json"}

    orders: list[dict] = []
    try:
        # Shopify pagination via Link header
        next_url: str | None = url
        page = 0
        while next_url and page < 20:  # safety cap (250*20=5000 orders ≒ 30日分余裕)
            req = urllib.request.Request(next_url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
                link = r.headers.get("Link", "")
            for o in data.get("orders", []):
                # extract per-line-item quantities matched to our SKUs
                for li in o.get("line_items", []):
                    sku = (li.get("sku") or "").lower()
                    handle = (li.get("variant_title") or "").lower()  # crude fallback
                    qty = li.get("quantity", 0)
                    product = None
                    if sku in j001 or any(s in sku for s in j001):
                        product = "sh-j001"
                    elif sku in j002 or any(s in sku for s in j002):
                        product = "sh-j002"
                    if product:
                        orders.append({
                            "product": product,
                            "qty": qty,
                            "created_at": o.get("created_at"),
                            "order_id": o.get("id"),
                            "sku": sku,
                        })
            # parse next link
            next_url = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    # <https://...>; rel="next"
                    next_url = part.split(";")[0].strip().strip("<>")
                    break
            page += 1
        return {"configured": True, "error": None, "orders": orders}
    except urllib.error.HTTPError as e:
        return {"configured": True, "error": f"HTTP {e.code}: {e.reason}", "orders": []}
    except Exception as e:  # noqa: BLE001
        return {"configured": True, "error": str(e), "orders": []}


# ===== 楽天 RMS =====
# searchOrder で 直近 30 日の注文番号を取得 → getOrder で詳細
# RMS API docs: https://webservice.rms.rakuten.co.jp/merchant-portal/view?contents=/api/order/

def fetch_rakuten_rms(days: int = 30) -> dict:
    license_key = os.environ.get("RAKUTEN_RMS_LICENSE_KEY")
    service_secret = os.environ.get("RAKUTEN_RMS_SERVICE_SECRET")
    if not license_key or not service_secret:
        return {"configured": False, "error": "RAKUTEN_RMS_LICENSE_KEY / SERVICE_SECRET not set", "orders": []}

    j001_code = (os.environ.get("RAKUTEN_J001_ITEM_CODE", "shojiki-official:10000000") or "").lower()
    j002_code = (os.environ.get("RAKUTEN_J002_ITEM_CODE", "shojiki-official:10000004") or "").lower()

    import base64
    auth = base64.b64encode(f"{service_secret}:{license_key}".encode()).decode()
    headers = {
        "Authorization": f"ESA {auth}",
        "Content-Type": "application/json; charset=utf-8",
    }
    date_to = datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+0900")
    date_from = (datetime.now(JST) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S+0900")

    # 1) searchOrder
    search_url = "https://api.rms.rakuten.co.jp/es/2.0/order/searchOrder/"
    search_body = json.dumps({
        "dateType": 1,  # 注文日
        "startDatetime": date_from,
        "endDatetime": date_to,
        "PaginationRequestModel": {"requestRecordsAmount": 1000, "requestPage": 1},
    }).encode()

    orders: list[dict] = []
    try:
        search_resp = http_json(search_url, headers, method="POST", body=search_body)
        order_numbers = search_resp.get("orderNumberList") or []
        if not order_numbers:
            return {"configured": True, "error": None, "orders": []}

        # 2) getOrder (max 100 numbers per call)
        get_url = "https://api.rms.rakuten.co.jp/es/2.0/order/getOrder/"
        for i in range(0, len(order_numbers), 100):
            chunk = order_numbers[i:i + 100]
            body = json.dumps({"orderNumberList": chunk, "version": 7}).encode()
            data = http_json(get_url, headers, method="POST", body=body)
            for order in data.get("OrderModelList") or []:
                created = order.get("orderDatetime")
                for pkg in order.get("PackageModelList") or []:
                    for item in pkg.get("ItemModelList") or []:
                        code = (item.get("itemNumber") or "").lower()
                        qty = item.get("units", 0) or 0
                        # itemNumber は "10000000" 形式、itemCode は "shojiki-official:10000000"
                        full = f"shojiki-official:{code}".lower()
                        product = None
                        if full == j001_code or code in j001_code:
                            product = "sh-j001"
                        elif full == j002_code or code in j002_code:
                            product = "sh-j002"
                        if product:
                            orders.append({
                                "product": product, "qty": qty,
                                "created_at": created, "order_id": order.get("orderNumber"),
                                "item_number": code,
                            })
        return {"configured": True, "error": None, "orders": orders}
    except urllib.error.HTTPError as e:
        return {"configured": True, "error": f"HTTP {e.code}: {e.reason}", "orders": []}
    except Exception as e:  # noqa: BLE001
        return {"configured": True, "error": str(e), "orders": []}


# ===== Amazon SP-API =====
# OAuth (LWA refresh token) → access_token → Orders API
# 概念実装。動作未テスト。本番投入前に LWA + Marketplace 設定が必要。

def fetch_amazon(days: int = 30) -> dict:
    refresh = os.environ.get("AMAZON_SP_REFRESH_TOKEN")
    cid = os.environ.get("AMAZON_SP_CLIENT_ID")
    secret = os.environ.get("AMAZON_SP_CLIENT_SECRET")
    if not all([refresh, cid, secret]):
        return {"configured": False, "error": "AMAZON_SP_REFRESH_TOKEN / CLIENT_ID / CLIENT_SECRET not set", "orders": []}

    marketplace = os.environ.get("AMAZON_MARKETPLACE_ID", "A1VC38T7YXB528")  # JP
    j001_asin = (os.environ.get("AMAZON_J001_ASIN") or "").upper()
    j002_asin = (os.environ.get("AMAZON_J002_ASIN") or "").upper()

    try:
        # LWA token exchange
        token_body = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": cid,
            "client_secret": secret,
        }).encode()
        token_resp = http_json(
            "https://api.amazon.com/auth/o2/token",
            {"Content-Type": "application/x-www-form-urlencoded"},
            method="POST", body=token_body,
        )
        access = token_resp.get("access_token")
        if not access:
            return {"configured": True, "error": "LWA token exchange failed", "orders": []}

        sp_host = "https://sellingpartnerapi-fe.amazon.com"  # FE = Far East (Japan)
        created_after = lookback_iso(days)
        params = urllib.parse.urlencode({
            "CreatedAfter": created_after,
            "MarketplaceIds": marketplace,
            "OrderStatuses": "Shipped,Unshipped,PartiallyShipped",
        })
        orders_url = f"{sp_host}/orders/v0/orders?{params}"
        headers = {"x-amz-access-token": access, "Accept": "application/json"}

        # NOTE: SP-API also requires AWS SigV4 in older flows but Orders v0
        # endpoints now accept just x-amz-access-token (Aug 2023+).

        orders: list[dict] = []
        next_token: str | None = None
        page = 0
        while page < 10:
            u = orders_url + (f"&NextToken={urllib.parse.quote(next_token)}" if next_token else "")
            data = http_json(u, headers)
            payload = data.get("payload", {})
            for o in payload.get("Orders", []):
                order_id = o.get("AmazonOrderId")
                created = o.get("PurchaseDate")
                # Get items
                items_data = http_json(f"{sp_host}/orders/v0/orders/{order_id}/orderItems", headers)
                for it in items_data.get("payload", {}).get("OrderItems", []):
                    asin = (it.get("ASIN") or "").upper()
                    qty = int(it.get("QuantityOrdered", 0))
                    product = None
                    if asin and asin == j001_asin:
                        product = "sh-j001"
                    elif asin and asin == j002_asin:
                        product = "sh-j002"
                    if product:
                        orders.append({
                            "product": product, "qty": qty,
                            "created_at": created, "order_id": order_id, "asin": asin,
                        })
            next_token = payload.get("NextToken")
            page += 1
            if not next_token:
                break
        return {"configured": True, "error": None, "orders": orders}
    except urllib.error.HTTPError as e:
        return {"configured": True, "error": f"HTTP {e.code}: {e.reason}", "orders": []}
    except Exception as e:  # noqa: BLE001
        return {"configured": True, "error": str(e), "orders": []}


# ===== aggregation =====

def to_jst_date(iso: str) -> str:
    if not iso:
        return ""
    # accept "2026-05-23T12:34:56Z" or with tz offset
    try:
        s = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(JST).strftime("%Y-%m-%d")
    except Exception:
        return iso[:10] if len(iso) >= 10 else ""


def aggregate(platform_to_orders: dict[str, list[dict]]) -> dict:
    """
    Returns shape:
    byProduct[sh-j00X] = {
      today, thisMonth, lastMonth, allTime: {total, rakuten, amazon, shopify},
      byMonth: [{month, rakuten, amazon, shopify, total}]
    }
    """
    today_str = jst_today_str()
    month_str = today_str[:7]
    last_month = (datetime.strptime(month_str + "-01", "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m")

    by_product: dict[str, dict] = {}
    for p in ["sh-j001", "sh-j002"]:
        by_product[p] = {
            "today": {"total": 0, "rakuten": 0, "amazon": 0, "shopify": 0},
            "thisMonth": {"total": 0, "rakuten": 0, "amazon": 0, "shopify": 0},
            "lastMonth": {"total": 0, "rakuten": 0, "amazon": 0, "shopify": 0},
            "allTime": {"total": 0, "rakuten": 0, "amazon": 0, "shopify": 0},
            "byMonth": [],
        }

    # accumulate per-day, per-product, per-platform
    daily: dict[tuple, int] = defaultdict(int)
    for platform, orders in platform_to_orders.items():
        for o in orders:
            p = o["product"]
            d = to_jst_date(o.get("created_at"))
            if not d:
                continue
            daily[(p, d, platform)] += o.get("qty", 0)

    # fill into by_product structures
    for (p, d, platform), qty in daily.items():
        m = d[:7]
        # byMonth aggregation
        bm = next((b for b in by_product[p]["byMonth"] if b["month"] == m), None)
        if bm is None:
            bm = {"month": m, "rakuten": 0, "amazon": 0, "shopify": 0, "total": 0}
            by_product[p]["byMonth"].append(bm)
        bm[platform] += qty
        bm["total"] += qty

        if d == today_str:
            by_product[p]["today"][platform] += qty
            by_product[p]["today"]["total"] += qty
        if m == month_str:
            by_product[p]["thisMonth"][platform] += qty
            by_product[p]["thisMonth"]["total"] += qty
        if m == last_month:
            by_product[p]["lastMonth"][platform] += qty
            by_product[p]["lastMonth"]["total"] += qty

    # sort byMonth desc
    for p in by_product:
        by_product[p]["byMonth"].sort(key=lambda b: b["month"], reverse=True)

    return by_product


def merge_with_existing(new_by_product: dict, platform_results: dict[str, dict]) -> dict:
    """Merge new (last-30d) data with existing JSON, preserving old months."""
    existing = {}
    if OUT_PATH.exists():
        try:
            existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    cutoff = (datetime.now(JST) - timedelta(days=30)).strftime("%Y-%m")

    for p, data in new_by_product.items():
        old = (existing.get("byProduct") or {}).get(p, {})
        old_by_month = old.get("byMonth") or []
        # Keep old months OLDER than the cutoff (we re-fetched the recent ones)
        kept_old = [b for b in old_by_month if b["month"] < cutoff]
        merged_by_month = data["byMonth"] + kept_old
        # dedupe by month, prefer new
        seen = set()
        out_by_month = []
        for b in merged_by_month:
            if b["month"] in seen:
                continue
            seen.add(b["month"])
            out_by_month.append(b)
        out_by_month.sort(key=lambda b: b["month"], reverse=True)
        data["byMonth"] = out_by_month

        # allTime aggregation (sum across all months)
        at = {"total": 0, "rakuten": 0, "amazon": 0, "shopify": 0}
        for b in out_by_month:
            for k in ("rakuten", "amazon", "shopify", "total"):
                at[k] += b.get(k, 0)
        data["allTime"] = at

        # Platform status snapshot
        data["platformStatus"] = {
            plat: {
                "configured": res.get("configured", False),
                "error": res.get("error"),
                "lastSyncOrders": sum(1 for o in res.get("orders", []) if o["product"] == p),
            }
            for plat, res in platform_results.items()
        }

    return {
        "updatedAt": jst_now_iso(),
        "byProduct": new_by_product,
    }


def main() -> int:
    days = int(os.environ.get("SALES_LOOKBACK_DAYS", "30"))

    print("=== fetching Shopify ===", file=sys.stderr)
    shop = fetch_shopify(days)
    print(f"  configured={shop['configured']} error={shop['error']} orders={len(shop['orders'])}", file=sys.stderr)

    print("=== fetching Rakuten RMS ===", file=sys.stderr)
    rkt = fetch_rakuten_rms(days)
    print(f"  configured={rkt['configured']} error={rkt['error']} orders={len(rkt['orders'])}", file=sys.stderr)

    print("=== fetching Amazon SP-API ===", file=sys.stderr)
    amz = fetch_amazon(days)
    print(f"  configured={amz['configured']} error={amz['error']} orders={len(amz['orders'])}", file=sys.stderr)

    platform_results = {"shopify": shop, "rakuten": rkt, "amazon": amz}
    platform_orders = {k: v["orders"] for k, v in platform_results.items()}

    by_product = aggregate(platform_orders)
    payload = merge_with_existing(by_product, platform_results)

    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT_PATH.name}")
    for p, d in by_product.items():
        print(f"  {p}: today={d['today']['total']} thisMonth={d['thisMonth']['total']} allTime={d['allTime']['total']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
