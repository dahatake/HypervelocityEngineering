# S005 ランク・ステータス確認画面

> **出典**: `docs/screen-list.md#S005`, `docs/app-list.md#APP-04`, `docs/data-model.md#LoyaltyAccount`, `docs/data-model.md#RankRule`  
> **作成日**: 2026-03-31

---

## 1. 概要

* **所属アプリケーション**: APP-04（顧客エンゲージメントポータル）
* **目的**: 現在のランク（BRONZE/SILVER/GOLD/PLATINUM）と次ランクまでの必要ポイントを表示する。ランク制度説明・有効期限も含む。
* **想定ユーザー**: 認証済み会員（顧客）
* **前提**: S003 の「ランクタブ」または直接アクセス。`RankRule` と `LoyaltyAccount` を参照。
* **対応 UC**: UC-03

---

## 2. 画面構成

### レイアウト概要

```
┌───────────────────────────────────────────┐
│  ナビゲーションバー（← ポータルへ戻る）           │
├───────────────────────────────────────────┤
│  現在ランクカード:                              │
│    [GOLD バッジアイコン]                        │
│    ランク: GOLD                                │
│    累計獲得ポイント: XXXX pt                    │
├───────────────────────────────────────────┤
│  昇格プログレスバー:                            │
│    GOLD → PLATINUM                            │
│    [========-------] XXXX / 30,000 pt         │
│    あと YYYY pt で PLATINUM                    │
├───────────────────────────────────────────┤
│  ランク有効期限:                                │
│    現ランク維持期限: YYYY-MM-DD               │
├───────────────────────────────────────────┤
│  ランク制度説明（アコーディオン）:                 │
│  ┌ BRONZE  : 0〜4,999 pt                      │
│  ├ SILVER  : 5,000〜14,999 pt                  │
│  ├ GOLD    : 15,000〜29,999 pt                 │
│  └ PLATINUM: 30,000 pt 以上                    │
│  ・特典別ランク特権の説明                          │
└───────────────────────────────────────────┘
```

### コンポーネント一覧

| コンポーネント | 種別 | 備考 |
|---|---|---|
| RankBadge | 表示 | ランク名・アイコン（色分け）|
| RankProgressBar | 表示 | 現在のポイント vs 次ランク閾値 |
| RankExpiryInfo | 表示 | ランク有効期限 |
| RankTierTable | 表示 | 全ランク・閾値一覧（アコーディオン）|
| RankBenefitsSection | 表示 | ランク別特典説明 |

---

## 3. ユーザーフロー / 状態

### 主要フロー

1. 画面アクセス → `GET /api/accounts/{memberId}/rank-status` でランク情報取得
2. ランクカード・プログレスバー・説明を表示

### 状態一覧

| 状態 | 説明 |
|---|---|
| 読み込み中 | スケルトン表示 |
| PLATINUM（最高ランク）| プログレスバーを「最高ランク達成！」メッセージで置換 |
| 通常表示 | 残りポイント・有効期限を表示 |
| エラー | 「ランク情報を取得できませんでした」 |

---

## 4. 入出力・データ

### 表示データ

| データ | 出典 |
|---|---|
| rank | `LoyaltyAccount.rank`（`docs/data-model.md#LoyaltyAccount`）|
| totalEarned | `LoyaltyAccount.totalEarned` |
| nextRankThreshold | `RankRule.threshold`（`docs/data-model.md#RankRule`）|
| rankExpiry | TBD（有効期限ロジック: ブロッカー#4）|
| rankTiers | `RankRule[]`（BRONZE/SILVER/GOLD/PLATINUM の閾値一覧）|

### API 連携

| 操作 | メソッド | エンドポイント | 備考 |
|---|---|---|---|
| ランクステータス取得 | GET | `/api/accounts/{memberId}/rank-status` | SVC-02 + SVC-03 |

---

## 5. バリデーション & エラーメッセージ

| ルール | エラーメッセージ |
|---|---|
| API エラー | 「ランク情報の取得に失敗しました。再度お試しください」 |
| 未ログイン | ログインページへリダイレクト |

---

## 6. A11y / i18n

* **キーボード操作**: Tab ナビゲーション。アコーディオンは Enter/Space で展開/折りたたみ。
* **フォーカス順**: 戻るリンク → RankBadge → RankProgressBar → RankExpiryInfo → RankTierTable アコーディオン
* **aria**: RankProgressBar に `role="progressbar"`, `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, `aria-label`. アコーディオンボタンに `aria-expanded`.
* **色以外の表現**: ランクは色＋アイコン＋テキスト名の3つで表現（色だけに依存しない）。
* **言語**: 日本語

---

## 7. セキュリティ / プライバシー

* **取り扱いデータ分類**: ポイント残高・ランク（非 PII）
* **認証**: 認証済みセッション必須。他会員データへのアクセス禁止。
* **ランク閾値の公開**: `RankRule` 閾値は全会員共通の公開情報（センシティブでない）。

---

## 8. 非機能要件

* **パフォーマンス**: ランクステータス取得 p95 < 500ms
* **ランク閾値キャッシュ**: `RankRule` は変更頻度低（運用時のみ変更）→ BFF でキャッシュ可（TTL: 1時間）

---

## 9. 受け入れ基準（テスト可能）

| # | Given | When | Then |
|---|---|---|---|
| AC-001 | GOLD ランクの会員がランク確認画面を開いた | 表示完了した | 現在ランク「GOLD」・累計ポイント・PLATINUMまでの残りポイントが表示される |
| AC-002 | PLATINUM ランクの会員が画面を開いた | 表示完了した | 「最高ランク達成！」メッセージが表示され、プログレスバーは非表示 |
| AC-003 | ランク制度説明アコーディオンを閉じた状態で | 「詳細を見る」を押した | 全ランクの閾値一覧が展開表示される |
| AC-004 | ランク取得 API が失敗した | 画面を開いた | 「ランク情報を取得できませんでした」エラーメッセージと再試行ボタンが表示される |

---

## 10. サンプルデータ（開発用・削除容易）

```json
{
  "rank": "GOLD",
  "totalEarned": 16500,
  "nextRankThreshold": 30000,
  "rankExpiry": "TODO:有効期限日（TBD）",
  "tiers": [
    { "name": "BRONZE", "threshold": 0 },
    { "name": "SILVER", "threshold": 5000 },
    { "name": "GOLD", "threshold": 15000 },
    { "name": "PLATINUM", "threshold": 30000 }
  ]
}
```
