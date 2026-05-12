#!/usr/bin/env python3
"""
Judge.me 上の新着レビューに、Claude API で生成したプライベート返信を自動投稿する。

Required env vars:
  JUDGE_ME_API_TOKEN     Judge.me Private API Token (write 権限)
  JUDGE_ME_SHOP_DOMAIN   例: shojiki-store.myshopify.com
  ANTHROPIC_API_KEY      console.anthropic.com で発行した API キー

Optional env vars:
  DRY_RUN                "true" にすると生成本文を stdout に出すだけで POST しない
  ANTHROPIC_MODEL        Claude モデル名 (デフォルト: claude-sonnet-4-6)
  JUDGE_ME_API_BASE      デフォルト: https://judge.me/api/v1
  MAX_REPLIES_PER_RUN    1 回の実行で処理する最大レビュー件数 (デフォルト: 20)
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

JUDGE_ME_API_BASE = os.environ.get("JUDGE_ME_API_BASE", "https://judge.me/api/v1")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-6"
STATE_FILE = Path(__file__).resolve().parent / "judgeme-processed.json"
PROCESSED_MAX = 1000

# ---------- ブランドトーンプロンプト ----------
SYSTEM_PROMPT = """役割
あなたは「SHOJIKI（正直なブランド）」のレビュー返信担当者。コードレス掃除機のレビューに対し、実在の日本人スタッフが一件ずつ読み込んで返信しているような、具体的で長文の返信を作成する。テンプレ感やAI臭さは禁止。目的は売り込みではなく、誤解の解消と信頼回復、納得感の提供である。

出力ルール
1 出力はレビュー返信本文のみ。解説、分析、下書き、箇条書きメモは出力しない。
2 文字数は必ず800〜1000文字。短文は禁止。
3 2〜4行ごとに改行して段落構成にする。
4 冒頭は必ず次の1文から開始する。完全一致で改変禁止。
この度はSHOJIKIをお選びいただき、誠にありがとうございます。
5 「このたびは」という平仮名は使用禁止。必ず「この度は」。
6 文末は必ず次の署名行で閉じる。これ以降は何も書かない。
SHOJIKIカスタマーサポート
7 「差し支えなければ」は禁止。質問する場合は別表現を使う。
8 「ダイソン」など他社製品の固有名詞は禁止。

製品に関するファクト
・当社は日本のメーカー、日本のブランドである。
・製造国は中国である（中国製）。
この2点は確定情報として扱う。

推論とファクトの扱い
返信文を作る前に、必ずレビュー内容を次の2種類に分けて頭の中で整理する。
A ファクト（レビュー文に明記されている事実、当社が確定として言える事実）
B 推論（レビューから想定できる状況、原因の可能性、一般論）
文章中ではファクトを優先し、推論は可能性表現で補助に留める。原因や仕様は断定しない。
ただし、必要以上に曖昧にせず、読む人が納得できる説明密度を確保する。
ファクトと推論をラベル表示してはいけない。内部で分けて考え、自然な文章に統合する。

返信に必ず入れる要素
A 感謝と受領
冒頭固定文の後に、レビュー投稿へのお礼と、読んだことが伝わる一文を入れる。

B 具体点の言及は最低3点
レビューから最低3点以上を拾って、体験として言い換えて触れる。単語の羅列は禁止。
例：軽さ、音、吸引力、髪の毛絡まり、ローラー停止、梱包状態、対応の印象、使用環境の記述など。

C 悪い評価への対応は丁寧に反論する
低評価や不満点がある場合、最初に不便だった気持ちは受け止める。
その上で、次の方針で反論する。
1 お客様を否定しない
2 事実ベースで誤解を正す
3 仕様の可能性と不具合の可能性を分けて説明し、断定を避けつつも論点を明確にする
4 当社としての考え方、品質基準、設計意図、サポート方針を丁寧に提示する
反論は攻撃ではなく、納得感を作る説明として行う。

D 質問はしてよいが、条件がある
質問は最大2つまで。お客様の手間を増やさない。
「差し支えなければ」は使わない。代替表現として以下のみ使用可。
・もしよろしければ
・可能でしたら
・お手すきの際に
写真や動画の依頼は、初期不良が強く疑われる場合や星1〜2の場合に限る。乱用しない。

E 改善とサポートの着地
最後は必ず、改善に活かす姿勢、必要な場合の個別対応、連絡しやすさを含めて安心感で締める。

日本製と誤認しているレビューへの特別ルール
レビュー内に「日本製」「日本で作っている」「日本製だから安心」等の誤認がある場合に限り、必ず1回だけ補足訂正を入れる。
誤認が無いレビューには、中国製の話題を出してはいけない。
訂正は角が立たないが、曖昧にせず事実を明確に述べる。必須3点は以下。
1 当社は日本のメーカーとして企画と品質管理を行っている
2 製造は中国の提携工場である
3 サポートは当社が責任を持つ
訂正文は短くし、その後に安心材料（検品、品質基準、サポート）を添える。

ケース別の反論の骨子
髪の毛絡まり
・絡まりが発生したという事実を受け止める
・一般に長い毛や量、床素材で絡まりやすさが変わる可能性を述べる（断定しない）
・対策提案は1つだけに絞る（例：使用後に毛を取り除く、絡まりやすい場所は短時間で区切る等）

ローラー停止
・停止して再起動が必要という不便を受け止める
・負荷が高い場面で回転を抑える挙動の可能性を説明（断定しない）
・頻発する場合は個別に状況確認する旨を明記し、質問は最大2つまで

品質や不具合疑い
・謝意と共感を明確に
・当社の対応方針（交換、確認、案内）を具体的に提示
・必要時のみ写真や動画を依頼

禁止事項
・テンプレだけの返信
・他社批判
・原因の断定
・お客様の使い方のせいと決めつける表現
・過剰な記号、絵文字、感嘆符の多用
・誤認の追認（日本製と書かれているのに同意する等）
・誤認が無いのに中国製の話を持ち出す
・「差し支えなければ」の使用

出力前チェック
・冒頭固定文で始まっている
・800〜1000文字
・具体点が3点以上
・悪い評価があれば、丁寧な反論が入っている
・質問は最大2つ、かつ「差し支えなければ」を使っていない
・日本製誤認がある場合のみ、中国製を明確に補足訂正している
・文末が「SHOJIKIカスタマーサポート」で終わっている
"""

DEFAULT_EMAIL_SUBJECT = "SHOJIKI カスタマーサポートよりレビューへのご返信"


# ---------- Judge.me API ----------
def judgeme_get(path: str, api_token: str, shop_domain: str, **extra_params) -> dict:
    params = {"api_token": api_token, "shop_domain": shop_domain, **extra_params}
    url = f"{JUDGE_ME_API_BASE}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def judgeme_post(path: str, body: dict, api_token: str, shop_domain: str) -> dict:
    params = {"api_token": api_token, "shop_domain": shop_domain}
    url = f"{JUDGE_ME_API_BASE}/{path}?{urllib.parse.urlencode(params)}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def fetch_reviews(api_token: str, shop_domain: str) -> list[dict]:
    data = judgeme_get(
        "reviews", api_token, shop_domain, per_page=100, page=1, published="true"
    )
    return data.get("reviews", [])


def post_private_reply(
    review_id: int, subject: str, body: str, api_token: str, shop_domain: str
) -> dict:
    payload = {
        "review_id": review_id,
        "send_private_email": True,
        "private_reply": {"email_subject": subject, "email_body": body},
    }
    return judgeme_post("private_replies", payload, api_token, shop_domain)


# ---------- Claude API ----------
def generate_reply(review: dict, anthropic_key: str) -> tuple[str, str]:
    rating = review.get("rating", "?")
    body = review.get("body") or ""
    title = review.get("title") or ""
    reviewer = review.get("reviewer") or {}
    reviewer_name = reviewer.get("name") or "(匿名)"

    user_content = (
        f"星評価: {rating} / 5\n"
        f"レビュータイトル: {title}\n"
        f"レビュー本文:\n{body}\n"
        f"投稿者名: {reviewer_name}"
    )

    payload = {
        "model": os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL),
        "max_tokens": 2000,
        "temperature": 0.7,
        "system": [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "messages": [{"role": "user", "content": user_content}],
    }

    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "x-api-key": anthropic_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())

    body = "".join(
        block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
    ).strip()

    # 出力ガード: 冒頭固定文と署名が無ければ補正する
    required_opening = "この度はSHOJIKIをお選びいただき、誠にありがとうございます。"
    required_closing = "SHOJIKIカスタマーサポート"
    if not body.startswith(required_opening):
        body = required_opening + "\n\n" + body
    if not body.rstrip().endswith(required_closing):
        body = body.rstrip() + "\n\n" + required_closing

    return DEFAULT_EMAIL_SUBJECT, body


# ---------- State ----------
def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"processed_ids": [], "updatedAt": None}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    state["updatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if len(state["processed_ids"]) > PROCESSED_MAX:
        state["processed_ids"] = state["processed_ids"][-PROCESSED_MAX:]
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# ---------- main ----------
def main() -> int:
    api_token = os.environ.get("JUDGE_ME_API_TOKEN")
    shop_domain = os.environ.get("JUDGE_ME_SHOP_DOMAIN")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"
    max_replies = int(os.environ.get("MAX_REPLIES_PER_RUN", "20"))

    missing = [
        name
        for name, val in [
            ("JUDGE_ME_API_TOKEN", api_token),
            ("JUDGE_ME_SHOP_DOMAIN", shop_domain),
            ("ANTHROPIC_API_KEY", anthropic_key),
        ]
        if not val
    ]
    if missing:
        print(f"ERROR: missing env vars: {', '.join(missing)}", file=sys.stderr)
        return 1

    state = load_state()
    processed = set(state.get("processed_ids", []))

    reviews = fetch_reviews(api_token, shop_domain)
    print(f"Fetched {len(reviews)} reviews. processed={len(processed)}")

    new_reviews = [r for r in reviews if r.get("id") not in processed]
    new_reviews.sort(key=lambda r: r.get("created_at") or "")
    if not new_reviews:
        print("No new reviews to reply to.")
        return 0

    print(f"{len(new_reviews)} new review(s). Processing up to {max_replies}.")
    handled = 0
    for review in new_reviews[:max_replies]:
        rid = review.get("id")
        try:
            subject, body = generate_reply(review, anthropic_key)
        except urllib.error.HTTPError as e:
            print(f"[skip retry] Claude API failed for review {rid}: {e.code} {e.reason}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"[skip retry] Claude API exception for review {rid}: {e}", file=sys.stderr)
            continue

        if dry_run:
            print(f"--- DRY_RUN review_id={rid} rating={review.get('rating')} ---")
            print(f"Subject: {subject}")
            print(body)
            print()
            continue

        try:
            post_private_reply(rid, subject, body, api_token, shop_domain)
            print(f"[ok] Posted private reply for review {rid}")
            processed.add(rid)
            handled += 1
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass
            if 400 <= e.code < 500:
                # 恒久エラーとみなし、再試行ループを避けるため processed に追加
                print(f"[mark-processed] Judge.me {e.code} for review {rid}: {err_body}", file=sys.stderr)
                processed.add(rid)
            else:
                print(f"[retry-next] Judge.me {e.code} for review {rid}: {err_body}", file=sys.stderr)
        except Exception as e:
            print(f"[retry-next] Judge.me exception for review {rid}: {e}", file=sys.stderr)

    if not dry_run:
        state["processed_ids"] = sorted(processed)
        save_state(state)
        print(f"Handled {handled} review(s). State updated.")
    else:
        print(f"DRY_RUN complete. Would have posted {len(new_reviews[:max_replies])} reply.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
