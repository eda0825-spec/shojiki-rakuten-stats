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
