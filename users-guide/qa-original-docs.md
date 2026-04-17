# QA Original Docs Review（AQOD）ガイド

## 概要

AQOD は `original-docs/` 配下の Markdown を横断分析し、質問票を自動生成するワークフローです。

- Web 実行: Issue Template `qa-original-docs.yml`
- ローカル実行: `python -m hve orchestrate --workflow aqod`

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
