# AKM Fan-out per-D{{key}} 追加指示

このサブタスクは AKM ワークフロー Step 1 の fan-out 子ステップであり、
**ドキュメント `{{key}}` のみ** を対象とする。他の D## ファイルは触らない。

## 対象ファイル

- 本体: `knowledge/{{key}}-*.md`（既存ファイル名は `template/business-requirement-document-master-list.md` の {{key}} 節を参照）
- ChangeLog: `knowledge/{{key}}-*-ChangeLog.md`（本体と同時更新）

## 必須参照

1. **`template/business-requirement-document-master-list.md`** の `{{key}}.` セクションを必ず最初に読み、当該文書の「必須度 / 目的 / 最低内容 / 不足判定」を確認する。
2. `original-docs/` 配下の関連資料を読み取り専用で参照する（変更・削除禁止 — `.github/copilot-instructions.md` §0）。
3. `qa/` 配下の既存質問票・回答（あれば）。

## 並列実行ルール（厳守）

- 他の D## ファイルへの書き込みは禁止（並列実行中の競合回避のため）。
- `knowledge/{{key}}-*.md` は work-artifacts-layout §4.1 準拠で「削除 → 新規作成」する。
- LOCK 情報を `knowledge/` 本体に埋め込まない（§0）。

## 成果物

1. `knowledge/{{key}}-*.md` を最新の根拠で更新（または新規作成）
2. `knowledge/{{key}}-*-ChangeLog.md` を更新（差分理由を 1〜3 行）

## 検証

- マスターリストの「不足判定」条件を満たしているか自己点検
- 捏造禁止: 根拠不明な事実は `TBD（推論: ...）` と明記

## 出力フォーマット

完了時、以下を必ず PR description / コメントに記載:

```
status: success | partial | failed
summary: {{key}} の更新内容を 1-2 行
next_actions: 横断レビュー Step 2 で確認すべき観点（存在すれば）
artifacts:
  - knowledge/{{key}}-*.md
  - knowledge/{{key}}-*-ChangeLog.md
```
