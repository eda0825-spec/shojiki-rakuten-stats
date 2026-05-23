#!/usr/bin/env python3
"""
Amazon Seller Central からダウンロードしたカスタマーレビュー CSV を読んで、
楽天と同じ形式 (reviews-{product}.json) に変換するインジェスタ。

Amazon は現状 SP-API でレビュー本文取得 API を公開していないため、
出店者画面 (Seller Central → 広告 → ブランド分析 → カスタマーレビュー、または
パフォーマンス → カスタマーレビュー) から CSV を手動ダウンロードして
インポートする半自動運用とする。

期待する CSV 列 (典型例 — 列名は環境で微妙に違うので柔軟に対応):
  Date / 投稿日 / Review Date
  Rating / 評価
  Title / タイトル
  Body / 本文 / Review Body
  Reviewer / 名前
  ASIN / Product ID
  Verified Purchase

使い方:
  # SH-J001 用
  python3 ingest-amazon-csv.py --product sh-j001 --csv amazon-j001-2026-05.csv

  # SH-J002 用
  python3 ingest-amazon-csv.py --product sh-j002 --csv amazon-j002-2026-05.csv

  # 既存 reviews-sh-j001.json にマージ (重複は id でスキップ)
  # 既存に Amazon 由来のものがあればスキップ、新規分だけ追加。

JSON の reviews アイテムには source="amazon" を追加 (楽天は source="rakuten")。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PRODUCTS = {"sh-j001", "sh-j002"}


def pick(row: dict, *keys: str) -> str:
    """case-insensitive partial match — Amazon CSV 列名のゆれを吸収"""
    for k in keys:
        for actual, value in row.items():
            if actual and k.lower() in actual.lower().strip():
                if value:
                    return value.strip()
    return ""


def normalize_date(s: str) -> str | None:
    if not s:
        return None
    s = s.strip()
    # ISO 形式
    m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # MM/DD/YYYY (US 形式)
    m = re.match(r"(\d{1,2})[/](\d{1,2})[/](\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    # "January 5, 2026" 形式
    try:
        dt = datetime.strptime(s, "%B %d, %Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        pass
    return None


def review_id(asin: str, body: str, nickname: str, date: str | None) -> str:
    seed = "|".join([asin, nickname, date or "", body[:80]])
    return "amz-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:14]


def parse_csv(csv_path: Path, product: str) -> list[dict]:
    out: list[dict] = []
    with csv_path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            body = pick(row, "review body", "body", "本文", "review text")
            if not body:
                continue
            rating_s = pick(row, "rating", "評価", "stars")
            try:
                rating = int(float(re.findall(r"[\d.]+", rating_s)[0])) if rating_s else 0
            except (IndexError, ValueError):
                rating = 0
            date = normalize_date(pick(row, "review date", "date", "投稿日", "submitted"))
            asin = pick(row, "asin", "product id", "商品コード")
            nickname = pick(row, "reviewer", "name", "投稿者", "customer") or "Amazon Customer"
            title = pick(row, "title", "タイトル", "review title") or None
            out.append(
                {
                    "id": review_id(asin or product, body, nickname, date),
                    "rating": rating,
                    "postDate": date,
                    "title": title,
                    "body": body.replace("\r\n", "\n").strip(),
                    "nickname": nickname,
                    "age": None,
                    "gender": None,
                    "source": "amazon",
                    "asin": asin or None,
                }
            )
    return out


def merge_into(product: str, new_reviews: list[dict]) -> None:
    here = Path(__file__).resolve().parent
    path = here / f"reviews-{product}.json"

    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
    else:
        existing = {
            "updatedAt": None,
            "product": product,
            "itemNumber": None,
            "summary": {},
            "reviewsCount": 0,
            "newReviewsThisRun": 0,
            "reviews": [],
        }

    have_ids = {r["id"] for r in existing.get("reviews", [])}
    added = [r for r in new_reviews if r["id"] not in have_ids]

    merged = added + existing.get("reviews", [])
    merged.sort(key=lambda r: (r.get("postDate") or "0000-00-00"), reverse=True)

    existing["reviews"] = merged
    existing["reviewsCount"] = len(merged)
    existing["newReviewsThisRun"] = len(added)
    existing["updatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[{product}] merged Amazon CSV: +{len(added)} new (total {len(merged)})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", required=True, choices=sorted(PRODUCTS))
    ap.add_argument("--csv", required=True, help="path to Amazon Seller Central CSV")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"ERROR: csv not found: {csv_path}", file=sys.stderr)
        return 1

    new_reviews = parse_csv(csv_path, args.product)
    print(f"parsed {len(new_reviews)} reviews from {csv_path.name}")
    if not new_reviews:
        print("nothing to merge", file=sys.stderr)
        return 0
    merge_into(args.product, new_reviews)
    print("次に: python3 categorize-reviews.py を実行して Amazon 分も分類されます。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
