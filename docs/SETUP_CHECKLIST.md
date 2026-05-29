# セットアップチェックリスト (ユーザー作業)

私 (Claude) が自走で構築完了した状態を引き継ぐためのチェックリスト。
各項目は5〜10分で終わる。

---

## 🟢 自動で動いているもの (確認のみでOK)

- [x] **レビュー収集パイプライン** — 日次 09:00 JST に楽天から両商品レビュー取得
- [x] **Claude による分類・要約・中国語訳** — `categorize-reviews.py` が JP/ZH 要約と対策案を生成
- [x] **商品別サイト公開 (J001/J002 を分離)**
  - SH-J001: <https://quality.glowup-inc.com/sh-j001/>
  - SH-J002: <https://quality.glowup-inc.com/sh-j002/>
  - 管理者ランディング (商品選択): <https://quality.glowup-inc.com/>
- [x] **defects 用 private リポ 2 つ作成** — `shojiki-defects-j001` / `shojiki-defects-j002`
- [x] **Issue Template (中日バイリンガル)** + **26 ラベル** 配置済み
- [x] **不具合報告フォーム** (各サイト内) — <https://.../sh-j001/defects.html> / <https://.../sh-j002/defects.html>
- [x] **不具合トラッカー画面** (各サイト内) — `j001/defects-dashboard.html` / `j002/defects-dashboard.html`
- [x] **CSV エクスポート** — ダッシュボード右上「⬇ CSV」ボタン
- [x] **月別トレンドチャート** — 不具合+改善要望の推移
- [x] **レビュー → Issue 起票ボタン** — 各レビューカードの「📋 Issue化」

---

## 🟡 ユーザー作業必要 (優先度順)

### ★★★ 必須: 工場メンバーを招待する

1. 工場メンバーから GitHub ユーザー名を集める
   - 中国語ガイドを送付: <https://quality.glowup-inc.com/FACTORY_REPORT_GUIDE_ZH.md>
2. 各 defect リポの **Settings → Collaborators**:
   - <https://github.com/eda0825-spec/shojiki-defects-j001/settings/access>
   - <https://github.com/eda0825-spec/shojiki-defects-j002/settings/access>
3. 「Add people」で各工場メンバーを **Write** 権限で招待
4. 日本側エンジニア (自分以外) も両方に招待

### ★★ 推奨: DEFECTS_SYNC_PAT を発行 (集約ビュー + 自動 Issue 化)

1. <https://github.com/settings/tokens> → Generate new token (classic)
   - Note: `shojiki-defects-sync`
   - Expiration: No expiration (or 1年)
   - Scopes: `repo` (Full control of private repositories)
2. <https://github.com/eda0825-spec/shojiki-rakuten-stats/settings/secrets/actions>
   - New repository secret
   - Name: `DEFECTS_SYNC_PAT`
   - Secret: 上の PAT
3. 動作確認:
   ```bash
   # 集約ダッシュボードに Issue 一覧が出るか
   gh workflow run sync-defects.yml -R eda0825-spec/shojiki-rakuten-stats
   # 顧客レビューの defect+high が Issue 化されるか (dry run)
   gh workflow run bridge-defects.yml -R eda0825-spec/shojiki-rakuten-stats -f dry_run=true -f max_per_run=5
   ```

### ★ 任意: Amazon レビュー取り込み

1. Seller Central → ブランド分析 → カスタマーレビュー で CSV ダウンロード
2. ローカルで:
   ```bash
   cd ~/shojiki-rakuten-stats
   python3 ingest-amazon-csv.py --product sh-j001 --csv ~/Downloads/amazon-j001.csv
   git add reviews-sh-j001.json && git commit -m "amazon: J001 reviews" && git push
   gh workflow run update-reviews.yml -f categorize_only=true
   ```

### ★ 任意: Lark Base 移行 (将来 SaaS 化したい時)

`docs/LARK_BASE_SCHEMA.md` の手順で Lark Base 3 つ作成 →
Secrets に `LARK_APP_ID` / `LARK_APP_SECRET` / `LARK_VOC_APP_TOKEN` / `LARK_VOC_TABLE_ID`
を追加 → `lark-push-voc.py` がレビュー自動 POST。

---

## 動作確認シナリオ (10分)

### A. 既存レビューが見える?
1. <https://quality.glowup-inc.com/sh-j001/> を開く (J001 専用サイト)
2. 「不具合」フィルタを押す → 故障報告レビューだけ表示される
3. 「📋 Issue化」を押す → GitHub に prefill 状態の Issue 作成画面が開く
4. J002 は <https://quality.glowup-inc.com/sh-j002/> で同様

### B. 工場側から見える?
1. 工場メンバーに <https://quality.glowup-inc.com/FACTORY_REPORT_GUIDE_ZH.md> を送付
2. メンバーが GitHub アカウント作成 + コラボレーター招待を受諾
3. J001 工場 → `j001/defects.html`、J002 工場 → `j002/defects.html` から実際に1件報告
4. <https://github.com/eda0825-spec/shojiki-defects-j001/issues> に Issue が立つことを確認
5. コメントで返信 → 工場側に通知が届くことを確認

### C. 動画ありの不具合報告?
1. 工場が 10MB 以下の動画を Issue にドラッグ → 動画が再生できることを確認
2. > 10MB の動画は WeTransfer → URL を フォーム/コメントに貼る → ダウンロードして再生確認

---

## トラブル時

| 症状 | 対処 |
|---|---|
| 中国からダッシュボードが開けない | jsdelivr/raw.gh の両方を試している。社内 VPN 案内 |
| GitHub Mobile が中国で使えない | 公式 APK 直配布: <https://github.com/mobile> |
| 動画が10MB超で投稿できない | WeTransfer/Mega/微云 のURL投稿に誘導 |
| Issue 数が多すぎる | Bridge の `min_severity=high` を `medium` に上げて拾う数を増やす逆も可 |
| Claude API のコスト気になる | Sonnet → Haiku に切替 (環境変数 `ANTHROPIC_MODEL=claude-haiku-4-6`) |
