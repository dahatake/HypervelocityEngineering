# Original Docs Review（AQOD）ガイド

## 概要

AQOD は `original-docs/` 配下の Markdown を横断分析し、質問票を自動生成するワークフローです。`original-docs/` → `qa/` の変換を担い、後続の `akm` が `knowledge/` へ統合します。

![AQOD が original-docs を分析して qa を生成し、後続の akm が knowledge に統合するフロー図](./images/knowledge-interface-flow.svg)

- Web 実行: Issue Template `original-docs-review.yml`
- ローカル実行: `python -m hve orchestrate --workflow aqod`

## Agent チェーン図（AQOD）

以下の図は、このワークフローで使用される Custom Agent がファイルの入出力を介してどのように連鎖するかを示します。

![AQOD: QA-DocConsistency の1ステップチェーン（並列0箇所含む）](./images/chain-aqod.svg)


## 出力

- Issue 起動時: `qa/QA-DocConsistency-Issue-<N>.md`
- ローカル実行時: `qa/QA-DocConsistency-<yyyymmdd-HHMMSS>.md`（JST）

## Issue Template 入力

- `target_scope`: 対象スコープ（省略時: `original-docs/`）
- `depth`: `standard` / `lightweight`
- `focus_areas`: 重点観点（任意）
- `model`: 使用モデル（任意）

## CLI 例

```bash
python -m hve orchestrate --workflow aqod
python -m hve orchestrate --workflow aqod --target-scope original-docs/ --depth lightweight
python -m hve orchestrate --workflow aqod --focus-areas "データ整合性、冪等性"
```
