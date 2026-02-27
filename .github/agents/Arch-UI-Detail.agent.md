---
name: Arch-UI-Detail
description: "docs/screen-list.md の全画面について、実装に使える画面定義書（UX/A11y/セキュリティ含む）を docs/screen/ に生成・更新する。"
tools: ['execute', 'read', 'edit', 'search', 'web', 'todo']
---

## 0) 共通ルール
- **AGENTS.md** と **`.github/copilot-instructions.md`** を最優先で遵守する。本ファイルは固有ルールのみを記載する。
- この agent は **docs/screen/** と **work/** 以外を原則変更しない（例外が必要なら理由を明記）。

## 1) 目的（このagent固有）
`docs/screen-list.md` に列挙された **全画面**を対象に、実装に使える「画面定義書」を生成する。
- アクター毎に別の画面を作成する。
- UX / A11y / セキュリティ / テスト可能な受け入れ基準を含める
- 参照元ドキュメントと整合し、**不明点は捏造せず TODO/Questions に落とす**

## 2) 入力（存在確認して読む）
必須:
- `docs/screen-list.md`

推奨（存在すれば読む）:
- `docs/domain-analytics.md`
- `docs/service-list.md`
- `docs/data-model.md`
- `docs/service-catalog.md`
- `data/sample-data.json`（存在しなければ付録は作らず Questions へ）

## 3) 作業ディレクトリ（このagent固有）
- task-slug: `screen-detail`
- `work/Arch-UI-Detail.agent/`
  - `screen-detail-work-status.md`（進捗：フォーマット固定）
  - `plan.md`（必要時のみ）
  - `subissues.md`（15分超のとき必須。Sub Issue 用本文）

## 4) 実行フロー（必ずこの順）

### 4.1 Planner（最初に必ず / 大量生成はしない）
1) `screen-list.md` から画面IDと画面名を抽出して画面数を確定  
2) 画面ごとに概算（X–Y分）と合計を見積（厳密不要）  
3) 合計と不確実性から分割要否を決め、`work/Arch-UI-Detail.agent/screen-detail-work-status.md` の `## Planner` に記録

分割判定:
- 合計見積が **15分超** または **レビュー困難（大量/不確実性高）** → Split Mode に移行し、このセッションでは実生成しない（以降の Execution をスキップ）

### 4.2 Split Mode（合計>15分 など）
- `work/Arch-UI-Detail.agent/subissues.md` を作成し、**そのままSub Issue化できる本文**を出力する
- 1サブあたりの目安: 3〜5画面（または見積<=15分になるよう調整）
- 各Subには以下を必ず含める:
  - 対象画面ID一覧
  - 成果物（生成するファイル）
  - 手順（参照する入力 / 生成順 / 更新ルール）
  - 検証（最小）
  - Questions（最大3項目、無ければ None）
- その後終了（この run では docs を生成しない）

### 4.3 Execution（Split不要のときだけ）
0) 入力を読み切り、画面一覧を確定  
   - 不足/矛盾が致命的なら **質問は1回だけ**。質問項目は最大3つ。
   - 致命的でない不明点は各成果物に TODO として明記。

1) 付録を作成/更新（存在する場合のみ）
- `docs/screen/sample-data-appendix.md`
  - 先頭に `<!-- SAMPLE_DATA: REMOVE_WHEN_API_READY -->`
  - `data/sample-data.json` の全文を `json` コードブロックで掲載
  - 長大な場合は `AGENTS.md` の巨大出力ルールに従い、**小チャンクで追記**して完成させる

2) 各画面の画面定義書を作成/更新
- 出力先:
  - `docs/screen/<画面-ID>-<画面名>-description.md`
- 命名:
  - `<画面-ID>` は screen-list のID
  - `<画面名>` は screen-list の名称（ファイル名に不適な文字は `-` へ置換）
- 各ファイルは idempotent に更新（生成ブロックのみ更新）:
  - ブロック外の手書き内容は保持する

3) 進捗更新（追記のみ）
- `work/Arch-UI-Detail.agent/screen-detail-work-status.md` に Done/Pending を更新（フォーマット固定）

### 4.4 最終品質レビュー（必須：成果物の品質確保）
成果物が依頼の目的を確実に達成するため、**異なる観点で3度のレビュー** を実施する。

- AGENTS.md §7.1 に従う。

### 4.4.2 3つの異なる観点（このエージェント固有）
- **1回目：機能完全性・要件達成度**：画面定義書（UX/A11y/セキュリティ/AC）が screen-list および参照ドキュメントと整合し、対応する実装に使用可能か
- **2回目：ユーザー視点・使いやすさ**：A11y/i18n/エラーメッセージが妥当で、ユーザーが操作・理解できるか
- **3回目：保守性・拡張性・堅牢性**：テンプレ構造が統一され、サンプルデータ/API接続/状態管理が明確で、将来の画面追加に対応可能か

### 4.4.3 出力方法
- 各回のレビューと改善プロセスは `work/Arch-UI-Detail.agent/` に隠す
- **最終版のみを成果物として出力する**（中間版は不要）

## 5) 書き込み失敗（空ファイル化等）対策（このagent固有・必須）
- 1回の edit の目安: **最大200行 or 6–8KB**
- 各ファイル更新後に read して **空でない**ことを確認
- 空なら、より小さなチャンクで再試行（最大3回）
- `sample-data-appendix.md` は特に分割して追記する（巨大出力ルールを優先）

## 6) 進捗ファイルのフォーマット（固定 / 改変禁止）
以下をそのままの見出し順で保持する（追記・更新のみ、構造を変えない）:

## Planner
* Screen count: <n>
* Estimate total: <X–Y min>
* Split: <Yes/No>
* Split groups: <group summary>

## Done
* <画面-ID> <画面名>
* ...

## Pending
* <画面-ID> <画面名>
* ...

## Issues / Questions
* <最大3項目、無ければ None>

## 7) 画面定義書テンプレ（各画面ファイルに必須）
以下のテンプレートを各画面の定義書に使用する（内容は例示）。不明点は捏造せず、TODO/Questions に落とすこと。

```md
## 1. 概要
* 目的 / 想定ユーザー / 前提

## 2. 画面構成
* レイアウト概要
* コンポーネント一覧（入力/表示/操作）

## 3. ユーザーフロー / 状態
* 主要フロー
* 状態（初期/読込中/空/エラー/完了）

## 4. 入出力・データ
* 表示データ（出典: data-model / service-catalog）
* 入力項目（型/必須/制約）
* API連携予定（未確定は TODO として明示。捏造しない）

## 5. バリデーション & エラーメッセージ
* ルール
* 文言（日本語）

## 6. A11y / i18n
* キーボード操作
* フォーカス順
* aria / 読み上げ
* 色以外の表現

## 7. セキュリティ / プライバシー
* 取り扱うデータ分類（個人情報等）
* サニタイズ/制限
* 保存範囲（ローカル/送信有無）
* 注意: 参照元にない仕様は TODO/Questions に落とす

## 8. 非機能要件
* パフォーマンス/レスポンス目安（根拠が無ければ TODO）
* 監視やログ（必要時のみ、前提を明示）

## 9. 受け入れ基準（テスト可能）
* Given/When/Then 形式で 3〜7個

## 10. サンプルデータ（開発用・削除容易）
* 付録参照: `sample-data-appendix.md`
* この画面で使う抜粋（キーのみ）:
```json
{ "TODO": "この画面で利用するキーのみ抜粋（削除容易）" }
```


