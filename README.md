# shojiki-rakuten-stats

楽天市場 SHOJIKI ストアの SH-J001 商品レビュー件数・平均評価を、毎日自動取得して JSON で公開するためのリポジトリ。

LP 側はこの JSON を fetch して数値を表示する。

## 仕組み

- GitHub Actions が毎日 09:00 JST(UTC 00:00)に `update-rakuten-stats.py` を実行
- 楽天 OpenAPI(`openapi.rakuten.co.jp`)から `reviewAverage` / `reviewCount` を取得
- 結果を `rakuten-stats.json` に保存
- 数値が前日と異なる場合のみ自動コミット & push

## JSON の URL

```
https://raw.githubusercontent.com/eda0825-spec/shojiki-rakuten-stats/main/rakuten-stats.json
```

## 必要な GitHub Secrets

| Name | 取得元 |
|---|---|
| `RAKUTEN_APP_ID` | 楽天 Developers ダッシュボードの「アプリケーションID」(UUID) |
| `RAKUTEN_ACCESS_KEY` | 同「アクセスキー」(`pk_` 始まり) |

## ローカル動作確認

```bash
RAKUTEN_APP_ID=... RAKUTEN_ACCESS_KEY=... python3 update-rakuten-stats.py
```

## レビュー本文の収集と分析

`analyze-rakuten-reviews.py` は `review.rakuten.co.jp` から全ページのレビュー本文を取得し、以下を出力する。

- `rakuten-reviews.json` — 取得した全レビュー(星, 日付, タイトル, 本文, 年代/性別)
- `rakuten-reviews-analysis.json` — 件数 / 平均 / 星分布 / 月別件数 / 年代・性別分布 / 頻出語(全体・高評価・低評価) / 各星の代表レビュー

GitHub Actions(`.github/workflows/analyze-rakuten-reviews.yml`)が毎週月曜 09:30 JST に自動実行し、差分があれば自動コミットする。手動実行(`workflow_dispatch`)で対象商品パスを切り替え可能。

ローカル実行:

```bash
REVIEW_ITEM_PATH=437323_10000000 python3 analyze-rakuten-reviews.py
```

---

# Judge.me レビュー自動返信

Shopify ストア (Judge.me) に新着レビューが入ったら、Claude API で生成した **プライベート返信** (= 投稿者へメールで届く返信。ウィジェット上には表示されない) を 15 分以内に自動投稿する仕組み。

## 仕組み

- GitHub Actions が 15 分おきに `judgeme-auto-reply.py` を実行
- Judge.me API (`GET /api/v1/reviews`) で最新 100 件を取得
- `judgeme-processed.json` で処理済 ID を除外
- 未処理レビューごとに Claude API (`claude-sonnet-4-6`) で SHOJIKI トーンの返信文を生成
- Judge.me API (`POST /api/v1/private_replies`) で投稿
- 1 件でも処理したら `judgeme-processed.json` を自動コミット

## 必要な GitHub Secrets

| Name | 取得元 |
|---|---|
| `JUDGE_ME_API_TOKEN` | Judge.me 管理画面 → Settings → API → Private Token |
| `JUDGE_ME_SHOP_DOMAIN` | `xxx.myshopify.com` 形式 |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com で発行 |

## 重要な前提

- Judge.me 公開 API には **Private Replies のみ**実装あり。「公開返信 (ウィジェット上に表示される Store reply)」を投稿する API は存在しない。
- 本仕組みの返信は **投稿者のメール宛にのみ届く**。ウィジェット上の星の下には何も表示されない。
- 公開返信が必要な場合は別途 Phase 2 (Playwright で管理画面操作) として実装する。

## 初回検証フロー

1. `workflow_dispatch` から `dry_run=true` で実行 → 生成本文をログで確認
2. 自分のメアドで Judge.me にテストレビュー投稿 → 15 分待ち → 返信メール受信を確認
3. Judge.me 管理画面で該当レビューに "Private Reply" フラグがつくこと確認
4. 同じレビュー ID で再実行しても重複 POST されないこと確認 (冪等性)

## ローカル動作確認

```bash
JUDGE_ME_API_TOKEN=... \
JUDGE_ME_SHOP_DOMAIN=xxx.myshopify.com \
ANTHROPIC_API_KEY=sk-ant-... \
DRY_RUN=true \
python3 judgeme-auto-reply.py
```
