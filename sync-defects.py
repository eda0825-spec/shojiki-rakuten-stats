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
                print(f"WARN {repo} {state} p{page}: {e}", file=sys.stderr)
                break
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
        "body_excerpt": (issue.get("body") or "")[:280],
        # Full body (capped at 12000 chars) for inline rendering on dashboard.
        # Factory cannot access GitHub private repo, so we render markdown directly.
        "body": (issue.get("body") or "")[:12000],
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

    for product, repo in REPOS.items():
        try:
            issues = fetch_issues(repo, token)
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {repo}: {e}", file=sys.stderr)
            continue
        shaped = [shape(i, product) for i in issues]
        per_file = {"updatedAt": now, "product": product, "repo": repo, "count": len(shaped), "issues": shaped}
        (out_dir / f"defects-{product}.json").write_text(
            json.dumps(per_file, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        all_shaped.extend(shaped)
        print(f"[{product}] {len(shaped)} issues from {repo}")

    # Merged feed sorted by updated_at desc, capped at 200
    all_shaped.sort(key=lambda x: x["updated_at"], reverse=True)
    merged = {"updatedAt": now, "count": len(all_shaped), "issues": all_shaped[:200]}
    (out_dir / "defects-merged.json").write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote docs/data/defects-merged.json ({len(merged['issues'])} issues)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
