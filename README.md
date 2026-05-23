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

## 工場×日本エンジニア共有ダッシュボード (NEW)

中国工場と日本エンジニアがレビュー由来の不具合・改善要望を共有するための
パイプライン。`docs/` 配下のダッシュボードで両商品を切り替えて閲覧できる。

### データフロー

```
[毎日 09:00 JST]
  1) fetch-reviews.py      楽天レビュー全件取得 (J001/J002 両方、増分のみ)
        ↓
        reviews-sh-j001.json / reviews-sh-j002.json
  2) categorize-reviews.py Claude API で分類+JP要約+ZH翻訳+対策案
        ↓
        categorized-sh-j001.json / categorized-sh-j002.json
  3) docs/index.html       両 JSON を fetch、商品タブ/分類/星でフィルタ可能
```

GitHub Actions: `.github/workflows/update-reviews.yml` が日次で 1→2→commit。
docs は GitHub Pages から `https://eda0825-spec.github.io/shojiki-rakuten-stats/` で公開。

### Amazon レビュー取り込み

`ingest-amazon-csv.py` で Seller Central からダウンロードした CSV を
楽天と同じ JSON 形式にマージする (Amazon SP-API がレビュー本文 API を
提供していないため半自動)。

```bash
python3 ingest-amazon-csv.py --product sh-j001 --csv ./amazon-j001-may.csv
python3 categorize-reviews.py     # マージ後に再分類すると Amazon 分も付く
```

### 不具合トラッカー (GitHub Issues ベース)

工場 ↔ 日本エンジニアの不具合共有を、以下の構成で実装:

- 投稿フォーム: <https://eda0825-spec.github.io/shojiki-rakuten-stats/defects.html>
- 集約ダッシュボード: <https://eda0825-spec.github.io/shojiki-rakuten-stats/defects-dashboard.html>
- 不具合用 private リポ (Issue Template + 26ラベル配置済):
  - <https://github.com/eda0825-spec/shojiki-defects-j001>
  - <https://github.com/eda0825-spec/shojiki-defects-j002>

ガイド:
- 工場向け (中文): <docs/FACTORY_REPORT_GUIDE_ZH.md>
- エンジニア向け (日本語): <docs/ENGINEER_GUIDE_JA.md>

#### Bridge: 顧客レビューの深刻な不具合を自動 Issue 化

`bridge-review-to-defect.py` が `categorized-*.json` から `defect+severity=high`
を抽出して shojiki-defects-{j001|j002} に Issue を起票。日次自動実行 (`.github/workflows/bridge-defects.yml`)。

```bash
# ローカルで動作確認 (DRY RUN)
BRIDGE_DRY_RUN=1 DEFECTS_SYNC_PAT=ghp_... python3 bridge-review-to-defect.py
```

#### 集約ダッシュボード用の sync

private リポの Issue を JSON に同期して公開ダッシュボードに表示:
- `sync-defects.py` + `.github/workflows/sync-defects.yml`
- 必要 Secret: `DEFECTS_SYNC_PAT` (bridge と共用)

### Lark Base 連携 (将来オプション)

`docs/LARK_BASE_SCHEMA.md` に Lark Base 3 ベース (J001 工場 / J002 工場 / VOC) の
列定義。Base 作成後に下記 Secrets を追加すると `lark-push-voc.py` で
カテゴリ済みレビューを自動 POST できる。

```
LARK_APP_ID
LARK_APP_SECRET
LARK_VOC_APP_TOKEN
LARK_VOC_TABLE_ID
```

### 追加 GitHub Secrets

| Name | 用途 |
|---|---|
| `ANTHROPIC_API_KEY` | categorize-reviews.py の分類/翻訳 (既存) |
| `DEFECTS_SYNC_PAT` (任意) | bridge-review-to-defect.py + sync-defects.py — PAT (Classic) `repo` scope |

### ローカル動作確認

```bash
# 楽天レビュー取得 (両商品)
python3 fetch-reviews.py

# 1商品だけ
REVIEW_ONLY_PRODUCT=sh-j002 python3 fetch-reviews.py

# Claude で分類 (要 ANTHROPIC_API_KEY)
ANTHROPIC_API_KEY=sk-ant-... python3 categorize-reviews.py
```

---

## (旧) レビュー本文の収集と分析

`analyze-rakuten-reviews.py` は古い HTML regex ベースの J001 専用スクリプト。
`fetch-reviews.py` (新) に置き換え済み。残してあるのは後方互換のため、ワークフロー
(`analyze-rakuten-reviews.yml`) のスケジュールは無効化済み。

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
