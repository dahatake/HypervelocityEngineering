---
name: agent-common-preamble
description: >
  全 Custom Agent が作業開始時に参照する共通プリアンブル。 USE FOR: agent start, common rules, preamble. DO NOT USE FOR: implementation. WHEN: Custom Agent が作業を開始したとき、共通ルールを確認したいとき。
metadata:
  origin: user
  version: 1.0.0
---

# agent-common-preamble

## 共通ルール

`.github/copilot-instructions.md` §0 を最優先で遵守する。本 Skill は全 Agent 共通の参照先を集約する。

## 出力言語ルール（思考プロセスを含む）

- 最終出力だけでなく **思考プロセス（reasoning / chain-of-thought / 内部独白）も日本語で行う** こと。
- ツール委譲の意図表明（例: "I need to delegate this task to ..."）、計画の自問自答、推論の途中経過もすべて日本語で記述する。
- 英語の固有名詞・コマンド名・ファイルパス・コード識別子・引用文はそのまま英語で構わない。
- 本ルールは hve オーケストレーターのターミナル出力（`○` で始まる Thinking 行）にも適用される。

## 全 Agent 共通 Skills 参照リスト

- `task-questionnaire`：コンテキスト収集・質問票作成の詳細手順
- `task-dag-planning`：DAG計画・見積・分割判定の詳細手順
- `work-artifacts-layout`：work/ 構造設計・README入口
- `large-output-chunking`：巨大出力の分割手順
- `adversarial-review`：敵対的レビューの詳細手順
- `harness-verification-loop`：コード変更の5段階検証パイプライン
- `harness-safety-guard`：破壊的操作の事前検知
- `harness-error-recovery`：エラー発生時の3要素出力
- `docs-output-format`：`docs/` 成果物フォーマットの共通原則
- `knowledge-management`：knowledge/ の分類・状態判定・更新手順
- `knowledge-lookup`：タスク実行中に業務要件が不明瞭な場合の knowledge/ 条件付き参照ルール

## 分割ルール

→ Skill `task-dag-planning` を参照。

## plan.md コミット前バリデーション（全 Agent 必須）

plan.md を作成・更新した場合、コミット前に以下を `execute` で実行すること:

```bash
bash .github/scripts/bash/validate-plan.sh --path {WORK}plan.md
```

`✅ PASS` を確認してからコミットする。`❌ FAIL` の場合はエラーメッセージを確認し、plan.md のメタデータ（冒頭4行の HTML コメント）または `## 分割判定` セクションを修正する。

## 書き込み失敗/巨大出力への対策

→ Skill `large-output-chunking` を参照。

## 最終品質レビュー

→ Skill `adversarial-review` を参照。Agent 固有の「3つの観点」は Agent 側で定義する。

## knowledge/ STALENESS CHECK（セッション開始時）

1. `knowledge/` 配下の対象ファイル冒頭にある STALENESS メタブロック（sources / blob_sha / generated_at / generator）を確認する
2. 記録された source path の現在 blob SHA とメタブロックの SHA を比較する
3. 不一致がある場合は「stale」と判定し、knowledge ファイルの再生成を優先する
4. 再生成時は work-artifacts-layout §4.1（削除→新規作成）に従い、メタブロックも最新 SHA で再作成する

## knowledge/ 条件付き参照（タスク実行中）

タスク実行中に業務要件・仕様・用語が不明瞭な場合は、Skill `knowledge-lookup` を参照すること。
Agent 固有の `### knowledge/ 参照` セクションで指定された D 番号はそちらを優先する。

## 入力ファイル確認

→ Skill `input-file-validation` を参照。Agent 固有の必読ファイルリストは Agent 側で定義する。

## APP-ID スコープ解決

→ Skill `app-scope-resolution` を参照。

**重要（AAD-WEB / ASDW-WEB / ABD / ABDV 向け）**:
APP-ID 未指定時に「全 APP 対象」とはしない。
`docs/catalog/app-arch-catalog.md` の `A) サマリ表（全APP横断）` を参照し、
workflow に対応する推薦アーキテクチャの APP-ID のみを対象とする。
詳細は Skill `app-scope-resolution` を参照。

## 参照資料

- `.github/skills/agent-common-preamble/references/agent-playbook.md`

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `task-questionnaire` | 参照 | コンテキスト収集・質問票作成の詳細手順 |
| `task-dag-planning` | 参照 | DAG計画・見積・分割判定の詳細手順 |
| `work-artifacts-layout` | 参照 | work/ 構造設計・README入口 |
| `large-output-chunking` | 参照 | 巨大出力の分割手順 |
| `adversarial-review` | 参照 | 敵対的レビューの詳細手順 |
| `harness-verification-loop` | 参照 | コード変更の5段階検証パイプライン |
| `harness-safety-guard` | 参照 | 破壊的操作の事前検知 |
| `harness-error-recovery` | 参照 | エラー発生時の3要素出力 |
| `docs-output-format` | 参照 | `docs/` 成果物フォーマットの共通原則 |
| `knowledge-management` | 参照 | knowledge/ 分類・状態判定・ステータス管理 |
| `knowledge-lookup` | 参照 | タスク実行中の knowledge/ 条件付き参照ルール |
| `input-file-validation` | 参照 | 入力ファイル確認・欠損時処理 |
| `app-scope-resolution` | 参照 | APP-ID スコープ解決 |
