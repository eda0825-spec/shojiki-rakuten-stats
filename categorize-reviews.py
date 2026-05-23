#!/usr/bin/env python3
"""
Read reviews-sh-j001.json / reviews-sh-j002.json, classify each review with the
Claude API into one of four buckets, summarize in Japanese, and translate the
summary to Chinese so the factory can read it directly.

Output (next to this script):
  categorized-sh-j001.json
  categorized-sh-j002.json

Incremental: previously-categorized review ids are skipped. To re-run from
scratch set CATEGORIZE_FULL_RESCAN=1.

Categories:
  defect       明確に「壊れた / 動かない / 充電できない / 異音 / 安全性」など製品不具合
  improvement  使えるが改善要望「もっと軽く / 〜が欲しい / 〜だったら良い」
  praise       良かった点だけのレビュー
  question     使い方の疑問・サポート依頼
  other        分類不能 / 配送・梱包・店舗対応のみ

Severity (defect/improvement only, else "n/a"):
  high    安全性・基本機能停止
  medium  使用上明確に支障
  low     軽微な不便

Env:
  ANTHROPIC_API_KEY        required
  ANTHROPIC_MODEL          default: claude-sonnet-4-6
  CATEGORIZE_BATCH_SIZE    reviews per Claude call, default 8
  CATEGORIZE_MAX_REVIEWS   safety cap per run, default 200 (raise for first run)
  CATEGORIZE_FULL_RESCAN   if "1", ignore existing categorized file
  CATEGORIZE_ONLY_PRODUCT  "sh-j001" or "sh-j002" to limit
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-6"
PRODUCTS = ["sh-j001", "sh-j002"]

PRODUCT_LABEL = {
    "sh-j001": "SHOJIKI SH-J001 (コードレス掃除機・吸引力重視モデル)",
    "sh-j002": "SHOJIKI SH-J002 (コードレス掃除機・軽量&操作性重視モデル)",
}

SYSTEM_PROMPT = """あなたは日本の家電ブランド SHOJIKI の品質改善担当アシスタントです。
楽天市場の商品レビューを読み、中国の製造工場と日本のエンジニアが共有できる形に整理します。

タスク:
複数のレビューを受け取り、各レビューについて以下のJSONフィールドを返してください。

- id: 入力のidをそのまま返す (string)
- category: 以下のいずれか1つだけ (string)
    "defect"       明確な製品不具合 (壊れた/動かない/充電できない/異音/異臭/煙/発熱/部品脱落 等)
    "improvement"  使えるが改善要望 (重い・うるさい・吸引力もう少し・〜が欲しい 等)
    "praise"       良かった点だけ
    "question"     使い方の疑問・サポート依頼
    "other"        分類不能/配送・店舗対応のみ
- severity: "high" | "medium" | "low" | "n/a"
    defect/improvement の時のみ意味あり。それ以外は "n/a"。
    high  : 安全性 (発火・感電・破損で怪我リスク) または基本機能の完全停止
    medium: 使用上明確に支障がある / 多くのユーザーが不満を持ちそう
    low   : 軽微な不便・好みの範囲
- summary_ja: 30-60字の日本語要約。事実のみ、感想形容詞は最小限 (string)
- summary_zh: 上記要約の中国語訳 (簡体字)。工場の技術者が読みやすい技術的・即物的な表現にする (string)
- topics: 関連する部位・機能のキーワードを1-4個 (array of string)
    例: ["バッテリー", "充電"], ["ダストカップ", "操作性"], ["ローラー", "髪の毛"], ["重量"], ["吸引力"]
    日本語で統一。工場側はsummary_zhと合わせて読む。
- action_hint: 工場/エンジニアが取れそうなアクション案を1文。改善ヒントが無ければ null (string|null)
    例: "ダストカップのロック機構の操作力を見直す", "充電端子の接触不良検査を強化"

出力ルール:
- JSONの配列のみ出力。前置き・コードフェンス・解説は一切禁止。
- 入力件数と同じ件数の配列要素を返す。順序も入力と同じ。
- 1つのレビューに複数の論点があれば、最も深刻なものでcategory/severityを決める。
- 軽い不満1点+称賛多数なら "praise" でなく "improvement" にする (改善信号を拾う)。
- 「使ってない/贈答用/まだ届いてない」は "other"。
"""


def call_claude_with_retry(api_key: str, model: str, batch: list[dict], product: str, attempts: int = 2) -> list[dict]:
    last_err = None
    for i in range(attempts):
        try:
            return call_claude(api_key, model, batch, product)
        except RuntimeError as e:
            last_err = e
            if "non-JSON" in str(e) or "non-array" in str(e):
                print(f"  retry {i+1}/{attempts}: {e}", file=sys.stderr)
                time.sleep(2)
                continue
            raise
        except Exception:
            raise
    raise last_err  # type: ignore


def call_claude(api_key: str, model: str, batch: list[dict], product: str) -> list[dict]:
    user_lines = [
        f"商品: {PRODUCT_LABEL.get(product, product)}",
        "以下の各レビューを分類・要約・翻訳してください。",
        "",
        "入力 (JSON):",
        json.dumps(
            [
                {
                    "id": r["id"],
                    "rating": r.get("rating"),
                    "title": r.get("title"),
                    "body": r.get("body"),
                }
                for r in batch
            ],
            ensure_ascii=False,
        ),
    ]
    payload = {
        "model": model,
        "max_tokens": 4000,
        "temperature": 0.2,
        "system": [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "messages": [{"role": "user", "content": "\n".join(user_lines)}],
    }
    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read())
    text = "".join(
        block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
    ).strip()
    # Best-effort cleanup of any code fences
    if text.startswith("```"):
        text = text.split("```", 2)
        text = text[1] if len(text) >= 2 else ""
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    try:
        out = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Claude returned non-JSON: {e}\n{text[:500]}")
    if not isinstance(out, list):
        raise RuntimeError(f"Claude returned non-array JSON: {type(out).__name__}")
    return out


def load_existing(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {r["id"]: r for r in data.get("results", []) if r.get("id")}


def categorize_product(product: str, api_key: str, model: str, batch_size: int, max_reviews: int, full_rescan: bool) -> None:
    here = Path(__file__).resolve().parent
    src = here / f"reviews-{product}.json"
    dst = here / f"categorized-{product}.json"
    if not src.exists():
        print(f"SKIP [{product}] no source file {src.name}", file=sys.stderr)
        return

    raw = json.loads(src.read_text(encoding="utf-8"))
    reviews = raw.get("reviews", [])
    existing = {} if full_rescan else load_existing(dst)

    todo = [r for r in reviews if r["id"] not in existing]
    todo = todo[:max_reviews]
    print(f"[{product}] total={len(reviews)} done={len(existing)} todo_now={len(todo)}", file=sys.stderr)

    results: dict[str, dict] = dict(existing)
    processed = 0
    for i in range(0, len(todo), batch_size):
        batch = todo[i : i + batch_size]
        try:
            out = call_claude_with_retry(api_key, model, batch, product)
        except Exception as e:  # noqa: BLE001
            print(f"ERROR [{product}] batch {i // batch_size}: {e}", file=sys.stderr)
            # save what we have so far and continue
            time.sleep(5)
            continue

        by_id = {row.get("id"): row for row in out if isinstance(row, dict)}
        for r in batch:
            row = by_id.get(r["id"])
            if not row:
                continue
            results[r["id"]] = {
                "id": r["id"],
                "category": row.get("category", "other"),
                "severity": row.get("severity", "n/a"),
                "summary_ja": row.get("summary_ja", ""),
                "summary_zh": row.get("summary_zh", ""),
                "topics": row.get("topics") or [],
                "action_hint": row.get("action_hint"),
            }
        processed += len(batch)
        print(f"[{product}] batch {i // batch_size + 1}: +{len(batch)} (running {processed}/{len(todo)})", file=sys.stderr)

        # Periodic flush so partial progress survives crashes / cancellation
        if (i // batch_size) % 5 == 4:
            _flush(dst, product, raw, results)

    _flush(dst, product, raw, results)
    print(f"[{product}] wrote {dst.name}: {len(results)} categorized")


def _flush(path: Path, product: str, raw: dict, results: dict[str, dict]) -> None:
    payload = {
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "product": product,
        "sourceUpdatedAt": raw.get("updatedAt"),
        "count": len(results),
        "results": list(results.values()),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY required", file=sys.stderr)
        return 1
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    batch_size = int(os.environ.get("CATEGORIZE_BATCH_SIZE", "8"))
    max_reviews = int(os.environ.get("CATEGORIZE_MAX_REVIEWS", "200"))
    full_rescan = os.environ.get("CATEGORIZE_FULL_RESCAN") == "1"
    only = os.environ.get("CATEGORIZE_ONLY_PRODUCT")

    targets = [only] if only in PRODUCTS else PRODUCTS
    for product in targets:
        categorize_product(product, api_key, model, batch_size, max_reviews, full_rescan)
    return 0


if __name__ == "__main__":
    sys.exit(main())
