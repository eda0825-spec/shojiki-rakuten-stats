#!/usr/bin/env python3
"""
カテゴリ済みレビュー (categorized-*.json) と元レビュー (reviews-*.json) から、
品質改善担当が一目で理解できる要約を Claude API で生成。

出力: summary-{product}.json
  {
    "updatedAt": "...",
    "product": "sh-j002",
    "stats": { "total_reviews": N, "negative": N, "defect_count": N, "improvement_count": N },
    "summary_ja": {
      "headline": "...",
      "key_findings": [ { "topic": "ダストカップ", "count": 20, "finding": "..." }, ... ],
      "actions": [ "工場が今すべき行動 1", ... ],
      "narrative": "全体の状況を2-3文で"
    },
    "summary_zh": { 同上 中国語 }
  }

ENV:
  ANTHROPIC_API_KEY      required
  ANTHROPIC_MODEL        default claude-sonnet-4-6
  SUMMARY_PRODUCTS       comma-separated, default "sh-j001,sh-j002"
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-6"

# Same cluster mapping as the dashboard
CLUSTERS = [
    ("charging", "充電・バッテリー", ["バッテリー","充電","充電端子","充電スタンド","充電台","電気系統","電池"]),
    ("weight",   "重量・サイズ",     ["重量","軽量","コンパクト","本体形状"]),
    ("suction",  "吸引力",          ["吸引力","吸力","基本機能"]),
    ("noise",    "音・静音性",      ["騒音","静音性","動作音","音"]),
    ("dustcup",  "ダストカップ",   ["ダストカップ","集尘杯","ゴミ捨て"]),
    ("roller",   "ローラー・ヘッド", ["ローラー","ヘッド","滚刷","吸头","ノズル","髪の毛","頭髪","毛絡まり"]),
    ("filter",   "フィルター",       ["フィルター","过滤器","メンテナンス","お手入れ"]),
    ("operation","操作・ボタン",   ["操作性","操作ボタン","スイッチ","ハンディモード","ボタン"]),
    ("stand",    "スタンド・自立",  ["自立機能","自走機能","スタンド","転倒耐性","壁掛け"]),
    ("design",   "デザイン",        ["デザイン","外装","外壳","カラー","色"]),
    ("safety",   "安全性",         ["安全性","怪我","発火","感電"]),
    ("carpet",   "床・カーペット",  ["カーペット対応","カーペット","絨毯対応","床"]),
]
TOPIC_TO_CLUSTER = {t: k for k, _, ts in CLUSTERS for t in ts}
CLUSTER_NAME = {k: n for k, n, _ in CLUSTERS}

PRODUCT_LABEL = {
    "sh-j001": "SH-J001 (吸引力重視・標準モデル)",
    "sh-j002": "SH-J002 (軽量・操作性重視モデル)",
}


def primary_cluster(topics: list[str]) -> str | None:
    for tp in topics:
        ck = TOPIC_TO_CLUSTER.get(tp)
        if ck:
            return ck
    return None


def build_input(product: str) -> dict | None:
    here = Path(__file__).resolve().parent
    revs_p = here / f"reviews-{product}.json"
    cats_p = here / f"categorized-{product}.json"
    if not revs_p.exists() or not cats_p.exists():
        return None
    revs = {r["id"]: r for r in json.loads(revs_p.read_text(encoding="utf-8")).get("reviews", [])}
    cats = json.loads(cats_p.read_text(encoding="utf-8")).get("results", [])

    # Aggregate per cluster (primary topic only)
    bucket = defaultdict(lambda: {"defect": 0, "improvement": 0, "samples": []})
    for c in cats:
        cat = c.get("category")
        if cat not in ("defect", "improvement"):
            continue
        pc = primary_cluster(c.get("topics") or [])
        if not pc:
            continue
        b = bucket[pc]
        b[cat] += 1
        if len(b["samples"]) < 4:
            r = revs.get(c["id"]) or {}
            b["samples"].append({
                "rating": r.get("rating"),
                "summary_ja": c.get("summary_ja"),
                "severity": c.get("severity"),
                "category": cat,
            })

    ranked = sorted(
        [{"key": k, "name": CLUSTER_NAME[k], **v, "total": v["defect"] + v["improvement"]}
         for k, v in bucket.items()],
        key=lambda x: -x["total"]
    )

    return {
        "product": product,
        "product_label": PRODUCT_LABEL.get(product, product),
        "total_reviews": len(revs),
        "total_categorized": len(cats),
        "defect_count": sum(1 for c in cats if c.get("category") == "defect"),
        "improvement_count": sum(1 for c in cats if c.get("category") == "improvement"),
        "praise_count": sum(1 for c in cats if c.get("category") == "praise"),
        "clusters": ranked,
    }


SYSTEM_PROMPT = """あなたは日本の家電ブランド SHOJIKI の品質改善担当アシスタントです。
楽天市場のお客様レビュー分析結果を、品質会議で1分以内に把握できる「要約レポート」にまとめます。

入力 (JSON):
- product / product_label
- total_reviews / defect_count / improvement_count / praise_count
- clusters: トピック別の件数と代表レビューサンプル

出力 (JSON、これだけ):
{
  "summary_ja": {
    "headline": "今のポイントを 30 字以内の見出しで",
    "narrative": "全体の状況を 2-3 文 (100-200字)",
    "key_findings": [
      { "topic": "ダストカップ", "count": 20, "finding": "20-40 字で具体的に何が言われているか" },
      { "topic": "...", "count": N, "finding": "..." },
      { "topic": "...", "count": N, "finding": "..." }
    ],
    "actions": [
      "工場が今すべき行動 1 (40 字以内、具体的に)",
      "工場が今すべき行動 2 (40 字以内、具体的に)"
    ]
  },
  "summary_zh": {
    "headline": "同上の中国語訳",
    "narrative": "...",
    "key_findings": [ 同構造 ],
    "actions": [ ... ]
  }
}

ルール:
- 数字は input から正確に持つ。創作禁止
- "key_findings" は count が多い順に最大3つ
- "actions" は工場が具体的に取れる動作 (検査強化 / 部品変更 / 設計見直し 等)。「検討する」「考慮する」のような曖昧な動詞は NG
- defect (深刻な不具合) が含まれるトピックは findings/actions で優先的に取り上げる
- JSON 配列・オブジェクト形式厳守、JSON 以外何も出力しない
"""


def call_claude(api_key: str, model: str, payload_in: dict) -> dict:
    body = json.dumps({
        "model": model,
        "max_tokens": 2000,
        "temperature": 0.3,
        "system": [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        "messages": [{
            "role": "user",
            "content": "以下を要約してください (JSON):\n\n" + json.dumps(payload_in, ensure_ascii=False, indent=2),
        }],
    }).encode("utf-8")
    req = urllib.request.Request(
        ANTHROPIC_API_URL, data=body, method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip().rstrip("`").strip()
    return json.loads(text)


def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY required", file=sys.stderr)
        return 1
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    products = (os.environ.get("SUMMARY_PRODUCTS") or "sh-j001,sh-j002").split(",")

    here = Path(__file__).resolve().parent
    for product in [p.strip() for p in products if p.strip()]:
        data = build_input(product)
        if not data:
            print(f"SKIP {product}: missing source files", file=sys.stderr)
            continue
        # Only top 8 clusters to keep prompt small
        prompt_payload = {
            **data,
            "clusters": data["clusters"][:8],
        }
        try:
            ai = call_claude(api_key, model, prompt_payload)
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {product}: {e}", file=sys.stderr)
            continue

        out = {
            "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "product": product,
            "stats": {
                "total_reviews": data["total_reviews"],
                "defect": data["defect_count"],
                "improvement": data["improvement_count"],
                "praise": data["praise_count"],
            },
            **ai,
        }
        out_path = here / f"summary-{product}.json"
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[{product}] wrote {out_path.name}: '{ai.get('summary_ja',{}).get('headline','')}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
