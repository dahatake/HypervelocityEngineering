---
name: task-dag-planning
description: >
  タスクの依存関係（DAG）で分解し、タスク粒度とコンテキストサイズで分割判断を行うスキル。 USE FOR: create plan, estimate task, split issue. DO NOT USE FOR: implementation execution (agents do that separately). WHEN: 計画を立てたい、見積をしたい。
metadata:
  origin: user
  version: 3.0.0
---
# task-dag-planning

## 目的
- task-dag-planning の適用判断と実行フローを定義する。

## トリガー
- この Skill の適用判断は frontmatter `description`（USE FOR / DO NOT USE FOR / WHEN）に従う。
- 詳細な手順・コマンド例・トラブルシューティングが必要になった時点で `references/` を参照する。

## 手順サマリ
1. 要件を確認し、対象範囲と非対象を明確化する。
2. `references/detail.md` を起点に、必要に応じて既存の `references/` 個別資料を併読する。
3. 前提条件・権限・安全条件を満たしたうえで実施する。
4. 実施後は検証結果と既知制約を記録し、後続 Skill へ必要事項を引き継ぐ。

## subissues.md 作成規約（SPLIT_REQUIRED 時・全 Agent 必須）

SPLIT_REQUIRED と判定された場合、`{WORK}subissues.md` を作成する。**フォーマット違反は Orchestrator がパース失敗で実行を停止する**ため、本文の規約を以下に集約する（references への遷移なしで完結させる）。

### 必須ルール

1. `references/subissues-template.md` を read してコピー元とする（再発明禁止）。
2. 各サブタスクは `<!-- subissue -->` マーカー行で開始する。
3. **マーカー直下に `<!-- title: <タイトル> -->` HTML コメントを必ず置く**（空値・`REPLACE_ME` 等のプレースホルダ禁止、大文字小文字不問）。
4. 任意メタデータ（必要時のみ）: `<!-- labels: a,b -->` / `<!-- custom_agent: AgentName -->` / `<!-- depends_on: 1,2 -->`（1-indexed、自身以上のブロック番号への前方参照禁止）。
5. Markdown 見出し（`## Sub-N: ...`）と `<!-- title: -->` の内容は一致させる。
6. ファイル保存後、Skill `agent-common-preamble` §subissues.md コミット前バリデーションに従い `validate-subissues` を実行し PASS を確認する（完了報告前必須）。

### 最小サンプル

```markdown
<!-- subissue -->
<!-- title: Sub-1 のタイトル -->
<!-- custom_agent: Arch-Microservice-ServiceDetail -->
<!-- depends_on: -->
## Sub-1: Sub-1 のタイトル

- 対象: ...
- 完了条件: ...
```

### よくある誤り（必ず避ける）

- Markdown 見出し（`## Sub-1: ...`）のみ書いて `<!-- title: -->` を省略する → パーサ [hve/split_fork.py](../../../hve/split_fork.py) が即失敗し Step が停止する。
- `<!-- title: REPLACE_ME -->` や空値のまま放置する → プレースホルダ検出で失敗する。
- `<!-- subissue -->` を箇条書きや見出し配下に埋めて行頭に置かない → ブロック分割が崩れる。

## Prompt Edition controller 例外
- Prompt Edition controller が提示済み実行計画への**明示承認**を取得し、その plan SHA-256 を渡して既存 `hve prompt run` を起動する場合、controller 自身が standalone かつ `task_scope=multi` / `context_size=large` でも、本 Skill の plan-only 規則はその**委譲自体**を禁止しない。HVE が FR-PROMPT-04 の SHA-256 一致を確認した場合だけ `orchestrate` へ進む。
- この例外は controller の**委譲可否**だけを扱う。controller 自身が対象成果物を直接実装・編集すること、または新しい実行フラグ・抽象化・別経路を導入することは許可しない。
- 承認前は停止する。`hve prompt run` が stale を検出した場合は `orchestrate` へ進まず、controller が再plan・再提示した後に再承認を要求する。
- 委譲先 Step は既存 Orchestrator 規則に従い、plan/subissues のみで停止せず、宣言された `output_paths` を実行完了時点で存在させる。通常の standalone / Cloud / CLI-GUI 規則、plan metadata、subissues.md 規則は維持する。

## 詳細ガイド（Progressive Disclosure）
- 移設した詳細本文: [references/detail.md](references/detail.md)
- 追加の詳細資料: `references/` 配下
