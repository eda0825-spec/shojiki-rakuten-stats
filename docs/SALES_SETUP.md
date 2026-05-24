# 販売台数トラッキング セットアップ

3 プラットフォーム (Shopify / 楽天 RMS / Amazon SP-API) から日次で販売数を集計し、
ダッシュボード上部に「今日 / 今月 / 先月 / 累計」を表示する仕組み。

毎日 07:30 JST に自動実行 → `sales-summary.json` に集計 → 各 sh-j00x サイトで自動表示。

設定したプラットフォームだけが動作 (未設定はダッシュボードでグレー表示)。

---

## 1. Shopify (推奨 — 設定 5 分)

### 手順
1. Shopify Admin → **Settings → Apps and sales channels → Develop apps**
2. **Create an app** → 名前: `shojiki-sales-tracker`
3. **Configure Admin API scopes** → `read_orders` だけ ON
4. **Install app** → API credentials → **Admin API access token** をコピー

### GitHub Secrets / Variables 設定
[Secrets and Variables → Actions](https://github.com/eda0825-spec/shojiki-rakuten-stats/settings/secrets/actions)

| 種類 | Name | 値 |
|---|---|---|
| Secret | `SHOPIFY_SHOP_DOMAIN`  | `shojiki-store.myshopify.com` (myshopify.com 込) |
| Secret | `SHOPIFY_ADMIN_TOKEN`  | `shpat_xxxxxxxxxxxx` |
| Variable | `SHOPIFY_J001_SKUS` | `sh-j001` (カンマ区切りで複数可。SKU の部分一致) |
| Variable | `SHOPIFY_J002_SKUS` | `sh-j002` |

### 動作確認
```bash
gh workflow run update-sales.yml -R eda0825-spec/shojiki-rakuten-stats
```
ダッシュボード sh-j001/ にアクセスして黒い「販売台数」widget が出れば OK。

---

## 2. 楽天 RMS (中) — 設定 30 分

> ⚠️ 既存の `RAKUTEN_APP_ID` (Ichiba Item Search 用) と **別物**。
> RMS WEB API SERVICE のキーが必要。

### 手順
1. [RMS](https://glogin.rms.rakuten.co.jp/) → 拡張サービス → **WEB API SERVICE**
2. 申込 → 数日後にライセンスキー発行
3. ライセンスキーから `serviceSecret` と `licenseKey` をメモ

### GitHub Secrets / Variables 設定
| 種類 | Name | 値 |
|---|---|---|
| Secret | `RAKUTEN_RMS_LICENSE_KEY`    | `SP123xxxxxxxxxxxx` |
| Secret | `RAKUTEN_RMS_SERVICE_SECRET` | `SK123xxxxxxxxxxxx` |
| Variable | `RAKUTEN_J001_ITEM_CODE` | `shojiki-official:10000000` |
| Variable | `RAKUTEN_J002_ITEM_CODE` | `shojiki-official:10000004` |

### 注意
- searchOrder API は **直近 31 日まで** 一度に取得可能
- 履歴 (sales-summary.json byMonth) は累積保持されるので問題なし

---

## 3. Amazon SP-API (重) — 設定 1〜2 時間

### 手順 (Seller Central)
1. **Apps & Services → Develop Apps → Add new app**
   - LWA Application name: `shojiki-sales-tracker`
   - Roles 不要 (Orders は public)
2. **LWA credentials** から `client_id` / `client_secret` をメモ
3. **Authorize** で 自分のセラーアカウント連携 → `refresh_token` 発行

### Variables (商品 ASIN)
| 種類 | Name | 値 |
|---|---|---|
| Variable | `AMAZON_J001_ASIN` | `B0XXXXXXX` (Seller Central の商品詳細ページ) |
| Variable | `AMAZON_J002_ASIN` | `B0YYYYYYY` |
| Variable | `AMAZON_MARKETPLACE_ID` | `A1VC38T7YXB528` (日本) |

### Secrets
| Name | 値 |
|---|---|
| `AMAZON_SP_REFRESH_TOKEN` | `Atzr|...` |
| `AMAZON_SP_CLIENT_ID`     | `amzn1.application-oa2-client.xxx` |
| `AMAZON_SP_CLIENT_SECRET` | `amzn1.oa2-cs.v1.xxx` |

---

## ダッシュボードでの見え方

### 全プラットフォーム未設定 → widget 非表示

### 1つでも設定済 → 黒い widget が出現
```
┌──────────────────────────────────────┐
│ 📦 販売台数        更新: 2026/05/24 07:30│
│                                          │
│    5      87      120     1,932          │
│  今日   今月    先月    累計             │
│                                          │
│ 楽天 今日 3・今月 60   Amazon 今日 2・今月 25   Shopify 未設定 │
└──────────────────────────────────────┘
```
未設定プラットフォームはグレーで「未設定」表示。

---

## トラブル時

| 症状 | 対処 |
|---|---|
| widget が出ない | `sales-summary.json` が存在するか確認: `curl -s https://raw.githubusercontent.com/eda0825-spec/shojiki-rakuten-stats/main/sales-summary.json` |
| 数字が 0 のまま | workflow ログで `error` 確認: `gh run view --log -R eda0825-spec/shojiki-rakuten-stats` |
| Shopify HTTP 401 | Admin token 期限切れ / scope 不足 |
| 楽天 RMS HTTP 401 | licenseKey 期限切れ (有効期限あり) |
| Amazon HTTP 403 | refresh_token 失効 (180日無使用で失効) |

---

## コスト

GitHub Actions 無料枠 2000 分/月 のうち、この workflow は ~1 分/日 × 30 = **30 分/月** だけ消費。
レビュー fetch (300 分/月) と合わせても全然余裕。
