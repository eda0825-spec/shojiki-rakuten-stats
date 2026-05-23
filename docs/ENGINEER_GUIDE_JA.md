# SHOJIKI 不具合トラッカー - エンジニア用ガイド

> 日本側エンジニア・QA・カスタマーサポート向け。

## 構成

```
中国工場 (J001)  ─報告→  shojiki-defects-j001 (private)
中国工場 (J002)  ─報告→  shojiki-defects-j002 (private)
                              │
                              │ 日次 sync
                              ▼
                  docs/data/defects-*.json (public)
                              │
                              ▼
                  defects-dashboard.html (集約閲覧)
```

## 初期セットアップ (1回だけ)

### 1. 工場メンバーを招待

各 private リポの **Settings → Collaborators** で:

- `shojiki-defects-j001` → J001 工場の GitHub アカウントを招待 (Write 権限)
- `shojiki-defects-j002` → J002 工場の GitHub アカウントを招待 (Write 権限)
- 日本側エンジニアは両方に招待 (Admin or Write)

### 2. 集約ダッシュボードを有効化 (任意)

private リポを直接見せたくない / 共有 URL だけで閲覧したい人向け。

1. https://github.com/settings/tokens で Personal Access Token (Classic) を発行
   - スコープ: `repo` (Full control of private repositories) のみ
2. `shojiki-rakuten-stats` リポの Settings → Secrets → Actions に追加
   - Name: `DEFECTS_SYNC_PAT`
   - Value: 上で発行した PAT
3. 翌日 09:15 JST に `sync-defects.yml` ワークフローが走り、`docs/data/defects-*.json` が生成される
4. defects-dashboard.html に「最近の活動」セクションが自動で出現

手動で今すぐ走らせたい場合: `gh workflow run sync-defects.yml -R eda0825-spec/shojiki-rakuten-stats`

## 日常運用

### 新規 Issue が届いたら

1. メール/モバイル通知で気づく (GitHub の通知設定で「Watching」にしておく)
2. Issue を開いて症状を確認
3. ラベルを正しく設定 (テンプレが `status:new` を付けるが、後で更新):
   - `severity:high|medium|low` (報告内容を読んで判断)
   - `area:battery|motor|...` (テンプレに記載があれば反映)
   - `source:factory|customer|support|internal`
   - `freq:single|sporadic|frequent|all`
4. 担当者 (Assignee) を割り振る
5. ラベル `status:investigating` に変更

### 調査・対策

- コメントで工場と双方向にやり取り
- 中国側にも分かるよう、日本語 + (できれば) 中国語で書く
- 動画 URL がある場合は内容を確認、見れなければ工場に再アップを依頼
- 不具合再現に成功したら写真/動画を添付して状況共有

### 解決時

1. 対策内容をコメントで明記 (再発防止策含む)
2. ラベル `status:resolved` に変更
3. Issue を Close

### 月次レビュー

- `area:` ラベルで集計して頻発エリアを把握
- `severity:high` の Close まで時間を見る
- LP / 商品改良の優先度判断材料に使う

## ラベル運用ルール

| プレフィックス | 必須 | 補足 |
|---|---|---|
| `status:` | ✅ 必ず1つ | テンプレが自動で `:new` を付ける |
| `severity:` | ✅ できれば1つ | エンジニアが判定 |
| `area:` | ✅ 1つ以上 | テンプレの部位選択を反映 |
| `source:` | ✅ 1つ | テンプレの報告元を反映 |
| `freq:` | (任意) | わかれば付ける |

## CLI で便利な操作

```bash
# 全 J001 open issue を一覧
gh issue list -R eda0825-spec/shojiki-defects-j001 --state open

# severity:high だけ
gh issue list -R eda0825-spec/shojiki-defects-j001 --label severity:high

# 自分にアサインされた両方
gh issue list -R eda0825-spec/shojiki-defects-j001 --assignee @me
gh issue list -R eda0825-spec/shojiki-defects-j002 --assignee @me

# Close 時にコメント残してラベル更新
gh issue close 12 -R eda0825-spec/shojiki-defects-j001 -c "対策: ロット2026-W20以降のバッテリー組立工程変更で再現せず" && \
gh issue edit 12 -R eda0825-spec/shojiki-defects-j001 --add-label "status:resolved" --remove-label "status:investigating"
```

## モバイル

GitHub Mobile (iOS / Android) で:
- 通知をプッシュ受信
- Issue のコメント返信
- ラベル/担当者変更
- 写真添付 (アプリから直接)

## 動画について

GitHub の Issue 本文への動画ドラッグは **10MB まで**。それ以上の動画は
工場側に WeTransfer / Mega / 微云 等の URL を貼ってもらう運用。

将来 Vercel + Cloudinary で大容量動画をフォーム経由でアップ可能にする予定
(別途実装、本ドキュメント外)。

## 関連

- 管理者ランディング (商品選択): <https://eda0825-spec.github.io/shojiki-rakuten-stats/>
- SH-J001 サイト: <https://eda0825-spec.github.io/shojiki-rakuten-stats/sh-j001/>
- SH-J002 サイト: <https://eda0825-spec.github.io/shojiki-rakuten-stats/sh-j002/>
- 工場用ガイド: <./FACTORY_REPORT_GUIDE_ZH.md>
