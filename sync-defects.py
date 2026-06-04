#!/usr/bin/env python3
"""
Mirror Issues from private shojiki-defects-{j001,j002} repos into a public JSON
file that the dashboard (defects-dashboard.html) can render without each
viewer needing repo auth.

Outputs:
  docs/data/defects-merged.json  最新 100 件の open issue (両商品まとめ)
  docs/data/defects-sh-j001.json
  docs/data/defects-sh-j002.json

Env:
  DEFECTS_SYNC_PAT   GitHub PAT with `repo` scope (read access to both private repos)
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.github.com"
REPOS = {
    "sh-j001": "eda0825-spec/shojiki-defects-j001",
    "sh-j002": "eda0825-spec/shojiki-defects-j002",
}


def gh(url: str, token: str) -> tuple[dict | list, dict]:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.loads(r.read())
        headers = dict(r.headers)
    return body, headers


def fetch_issues(repo: str, token: str) -> list[dict]:
    """Fetch all open + recently-closed issues, paginated."""
    out: list[dict] = []
    for state in ("open", "closed"):
        page = 1
        while True:
            url = f"{API}/repos/{repo}/issues?state={state}&per_page=100&page={page}&sort=updated&direction=desc"
            try:
                items, _ = gh(url, token)
            except urllib.error.HTTPError as e:
                # 一時的なAPIエラーで部分結果を返すと、公開JSONを欠損状態で上書きしてしまう。
                # ここで例外を伝播させ、呼び出し側(main)で「書き込まない」判断をさせる。
                raise RuntimeError(f"{repo} {state} p{page} fetch failed: {e}") from e
            if not items:
                break
            for it in items:
                if it.get("pull_request"):
                    continue  # skip PRs
                out.append(it)
            if len(items) < 100:
                break
            page += 1
            # closed: cap at 200 (2 pages) to keep file small
            if state == "closed" and page > 2:
                break
    return out


# 公開JSON用 PII マスク: 注文番号(楽天形式)と 氏名/投稿者 を伏せる。
# admin はこの JSON ではなく GitHub API から実データを直接取得するため、マスクは
# 公開(PAT なし)閲覧者にのみ効く。管理側は引き続き実データを閲覧できる。
_ORDER_RE = re.compile(r"\d{6}-\d{8}-\d{10}")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?<!\d)0\d{1,3}[-(]?\d{1,4}[-)]?\d{3,4}(?!\d)")
_POSTAL_RE = re.compile(r"〒\s?\d{3}-?\d{4}")
# 構造化テーブル行で値をマスクする PII/業務情報キー
_PII_ROW_RE = re.compile(
    r"(\|\s*(?:注文番号|氏名|お名前|名前|投稿者|電話番号|電話|TEL|メール|メールアドレス|E-?mail|住所|郵便番号|郵便|ロット番号|ロット|シリアル番号|シリアル)[^|]*\|\s*)([^|]+?)(\s*\|)"
)
# 顧客の自由記述セクションは公開JSONから内容を伏せる (PII/業務情報の漏えい防止)。
# AI 生成の「要約」「対策案」は残す。詳細はWeChat要約と管理画面(API実データ)で参照する。
_FREETEXT_HEADINGS = ("原文", "詳細", "補足", "症状")


def _hide_verbatim_sections(text: str) -> str:
    out, skip = [], False
    for ln in text.split("\n"):
        h = re.match(r"^#{2,4}\s+(.+?)\s*$", ln)
        if h:
            base = re.split(r"\s*/\s*", h.group(1))[0]
            skip = any(base.startswith(k) for k in _FREETEXT_HEADINGS)
            out.append(ln)
            if skip:
                out.append("（個人情報を含むため管理画面で確認）")
            continue
        if not skip:
            out.append(ln)
    return "\n".join(out)


def mask_pii(text: str) -> str:
    if not text:
        return text
    t = _hide_verbatim_sections(text)
    t = _ORDER_RE.sub("●●●（管理画面で確認）", t)
    t = _EMAIL_RE.sub("●●●", t)
    t = _PHONE_RE.sub("●●●", t)
    t = _POSTAL_RE.sub("●●●", t)
    t = _PII_ROW_RE.sub(lambda m: m.group(1) + "●●●" + m.group(3), t)
    return t


def shape(issue: dict, product: str) -> dict:
    labels = [l["name"] for l in (issue.get("labels") or [])]
    severity = next((l.replace("severity:", "") for l in labels if l.startswith("severity:")), None)
    status = next((l.replace("status:", "") for l in labels if l.startswith("status:")), None)
    areas = [l.replace("area:", "") for l in labels if l.startswith("area:")]
    return {
        "id": issue["id"],
        "number": issue["number"],
        "product": product,
        "title": issue["title"],
        "url": issue["html_url"],
        "state": issue["state"],
        "user": (issue.get("user") or {}).get("login"),
        "assignees": [a["login"] for a in (issue.get("assignees") or [])],
        "labels": labels,
        "severity": severity,
        "status": status,
        "areas": areas,
        "created_at": issue["created_at"],
        "updated_at": issue["updated_at"],
        "closed_at": issue.get("closed_at"),
        "comments": issue.get("comments", 0),
        "body_excerpt": mask_pii((issue.get("body") or "")[:280]),
        # Full body (capped at 12000 chars) for inline rendering on dashboard.
        # Factory cannot access GitHub private repo, so we render markdown directly.
        # 注文番号・氏名は公開JSONではマスク (admin は API から実データ取得)。
        "body": mask_pii((issue.get("body") or "")[:12000]),
    }


def main() -> int:
    token = os.environ.get("DEFECTS_SYNC_PAT")
    if not token:
        print(
            "NOTICE: DEFECTS_SYNC_PAT not set — skipping sync.\n"
            "  See docs/SETUP_CHECKLIST.md to enable aggregated dashboard.",
            file=sys.stderr,
        )
        return 0

    here = Path(__file__).resolve().parent
    out_dir = here / "docs" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_shaped: list[dict] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # まず全 repo を取得してから書き込む。1 つでも失敗したら既存ファイルを一切上書きしない
    # (件数が突然 0 件/片側商品だけになる事故を防止)。
    fetched: dict[str, list[dict]] = {}
    failures: list[str] = []
    for product, repo in REPOS.items():
        try:
            fetched[product] = fetch_issues(repo, token)
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {repo}: {e}", file=sys.stderr)
            failures.append(product)

    if failures:
        print(
            f"ERROR: {failures} の取得に失敗したため、既存の公開JSONを保持します (欠損上書き防止)。"
            " 次回の正常実行で更新されます。",
            file=sys.stderr,
        )
        return 1

    for product, repo in REPOS.items():
        shaped = [shape(i, product) for i in fetched[product]]
        per_file = {"updatedAt": now, "product": product, "repo": repo, "count": len(shaped), "issues": shaped}
        (out_dir / f"defects-{product}.json").write_text(
            json.dumps(per_file, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        all_shaped.extend(shaped)
        print(f"[{product}] {len(shaped)} issues from {repo}")

    # Merged feed sorted by updated_at desc. cap を 1000 に引き上げ (200 だと件数集計が過小になるため)。
    all_shaped.sort(key=lambda x: x["updated_at"], reverse=True)
    merged = {"updatedAt": now, "count": len(all_shaped), "issues": all_shaped[:1000]}
    (out_dir / "defects-merged.json").write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote docs/data/defects-merged.json ({len(merged['issues'])} issues)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
