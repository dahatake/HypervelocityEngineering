---
name: architecture-questionnaire
description: >
  アーキテクチャ候補選定時の質問票テンプレートと適合度表・判定ロジックを提供する。 USE FOR: architecture selection, non-functional requirements, Q1-Q26 questionnaire. DO NOT USE FOR: implementation. WHEN: アーキテクチャ候補を分析する、非機能要件を収集する。
metadata:
  origin: user
  version: 1.0.0
---

# architecture-questionnaire

## 目的

アーキテクチャ候補選定時に使用する質問票テンプレート（Q1-Q26）と、
適合度評価ルールを提供する。

## 質問票テンプレート

→ `.github/skills/planning/architecture-questionnaire/references/question-template.md`

Q1-Q26 の全質問、選択肢、デフォルト回答、デフォルト根拠を含む。

## 出力フォーマット

→ `.github/skills/planning/architecture-questionnaire/assets/output-format.md`

適合度表・推薦レポートの出力フォーマット定義を含む。

## 使用手順

1. 入力ファイル（APP別 `architectural-requirements-app-xx.md`）を確認する
2. `question-template.md` の Q1-Q26 を参照し、回答を収集する
3. 判定ロジックに基づき最適なアーキテクチャを選定する
4. `output-format.md` に従い適合度表を生成する

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `microservice-design-guide` | 後続 | アーキテクチャ選定後のサービス設計詳細化に移行する |
| `task-questionnaire` | 先行 | 非機能要件収集前のコンテキスト確認・不明点整理に使用する |
| `work-artifacts-layout` | 出力先 | 適合度表・推薦レポートの work/ 配下への保存先 |
