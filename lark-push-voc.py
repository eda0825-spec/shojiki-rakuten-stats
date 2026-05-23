#!/usr/bin/env python3
"""
カテゴリ分類済みレビュー (categorized-*.json + reviews-*.json) を、
Lark Base の VOC テーブルへバッチ POST するスクリプト。

スキーマは docs/LARK_BASE_SCHEMA.md の Base 3 (`カスタマー VOC`) を参照。

実行前提:
1. Lark Developer Console (https://open.larksuite.com/app) でアプリ作成
   - App ID と App Secret を取得
   - tenant_access_token を発行できる権限を有効化
   - Bitable (多維表格) の Read/Write スコープを付与
2. Lark Base に該当アプリを「ベースを共有」→「アプリ共有」で追加
3. Base 3 (カスタマー VOC) を作成し、URL から appToken と tableId を取得

GitHub Secrets に追加 (準備でき次第):
  LARK_APP_ID
  LARK_APP_SECRET
  LARK_VOC_APP_TOKEN
  LARK_VOC_TABLE_ID

進捗:
  pushed-to-lark.json に同期済み id を保持し、再実行で重複 POST しない。
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LARK_BASE = os.environ.get("LARK_BASE_URL", "https://open.larksuite.com")
# 中国本土のテナント (飞书) の場合は https://open.feishu.cn に切り替え
# LARK_BASE_URL=https://open.feishu.cn python3 lark-push-voc.py

PRODUCTS = ["sh-j001", "sh-j002"]
STATE_PATH = Path(__file__).resolve().parent / "pushed-to-lark.json"


def get_tenant_token(app_id: str, app_secret: str) -> str:
    url = f"{LARK_BASE}/open-apis/auth/v3/tenant_access_token/internal"
    payload = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    if data.get("code") != 0:
        raise RuntimeError(f"tenant_access_token failed: {data}")
    return data["tenant_access_token"]


def batch_create(token: str, app_token: str, table_id: str, records: list[dict]) -> dict:
    url = f"{LARK_BASE}/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"
    payload = json.dumps({"records": [{"fields": r} for r in records]}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    if data.get("code") != 0:
        raise RuntimeError(f"batch_create failed: {data}")
    return data


def load_pushed() -> set[str]:
    if not STATE_PATH.exists():
        return set()
    try:
        return set(json.loads(STATE_PATH.read_text(encoding="utf-8")).get("ids", []))
    except Exception:
        return set()


def save_pushed(ids: set[str]) -> None:
    # 最新 5000 件だけ保持 (古いものは再 push してもどうせ重複)
    arr = sorted(ids)[-5000:]
    STATE_PATH.write_text(
        json.dumps({"updatedAt": datetime.now(timezone.utc).isoformat(), "ids": arr}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


def build_record(review: dict, cat: dict, product: str) -> dict:
    """Lark の field 名は Base 側の設定と一致させる必要がある。
    docs/LARK_BASE_SCHEMA.md の Base 3 列名に揃えてある。"""
    return {
        "ID": review["id"],
        "取得日": cat_iso_date(),
        "モール": "Amazon" if review.get("source") == "amazon" else "楽天",
        "商品": "SH-J001" if product == "sh-j001" else "SH-J002",
        "星": review.get("rating") or 0,
        "レビュー日": review.get("postDate") or None,
        "投稿者": review.get("nickname") or "—",
        "本文 (JP)": review.get("body") or "",
        # 中国語訳本文は要約のみ供給。フル本文の翻訳は categorize 側で対応未実装。
        "本文 (ZH)": "",
        "要約 (JP)": cat.get("summary_ja") or "",
        "要約 (ZH)": cat.get("summary_zh") or "",
        "分類": cat_jp_category(cat.get("category")),
        "深刻度": cat_jp_severity(cat.get("severity")),
        "トピック": cat.get("topics") or [],
        "対策案": cat.get("action_hint") or "",
        "工場転記済み": False,
        "URL": rakuten_url(review, product) if review.get("source") != "amazon" else None,
    }


def cat_iso_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def cat_jp_category(c: str | None) -> str:
    return {
        "defect": "不具合",
        "improvement": "改善要望",
        "praise": "称賛",
        "question": "質問",
        "other": "その他",
    }.get(c or "", "その他")


def cat_jp_severity(s: str | None) -> str:
    return {
        "high": "高",
        "medium": "中",
        "low": "低",
        "n/a": "該当なし",
    }.get(s or "", "該当なし")


def rakuten_url(r: dict, product: str) -> str:
    item = "10000000" if product == "sh-j001" else "10000004"
    return f"https://review.rakuten.co.jp/item/1/437323_{item}/"


def main() -> int:
    app_id = os.environ.get("LARK_APP_ID")
    app_secret = os.environ.get("LARK_APP_SECRET")
    app_token = os.environ.get("LARK_VOC_APP_TOKEN")
    table_id = os.environ.get("LARK_VOC_TABLE_ID")
    if not all([app_id, app_secret, app_token, table_id]):
        print("ERROR: LARK_APP_ID / LARK_APP_SECRET / LARK_VOC_APP_TOKEN / LARK_VOC_TABLE_ID を全て設定してください", file=sys.stderr)
        return 1

    token = get_tenant_token(app_id, app_secret)
    pushed = load_pushed()

    here = Path(__file__).resolve().parent
    total_pushed = 0
    for product in PRODUCTS:
        reviews_path = here / f"reviews-{product}.json"
        cat_path = here / f"categorized-{product}.json"
        if not reviews_path.exists() or not cat_path.exists():
            print(f"SKIP [{product}] missing source files", file=sys.stderr)
            continue
        reviews = json.loads(reviews_path.read_text(encoding="utf-8")).get("reviews", [])
        cats = {r["id"]: r for r in json.loads(cat_path.read_text(encoding="utf-8")).get("results", [])}

        todo = []
        for r in reviews:
            if r["id"] in pushed:
                continue
            c = cats.get(r["id"])
            if not c:
                continue  # まだ分類されていない
            todo.append((r, c))

        print(f"[{product}] {len(todo)} new records to push")
        for i in range(0, len(todo), 100):  # Lark batch_create max 1000, 100 で余裕
            batch = todo[i : i + 100]
            recs = [build_record(r, c, product) for r, c in batch]
            try:
                batch_create(token, app_token, table_id, recs)
                for r, _ in batch:
                    pushed.add(r["id"])
                total_pushed += len(batch)
                print(f"  pushed {len(batch)} ({i+len(batch)}/{len(todo)})")
                time.sleep(0.5)
            except Exception as e:  # noqa: BLE001
                print(f"  ERROR batch {i//100}: {e}", file=sys.stderr)
                save_pushed(pushed)
                return 2

    save_pushed(pushed)
    print(f"DONE: pushed {total_pushed} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
