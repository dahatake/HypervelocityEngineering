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

## 詳細ガイド（Progressive Disclosure）
- 移設した詳細本文: [references/detail.md](references/detail.md)
- 追加の詳細資料: `references/` 配下
