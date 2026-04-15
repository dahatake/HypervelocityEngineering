---
name: agent-common-preamble
description: >
  全 Custom Agent が作業開始時に参照する共通プリアンブル。
  copilot-instructions.md §0 の共通ルール参照、全 Agent 共通の Skills 参照リスト、
  分割ルール・エラー対策・品質レビューの Skill 参照先を一元管理する。
  USE FOR: agent start, common rules, preamble, skill reference list,
  shared rules lookup, agent initialization.
  DO NOT USE FOR: implementation, testing, deployment,
  specific skill execution (use the specific skill directly).
  WHEN: Custom Agent が作業を開始したとき、共通ルールを確認したいとき、
  参照すべき Skills 一覧を知りたいとき。
metadata:
  origin: user
  version: "1.0.0"
---

# agent-common-preamble

## 共通ルール

`.github/copilot-instructions.md` §0 を最優先で遵守する。本 Skill は全 Agent 共通の参照先を集約する。

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

## 入力ファイル確認

→ Skill `input-file-validation` を参照。Agent 固有の必読ファイルリストは Agent 側で定義する。

## APP-ID スコープ解決

→ Skill `app-scope-resolution` を参照。

## 参照資料

- `.github/skills/planning/agent-common-preamble/references/agent-playbook.md`

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
| `input-file-validation` | 参照 | 入力ファイル確認・欠損時処理 |
| `app-scope-resolution` | 参照 | APP-ID スコープ解決 |
