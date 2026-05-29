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


CORE_FUNCTION_CLUSTERS = {"suction", "charging", "safety"}  # 製品の核心機能 (使えなくなる影響大)


def classify_issue_kind(issue: dict) -> str:
    """defect / return / other を Issue ラベルから判定"""
    labels = [str(l).lower() for l in (issue.get("labels") or [])]
    if any("return" in l for l in labels):
        return "return"
    if any("defect" in l for l in labels):
        return "defect"
    return "other"


def map_issue_to_cluster(issue: dict) -> str | None:
    """Issue タイトル + body から該当クラスタを推定 (簡易キーワード)"""
    text = (issue.get("title") or "") + " " + (issue.get("body_excerpt") or "")
    text = text.lower()
    for k, _name, topics in CLUSTERS:
        for t in topics:
            if t.lower() in text:
                return k
    return None


def load_issues(product: str) -> list[dict]:
    here = Path(__file__).resolve().parent
    p = here / "docs" / "data" / f"defects-{product}.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("issues", []) or []
    except Exception:
        return []


def build_input(product: str) -> dict | None:
    here = Path(__file__).resolve().parent
    revs_p = here / f"reviews-{product}.json"
    cats_p = here / f"categorized-{product}.json"
    if not revs_p.exists() or not cats_p.exists():
        return None
    revs = {r["id"]: r for r in json.loads(revs_p.read_text(encoding="utf-8")).get("reviews", [])}
    cats = json.loads(cats_p.read_text(encoding="utf-8")).get("results", [])
    issues = load_issues(product)

    # Aggregate per cluster (primary topic only) from reviews
    bucket = defaultdict(lambda: {
        "review_defect": 0, "review_improvement": 0,
        "issue_defect": 0, "issue_return": 0,
        "samples": [], "issue_samples": []
    })
    for c in cats:
        cat = c.get("category")
        if cat not in ("defect", "improvement"):
            continue
        pc = primary_cluster(c.get("topics") or [])
        if not pc:
            continue
        b = bucket[pc]
        key = "review_defect" if cat == "defect" else "review_improvement"
        b[key] += 1
        if len(b["samples"]) < 4:
            r = revs.get(c["id"]) or {}
            b["samples"].append({
                "rating": r.get("rating"),
                "summary_ja": c.get("summary_ja"),
                "severity": c.get("severity"),
                "category": cat,
            })

    # Merge defect/return Issues (factory-side reports)
    issue_kind_total = {"defect": 0, "return": 0}
    for it in issues:
        kind = classify_issue_kind(it)
        if kind == "other":
            continue
        issue_kind_total[kind] += 1
        ck = map_issue_to_cluster(it) or "other"
        if ck == "other":
            # Still count toward defect/return totals but no cluster bump
            continue
        b = bucket[ck]
        b["issue_defect" if kind == "defect" else "issue_return"] += 1
        if len(b["issue_samples"]) < 3:
            b["issue_samples"].append({
                "kind": kind,
                "title": it.get("title"),
                "severity": it.get("severity"),
            })

    # IMPACT scoring: 返品=5, 工場側不具合Issue=4, レビュー深刻不具合=3, レビュー改善要望=1
    # 核心機能 (suction/charging/safety) は ×1.5 ブースト
    def impact(k: str, v: dict) -> float:
        s = (v["issue_return"] * 5 + v["issue_defect"] * 4
             + v["review_defect"] * 3 + v["review_improvement"] * 1)
        if k in CORE_FUNCTION_CLUSTERS:
            s *= 1.5
        return s

    ranked = sorted(
        [{
            "key": k,
            "name": CLUSTER_NAME[k],
            "is_core_function": k in CORE_FUNCTION_CLUSTERS,
            "review_defect": v["review_defect"],
            "review_improvement": v["review_improvement"],
            "issue_defect": v["issue_defect"],
            "issue_return": v["issue_return"],
            "total_mentions": (v["review_defect"] + v["review_improvement"]
                               + v["issue_defect"] + v["issue_return"]),
            "impact_score": round(impact(k, v), 1),
            "samples": v["samples"],
            "issue_samples": v["issue_samples"],
        } for k, v in bucket.items()],
        key=lambda x: -x["impact_score"]
    )

    return {
        "product": product,
        "product_label": PRODUCT_LABEL.get(product, product),
        "total_reviews": len(revs),
        "total_categorized": len(cats),
        "review_defect": sum(1 for c in cats if c.get("category") == "defect"),
        "review_improvement": sum(1 for c in cats if c.get("category") == "improvement"),
        "praise_count": sum(1 for c in cats if c.get("category") == "praise"),
        "issue_defect_total": issue_kind_total["defect"],
        "issue_return_total": issue_kind_total["return"],
        "clusters": ranked,
        "scoring_note": "impact_score = 返品×5 + 工場側不具合×4 + レビュー深刻不具合×3 + レビュー改善要望×1 (核心機能=吸引力/充電/安全は×1.5)",
    }


SYSTEM_PROMPT = """あなたは日本の家電ブランド SHOJIKI の品質改善担当アシスタントです。
3つの情報源 (お客様レビュー / 工場側不具合Issue / 返品Issue) を統合し、
品質会議で1分以内に把握できる「要約レポート」にまとめます。

入力 (JSON):
- product / product_label
- total_reviews / review_defect / review_improvement / praise_count
- issue_defect_total / issue_return_total  ← 工場/サポート側に登録された Issue 件数
- clusters[]: クラスタごとに以下を含む
    - review_defect / review_improvement : レビュー由来
    - issue_defect / issue_return        : Issue 由来
    - total_mentions / impact_score
    - is_core_function : true なら吸引力/充電/安全など製品の核心機能
    - samples / issue_samples
- scoring_note : impact_score の算出ロジック

出力 (JSON、これだけ):
{
  "summary_ja": {
    "headline": "今のポイントを 30 字以内の見出しで",
    "narrative": "レビュー全体の傾向を 2-3 文 (100-200字)。何が多く言われているかに集中する。返品の件数や、impact_score など内部スコア名には絶対に触れない",
    "key_findings": [
      { "topic": "吸引力", "count": 27, "finding": "20-40 字で具体的に何が起きているか" },
      { "topic": "...", "count": N, "finding": "..." },
      { "topic": "...", "count": N, "finding": "..." }
    ],
    "actions": [
      "GlowUp と工場で取り組む改善アクション 1 (40 字以内、具体的に)",
      "GlowUp と工場で取り組む改善アクション 2 (40 字以内、具体的に)"
    ]
  },
  "summary_zh": {
    "headline": "同上の中国語訳",
    "narrative": "...",
    "key_findings": [ 同構造 ],
    "actions": [ ... ]
  }
}

優先順位ルール (重要):
1. **impact_score の高い順** に key_findings を最大3つ選ぶ。生件数 (total_mentions) より impact_score を優先
2. **製品の核心機能 (is_core_function=true: 吸引力・充電・安全)** で不満が出ているものは、件数が同程度なら ergonomic な不満 (着脱しにくい/操作しにくい) より優先
3. **返品 (issue_return) ＞ 工場側不具合 (issue_defect) ＞ レビュー深刻不具合 (review_defect) ＞ レビュー改善要望 (review_improvement)** の順で重い問題と扱う
4. headline は核心機能の深刻不具合があればそれを必ず含める。ergonomic な改善要望だけを headline にしない
5. count フィールドには total_mentions を入れる
6. finding には「レビュー内訳 (不具合N件・改善要望N件)」と「具体的に何が言われているか」を入れる。返品の件数には触れない

その他ルール:
- 数字は input から正確に持つ。創作禁止
- headline・narrative・finding すべてで返品や内部スコア名 (impact_score / total_mentions / cluster 等) には触れない。お客様レビューの話に集中する (返品は別タブで扱う)
- "actions" は GlowUp (ブランド側) と工場が共同で取り組む改善動作 (検査強化 / 部品変更 / 設計見直し 等)。特定の部門・工場だけを責める書き方 (他責) は禁止。主語は「自分たち (GlowUp・工場)」。「検討する」「考慮する」のような曖昧な動詞も NG
- JSON 配列・オブジェクト形式厳守、JSON 以外何も出力しない
"""


TYPE_SUMMARY_SYSTEM = """あなたは日本の家電ブランド SHOJIKI の品質改善担当アシスタントです。
特定の Issue タイプ (returns または defects) だけを対象に、品質会議で即座に
把握できる「要約レポート」を作ります。

入力 (JSON):
- product / product_label
- issue_type: "return" または "defect"
- count: 件数
- issues: 各 Issue の {number, title, body_excerpt, fields(パース済み)}

出力 (JSON、これだけ):
{
  "summary_ja": {
    "headline": "工場が最優先で対応すべき要点を1文 (35字以内・体言止め)。これだけ読めば何をすべきか分かる一言",
    "narrative": "現在のNeg件数の特徴を 2-3文 (80-200字)。理由/対応の傾向や、共通する顧客の不満内容に触れる。レビューや他データには触れない、このタイプの Issue だけ。",
    "key_findings": [
      { "topic": "充電", "count": 3, "finding": "症状と推定原因の要点 (60字以内)" }
    ],
    "actions": [
      "GlowUp と工場で取り組む改善アクション 1 (40字以内)",
      "GlowUp と工場で取り組む改善アクション 2 (40字以内)"
    ]
  },
  "summary_zh": { 同上の中国語訳 }
}

ルール:
- 数字は input から正確に持つ。創作禁止
- "key_findings" は「件数が多い/深刻な順」=対応優先順位の高い順に並べ、最大3件。topic は短い名詞 (充電/吸引力/ダストカップ 等)、count はそのトピックの件数
- "headline" は最も優先度の高い課題を1文で。工場が一目で対応対象を把握できる表現
- レビュー全体傾向や他タイプ (returns ページなら defects、defects ページなら returns) には絶対に触れない
- データが 0 件の場合: headline="現時点で対応事項なし" / narrative = "現時点で報告された{タイプ}はありません。" / key_findings=[] / actions = []
- データが 1 件しかない場合でも、その 1 件の具体的内容に踏み込む
- "actions" は GlowUp (ブランド側) と工場が共同で取り組む改善動作。特定の部門・工場だけを責める書き方 (他責) は禁止。「検討する」「考慮する」など曖昧動詞 NG、「再設計する」「強化する」「変更する」など具体動詞
- JSON 以外何も出力しない。文字列内の改行・引用符は必ずエスケープする
- 文字列値の中では半角ダブルクォート (") を絶対に使わない。型番・用語を強調したい場合は鉤括弧「」を使う (JSON が壊れるため)
"""


def call_claude_type_summary(api_key: str, model: str, payload_in: dict) -> dict:
    user_content = "以下の Issue 一覧を要約してください (JSON):\n\n" + json.dumps(payload_in, ensure_ascii=False, indent=2)
    last_err = None
    # JSON 崩れ対策: temperature=0 + 最大3回リトライ (Claude の出力が稀に不正JSONになるため)
    for _attempt in range(3):
        body = json.dumps({
            "model": model,
            "max_tokens": 2000,
            # temperature を 0 にすると毎回同じ壊れたJSONを返しリトライが無意味になるため、
            # わずかに散らして試行ごとに出力を変える
            "temperature": 0.4,
            "system": [{"type": "text", "text": TYPE_SUMMARY_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user_content}],
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
        try:
            return _parse_json_lenient(text)
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    raise last_err if last_err else RuntimeError("type summary parse failed")


def parse_issue_body(body: str) -> dict:
    """簡易 markdown table パーサ ({key:value})"""
    fields = {}
    if not body:
        return fields
    for ln in body.replace("\r\n", "\n").split("\n"):
        if "|" not in ln:
            continue
        # skip separator rows like |---|---|
        import re as _re
        if _re.match(r"^\s*\|?[\s:-]+\|[\s:|-]+$", ln):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) == 2 and cells[0] and cells[1] and cells[0] not in ("項目", "値"):
            fields[cells[0]] = cells[1]
    return fields


HEADLINE_SYSTEM = """あなたはカスタマーサポート担当が一覧画面で1秒で要点を掴めるよう、
顧客の返品/不具合報告内容を 15〜26 字以内の短い見出しに要約します。

入力 (JSON):
- issues: [{ number, body }] のリスト

出力 (JSON、これだけ):
{
  "headlines": {
    "<number>": { "ja": "...", "zh": "..." },
    ...
  }
}

要約ルール:
- 顧客が何に困っているか/何が起きているかを **動詞付き** で具体的に
- "まだ2回しか使用していませんが" のような前置きは捨てる
- 商品名や挨拶などのノイズは捨て、不具合/不満の core だけ拾う
- 例: "カーペットでペット毛が吸えない" / "充電スタンドで通電しない" / "本体破損 (操作パネル欠落)"
- 26字以内厳守 (はみ出る場合は短くする、句読点や余計な接続詞を削る)
- ja は日本語、zh は中国語簡体字。両方必須
- 創作禁止: body にある内容のみから要約
- JSON 以外出力しない
"""


def build_issue_headlines(api_key: str, model: str, product: str) -> dict | None:
    """全 Issue (defect + return) について Claude に短い見出しを生成させる。
    結果: { "<issue_number>": {"ja": "...", "zh": "..."} }"""
    here = Path(__file__).resolve().parent
    p = here / "docs" / "data" / f"defects-{product}.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8")).get("issues", []) or []
    except Exception:
        return None
    if not data:
        return {}

    payload = {
        "issues": [
            {
                "number": i.get("number"),
                "body": (i.get("body") or i.get("body_excerpt") or "")[:1500],
            }
            for i in data[:50]
            if (i.get("body") or i.get("body_excerpt"))
        ]
    }
    if not payload["issues"]:
        return {}

    body = json.dumps({
        "model": model,
        "max_tokens": 2000,
        "temperature": 0.3,
        "system": [{"type": "text", "text": HEADLINE_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        "messages": [{
            "role": "user",
            "content": "以下の Issue を要約して短い見出しを返してください:\n\n" + json.dumps(payload, ensure_ascii=False, indent=2),
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
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = json.loads(r.read())
        text = "".join(b.get("text", "") for b in raw.get("content", []) if b.get("type") == "text").strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip().rstrip("`").strip()
        parsed = json.loads(text)
        return parsed.get("headlines", {})
    except Exception as e:  # noqa: BLE001
        print(f"WARN {product} headlines failed: {e}", file=sys.stderr)
        return None


def _parse_json_lenient(text: str) -> dict:
    """Robust JSON parser: strips code fences, retries with relaxed escape handling."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.startswith("json"):
            t = t[4:]
        t = t.strip().rstrip("`").strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        # Best-effort: replace unescaped real newlines inside strings with \n.
        # Strategy: find narrative/actions value strings and re-escape.
        import re as _re
        # Replace bare LF inside double-quoted strings only
        def fix_str(m):
            inner = m.group(1).replace("\n", "\\n").replace("\r", "")
            return f'"{inner}"'
        t2 = _re.sub(r'"((?:[^"\\]|\\.)*)"', fix_str, t, flags=_re.DOTALL)
        try:
            return json.loads(t2)
        except json.JSONDecodeError:
            # オブジェクト/配列要素間のカンマ抜けを補修 ( }{ , }"  ]" など)
            t3 = _re.sub(r'}\s*{', '},{', t2)
            t3 = _re.sub(r'(["\]\}])\s*\n\s*(")', r'\1,\n\2', t3)
            return json.loads(t3)


def build_type_summary(api_key: str, model: str, product: str, issue_type: str) -> dict | None:
    """returns または defects だけを対象にした要約を生成して dict を返す。
    issue_type は "return" か "defect"。"""
    here = Path(__file__).resolve().parent
    p = here / "docs" / "data" / f"defects-{product}.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8")).get("issues", []) or []
    except Exception:
        return None

    def is_match(i: dict) -> bool:
        labels = [str(l).lower() for l in (i.get("labels") or [])]
        has_return = any("return" in l for l in labels)
        return has_return if issue_type == "return" else not has_return

    matched = [i for i in data if is_match(i)]
    payload = {
        "product": product,
        "product_label": PRODUCT_LABEL.get(product, product),
        "issue_type": issue_type,
        "count": len(matched),
        "issues": [
            {
                "number": i.get("number"),
                "title": i.get("title"),
                "state": i.get("state"),
                "fields": parse_issue_body(i.get("body") or i.get("body_excerpt") or ""),
                "body_excerpt": (i.get("body") or i.get("body_excerpt") or "")[:600],
            }
            for i in matched[:30]  # cap
        ],
    }
    try:
        return call_claude_type_summary(api_key, model, payload)
    except Exception as e:  # noqa: BLE001
        print(f"WARN {product}/{issue_type} summary failed: {e}", file=sys.stderr)
        return None


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

        # Per-type summaries (returns-only / defects-only) for detail pages
        returns_summary = build_type_summary(api_key, model, product, "return")
        defects_summary = build_type_summary(api_key, model, product, "defect")
        # Per-Issue short headlines (AI generated; used by detail card list)
        issue_headlines = build_issue_headlines(api_key, model, product)

        out = {
            "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "product": product,
            "stats": {
                "total_reviews": data["total_reviews"],
                "defect": data["review_defect"],
                "improvement": data["review_improvement"],
                "praise": data["praise_count"],
                "issue_defect": data["issue_defect_total"],
                "issue_return": data["issue_return_total"],
            },
            "top_clusters": [
                {
                    "name": c["name"],
                    "impact": c["impact_score"],
                    "review_defect": c["review_defect"],
                    "review_improvement": c["review_improvement"],
                    "issue_defect": c["issue_defect"],
                    "issue_return": c["issue_return"],
                    "is_core_function": c["is_core_function"],
                }
                for c in data["clusters"][:6]
            ],
            **ai,
            "returns_summary": returns_summary,
            "defects_summary": defects_summary,
            "issue_headlines": issue_headlines or {},
        }
        out_path = here / f"summary-{product}.json"
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[{product}] wrote {out_path.name}: '{ai.get('summary_ja',{}).get('headline','')}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
