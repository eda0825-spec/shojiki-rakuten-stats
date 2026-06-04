#!/usr/bin/env python3
"""
Bridge: categorized customer reviews → GitHub Issues in defects repos.

categorized-sh-j001.json / categorized-sh-j002.json の中で
  category=defect AND severity=(high|medium)
のレビューを検出し、shojiki-defects-{j001|j002} に Issue を起票する。

重複防止: bridged-issues.json に処理済み review id を保持。

ENV:
  DEFECTS_SYNC_PAT  GitHub PAT (repo scope, write to both private repos)
  BRIDGE_MIN_SEVERITY  "high" or "medium" (default: high)
  BRIDGE_MAX_PER_RUN   1回の実行で起票する最大件数 (default: 20)
  BRIDGE_DRY_RUN       "1" なら起票せず内容を stdout に出すだけ
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.github.com"
REPO_OWNER = "eda0825-spec"
DEFECT_REPOS = {
    "sh-j001": f"{REPO_OWNER}/shojiki-defects-j001",
    "sh-j002": f"{REPO_OWNER}/shojiki-defects-j002",
}
RAKUTEN_BASE = "https://review.rakuten.co.jp/item/1/437323_"
ITEM_NUMBERS = {"sh-j001": "10000000", "sh-j002": "10000004"}

SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1, "n/a": 0}

STATE_PATH = Path(__file__).resolve().parent / "bridged-issues.json"


def gh_post(url: str, token: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"bridged": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"bridged": {}}


def save_state(state: dict) -> None:
    state["updatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_issue(review: dict, cat: dict, product: str) -> dict:
    sev = cat.get("severity", "n/a")
    sev_label = {"high": "[高]", "medium": "[中]", "low": "[低]"}.get(sev, "")
    title_ja = (cat.get("summary_ja") or "顧客レビューより不具合報告").split("\n")[0][:60]
    product_tag = "[J001]" if product == "sh-j001" else "[J002]"
    title = f"{product_tag} [顧客] {sev_label} {title_ja}".strip()

    star = "★" * (review.get("rating") or 0) + "☆" * (5 - (review.get("rating") or 0))
    review_url = f"{RAKUTEN_BASE}{ITEM_NUMBERS[product]}/"

    topics_line = ""
    if cat.get("topics"):
        topics_line = "・".join(cat["topics"])

    body = f"""> ⚠️ **このIssueは楽天レビューから自動生成されました**
> 自动从楽天评论生成 ({datetime.now(timezone.utc).strftime("%Y-%m-%d")})

## レビュー内容 / 评论原文

| 項目 / 项目 | 値 / 值 |
|---|---|
| 商品 / 产品 | {"SH-J001" if product == "sh-j001" else "SH-J002"} |
| 評価 / 评价 | {star} ({review.get("rating", "?")}) |
| 投稿日 / 日期 | {review.get("postDate") or "不明"} |
| 投稿者 / 投稿者 | {review.get("nickname") or "—"} |
| AI 分類 / AI 分类 | **{cat.get("category")}** ・ 深刻度 **{cat.get("severity")}** |
| トピック / 话题 | {topics_line or "—"} |

### 要約 / 摘要

- **日本語**: {cat.get("summary_ja") or "—"}
- **中文**: {cat.get("summary_zh") or "—"}

### 対策案 (AI 提案) / 对策建议 (AI 提议)

{cat.get("action_hint") or "(なし / 无)"}

### 原文 / 原文

```
{(review.get("body") or "").strip()}
```

---

🔗 元レビュー: <{review_url}>
🆔 Review ID: `{review.get("id")}`
"""

    labels = ["type:defect", "status:new", "source:customer"]
    if sev in ("high", "medium", "low"):
        labels.append(f"severity:{sev}")
    # map topics → area labels heuristically
    topic_to_area = {
        "バッテリー": "area:battery",
        "电池": "area:battery",
        "充電": "area:charging",
        "充电": "area:charging",
        "モーター": "area:motor",
        "电机": "area:motor",
        "ローラー": "area:roller",
        "滚刷": "area:roller",
        "ダストカップ": "area:dustcup",
        "集尘杯": "area:dustcup",
        "フィルター": "area:filter",
        "过滤器": "area:filter",
        "ボタン": "area:button",
        "按钮": "area:button",
        "重量": "area:body",
        "外装": "area:body",
        "付属品": "area:accessory",
        "配件": "area:accessory",
    }
    for t in (cat.get("topics") or []):
        for kw, lab in topic_to_area.items():
            if kw in t and lab not in labels:
                labels.append(lab)
                break

    return {"title": title, "body": body, "labels": labels}


def main() -> int:
    token = os.environ.get("DEFECTS_SYNC_PAT")
    if not token:
        print(
            "NOTICE: DEFECTS_SYNC_PAT not set — skipping bridge.\n"
            "  To enable: add a GitHub PAT (Classic, repo scope) as secret\n"
            "  DEFECTS_SYNC_PAT in eda0825-spec/shojiki-rakuten-stats.\n"
            "  See docs/SETUP_CHECKLIST.md for full steps.",
            file=sys.stderr,
        )
        return 0  # exit 0 so the workflow stays green when PAT not yet configured
    min_sev = os.environ.get("BRIDGE_MIN_SEVERITY", "high").strip().lower()
    max_per_run = int(os.environ.get("BRIDGE_MAX_PER_RUN", "20"))
    dry = os.environ.get("BRIDGE_DRY_RUN") == "1"
    min_rank = SEVERITY_RANK.get(min_sev, 3)

    here = Path(__file__).resolve().parent
    state = load_state()
    bridged = state.get("bridged", {})
    total_created = 0

    for product, repo in DEFECT_REPOS.items():
        rev_path = here / f"reviews-{product}.json"
        cat_path = here / f"categorized-{product}.json"
        if not rev_path.exists() or not cat_path.exists():
            print(f"SKIP [{product}] missing source file", file=sys.stderr)
            continue
        reviews = {r["id"]: r for r in json.loads(rev_path.read_text(encoding="utf-8")).get("reviews", [])}
        cats = {c["id"]: c for c in json.loads(cat_path.read_text(encoding="utf-8")).get("results", [])}

        # candidates: defect category AND severity >= min
        candidates = []
        for rid, c in cats.items():
            if c.get("category") != "defect":
                continue
            if SEVERITY_RANK.get(c.get("severity", "n/a"), 0) < min_rank:
                continue
            if rid in bridged:
                continue
            r = reviews.get(rid)
            if not r:
                continue
            candidates.append((r, c))

        # newest first
        candidates.sort(key=lambda x: x[0].get("postDate", "0000-00-00"), reverse=True)
        candidates = candidates[:max_per_run]

        print(f"[{product}] {len(candidates)} new candidate(s) to bridge into Issues", file=sys.stderr)

        for r, c in candidates:
            issue = build_issue(r, c, product)
            if dry:
                print(f"\n=== DRY RUN [{product}] ===")
                print(f"  title: {issue['title']}")
                print(f"  labels: {issue['labels']}")
                print(f"  body (first 200 chars): {issue['body'][:200]}")
                # dry-run では bridged に記録しない (記録すると本番実行時に連携済み扱いで Issue 化されない)
                continue
            try:
                resp = gh_post(f"{API}/repos/{repo}/issues", token, issue)
                num = resp.get("number")
                url = resp.get("html_url")
                bridged[r["id"]] = {"product": product, "issue_number": num, "url": url, "bridged_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
                total_created += 1
                print(f"  [{product}] created #{num}: {url}")
            except urllib.error.HTTPError as e:
                print(f"  ERROR [{product}] {r['id']}: {e} - {e.read().decode()[:200]}", file=sys.stderr)
            except Exception as e:  # noqa: BLE001
                print(f"  ERROR [{product}] {r['id']}: {e}", file=sys.stderr)

    state["bridged"] = bridged
    save_state(state)
    print(f"DONE: created {total_created} Issues, total bridged: {len(bridged)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
