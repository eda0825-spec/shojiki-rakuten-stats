#!/usr/bin/env python3
"""
Scrape all customer reviews for a Rakuten Ichiba item from review.rakuten.co.jp
and write both the raw reviews and an aggregated analysis to JSON.

Outputs (next to this script):
  rakuten-reviews.json           raw list of reviews
  rakuten-reviews-analysis.json  aggregated stats

Env:
  REVIEW_ITEM_PATH   item path under /item/1/, default "437323_10000000"
  REVIEW_MAX_PAGES   safety cap, default 100
  REVIEW_SLEEP_SEC   delay between page fetches, default 1.5
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

BASE = "https://review.rakuten.co.jp"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Referer": "https://www.rakuten.co.jp/",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    for enc in ("utf-8", "euc-jp", "shift_jis"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p", "div", "li"):
            self.parts.append("\n")


def strip_html(s: str) -> str:
    p = _Stripper()
    p.feed(s)
    text = "".join(p.parts)
    text = re.sub(r"[ \t　]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


# Rakuten review pages historically use blocks identified by review item containers
# that include a star rating image (alt="..."), a posted date, an optional title,
# and a body. Markup changes over time, so the parser uses multiple fallback
# heuristics and logs when nothing matches.
_REVIEW_BLOCK_RE = re.compile(
    r'<div[^>]*class="[^"]*(?:revRvwUserMain|review-body|revRvwUserSec)[^"]*"[^>]*>(.*?)</div>\s*</div>',
    re.DOTALL,
)
_STAR_RE = re.compile(r'(?:alt|aria-label)="(\d)(?:\.0)?\s*[^"]*"')
_STAR_FALLBACK_RE = re.compile(r"★\s*(\d)")
_DATE_RE = re.compile(r"(\d{4})[/年\-](\d{1,2})[/月\-](\d{1,2})")
_REVIEWER_RE = re.compile(
    r'(?:nickname|user|reviewer)[^>]*>\s*([^<\s][^<]{0,40}?)\s*<', re.IGNORECASE
)
_AGE_GENDER_RE = re.compile(r"(\d{2,3})代\s*[・/\s]?\s*(男性|女性|男|女)?")
_TOTAL_RE = re.compile(r"(?:全|計|レビュー(?:総)?件数[:：]?)\s*([\d,]+)\s*件")
_NEXT_PAGE_RE = re.compile(r'href="([^"]*/(\d+)\.1/)"[^>]*>(?:次へ|&gt;|next)', re.IGNORECASE)


def parse_page(html: str) -> tuple[list[dict], int | None]:
    reviews: list[dict] = []

    blocks = _REVIEW_BLOCK_RE.findall(html)
    if not blocks:
        # Looser fallback: review items often live inside <div class="...rvwBox...">
        blocks = re.findall(
            r'<div[^>]*class="[^"]*rvw[^"]*"[^>]*>(.*?)</div>\s*</div>',
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )

    for block in blocks:
        m_star = _STAR_RE.search(block) or _STAR_FALLBACK_RE.search(block)
        if not m_star:
            continue
        rating = int(m_star.group(1))

        m_date = _DATE_RE.search(block)
        date = (
            f"{m_date.group(1)}-{int(m_date.group(2)):02d}-{int(m_date.group(3)):02d}"
            if m_date
            else None
        )

        m_age = _AGE_GENDER_RE.search(strip_html(block))
        age = m_age.group(1) + "代" if m_age else None
        gender = m_age.group(2) if (m_age and m_age.group(2)) else None

        m_user = _REVIEWER_RE.search(block)
        reviewer = m_user.group(1) if m_user else None

        # Title is typically inside a heading or a span with class containing "title".
        m_title = re.search(
            r'<(?:h\d|span)[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</(?:h\d|span)>',
            block,
            flags=re.DOTALL | re.IGNORECASE,
        )
        title = strip_html(m_title.group(1)) if m_title else None

        text = strip_html(block)
        # Heuristic body: take the longest non-header line.
        lines = [ln.strip() for ln in text.split("\n") if len(ln.strip()) >= 5]
        body = max(lines, key=len) if lines else text

        reviews.append(
            {
                "rating": rating,
                "date": date,
                "title": title,
                "body": body,
                "age": age,
                "gender": gender,
                "reviewer": reviewer,
            }
        )

    # Find the highest numbered page link present on the listing to know last page.
    last_page = None
    for m in re.finditer(r'/(\d+)\.1/"', html):
        n = int(m.group(1))
        last_page = n if last_page is None else max(last_page, n)

    return reviews, last_page


_STOPWORDS = set(
    "の は が を に て と で も や な し い う お か こ さ そ た だ "
    "です ます した して いる ある なる する いう こと もの ため よう より とても "
    "この その あの どの これ それ あれ どれ ここ そこ あそこ どこ また まで から "
    "ない なく なって ですが ですよ でした 思い 思う 買い 買って 商品 購入 レビュー "
    "とても 少し すごく 凄く 凄い 素晴らしい 良い 良かった 悪い".split()
)
_TOKEN_RE = re.compile(r"[一-龯ぁ-んァ-ヶー々a-zA-Z]{2,}")


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text) if t not in _STOPWORDS]


def analyze(reviews: list[dict]) -> dict:
    n = len(reviews)
    if n == 0:
        return {"count": 0}

    ratings = [r["rating"] for r in reviews if r.get("rating")]
    avg = round(sum(ratings) / len(ratings), 3) if ratings else None
    dist = Counter(ratings)

    by_month: dict[str, int] = {}
    for r in reviews:
        if r.get("date"):
            ym = r["date"][:7]
            by_month[ym] = by_month.get(ym, 0) + 1

    gender = Counter(r.get("gender") for r in reviews if r.get("gender"))
    age = Counter(r.get("age") for r in reviews if r.get("age"))

    tokens: list[str] = []
    pos_tokens: list[str] = []
    neg_tokens: list[str] = []
    for r in reviews:
        toks = tokenize((r.get("title") or "") + " " + (r.get("body") or ""))
        tokens.extend(toks)
        if r.get("rating", 0) >= 4:
            pos_tokens.extend(toks)
        elif r.get("rating", 0) <= 2:
            neg_tokens.extend(toks)

    def top(c: Counter, k: int = 30) -> list[list]:
        return [[w, n] for w, n in c.most_common(k)]

    # Pick representative reviews (longest body per rating bucket).
    samples: dict[str, dict] = {}
    for star in (5, 4, 3, 2, 1):
        bucket = [r for r in reviews if r.get("rating") == star and r.get("body")]
        if bucket:
            samples[str(star)] = max(bucket, key=lambda r: len(r["body"]))

    return {
        "count": n,
        "average": avg,
        "rating_distribution": {str(k): dist.get(k, 0) for k in (5, 4, 3, 2, 1)},
        "monthly_count": dict(sorted(by_month.items())),
        "gender": dict(gender),
        "age": dict(sorted(age.items())),
        "top_words_overall": top(Counter(tokens)),
        "top_words_positive": top(Counter(pos_tokens)),
        "top_words_negative": top(Counter(neg_tokens)),
        "samples_by_rating": samples,
    }


def main() -> int:
    item = os.environ.get("REVIEW_ITEM_PATH", "437323_10000000")
    max_pages = int(os.environ.get("REVIEW_MAX_PAGES", "100"))
    sleep_sec = float(os.environ.get("REVIEW_SLEEP_SEC", "1.5"))

    all_reviews: list[dict] = []
    last_page_seen = 1
    for page in range(1, max_pages + 1):
        url = f"{BASE}/item/1/{item}/{page}.1/"
        try:
            html = fetch(url)
        except Exception as e:  # noqa: BLE001
            print(f"WARN: fetch failed page={page}: {e}", file=sys.stderr)
            break

        reviews, last_page = parse_page(html)
        if last_page:
            last_page_seen = max(last_page_seen, last_page)

        if not reviews and page > 1:
            print(f"INFO: no reviews on page {page}; stopping", file=sys.stderr)
            break

        all_reviews.extend(reviews)
        print(
            f"page {page}: parsed {len(reviews)} (total {len(all_reviews)}, "
            f"last_page_hint={last_page_seen})",
            file=sys.stderr,
        )

        if page >= last_page_seen:
            break
        time.sleep(sleep_sec)

    # Deduplicate (date + body) to be safe.
    seen: set[tuple] = set()
    dedup: list[dict] = []
    for r in all_reviews:
        key = (r.get("date"), (r.get("body") or "")[:80])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(r)

    here = Path(__file__).resolve().parent
    raw_path = here / "rakuten-reviews.json"
    analysis_path = here / "rakuten-reviews-analysis.json"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raw_path.write_text(
        json.dumps(
            {"updatedAt": now, "itemPath": item, "reviews": dedup},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    analysis = analyze(dedup)
    analysis_path.write_text(
        json.dumps(
            {"updatedAt": now, "itemPath": item, **analysis},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        f"Wrote {raw_path.name} ({len(dedup)} reviews) and "
        f"{analysis_path.name} (avg={analysis.get('average')})"
    )
    return 0 if dedup else 3


if __name__ == "__main__":
    sys.exit(main())
