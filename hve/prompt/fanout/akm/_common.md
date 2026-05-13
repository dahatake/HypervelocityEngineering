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

1. `knowledge/{{key}}-*.md` を **要求項目（REQ）テーブル形式** で最新の根拠で更新（または新規作成）
   - §2 = Confirmed REQ（`REQ-{{key}}-001` 番台、各 REQ は独立サブセクション + テーブル）
   - §3 = Tentative REQ（`REQ-{{key}}-101` 番台、`推論根拠`・`要確認アクション` 行必須）
   - §4 = Unknown 表（従来形式維持）
   - §5-§7 = REQ 単位カバー率・件数
   - 散文の箇条書きや QA 回答セルの貼り付けは禁止（Skill `knowledge-management` references/knowledge-management-guide.md §7 / §11.6 準拠）
2. `knowledge/{{key}}-*-ChangeLog.md` を **REQ-ID 別サブセクション構造** で更新
   - 冒頭メタブロック（sources / generated_at / generator）
   - 全体更新履歴（生成イベント 1 行追記）
   - 要求項目別ログ（各 `REQ-{{key}}-XXX` サブセクションに `新規/マージ/値更新/状態降格` を日付昇順で追記）
   - 付録 A（マッピング元入力の原文保存、`統合先 REQ-ID` 列必須）

## 同類項目マージ要件（厳守）

- §11.6 マージ判定（AND 条件）: 主題キーワード一致 + 採用値一致 + 状態一致 → 1 REQ にマージ
- マージした場合は `根拠（Source of Truth）` 行に全出典をセミコロン区切りで列挙
- ChangeLog の該当 REQ-ID サブセクションへ各出典を 1 行ずつ記録（最初=新規、以降=マージ）

## 検証

- マスターリストの「不足判定」条件を満たしているか自己点検
- 捏造禁止: 根拠不明な事実は `TBD（推論: ...）` と明記
- 各 REQ テーブルの必須行（要求ID/要求名/分類/優先度/状態/要求内容/根拠）が欠落していないか確認

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
