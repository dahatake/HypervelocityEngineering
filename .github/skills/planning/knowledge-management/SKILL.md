---
name: knowledge-management
description: >
  knowledge/ 配下のファイル管理ルールを提供する。業務要件・判定表・連携契約等の
  ドメイン知識ドキュメントの分類・命名・更新手順を定義する。
  qa/ と knowledge/ の使い分けと整合性管理を含む。
  USE FOR: knowledge/ file management, D01-D21 classification,
  domain knowledge organization, business requirements structuring,
  qa/ vs knowledge/ separation.
  DO NOT USE FOR: qa/ file creation (use work-artifacts-layout),
  implementation, deployment, testing.
  WHEN: knowledge/ 配下にファイルを作成・更新する、ドメイン知識を整理する、
  業務要件を構造化する、qa/ と knowledge/ の使い分けを判断する。
metadata:
  origin: user
  version: "1.0.0"
---

# knowledge-management

## 目的

`knowledge/` 配下のドメイン知識ドキュメントの分類・命名・更新手順を一元管理する。

## Non-goals（このスキルの範囲外）

- **qa/ 配下のファイル作成** — Skill `work-artifacts-layout` が担当
- **ドキュメント内容の品質評価** — Skill `adversarial-review` が担当
- **実装・デプロイ・テスト** — 各 Agent / harness Skill が担当

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/knowledge-management-guide.md` | D01〜D21 完全分類ルール・状態判定・ステータス管理テンプレート |

## 概要

### ファイル分類（D01〜D21）

`knowledge/` ファイルは以下のカテゴリに分類される:

| カテゴリ | 対象 |
|---------|------|
| D01〜D07 | 事業・スコープ・ステークホルダー・業務プロセス・ユースケース・業務ルール・用語 |
| D08〜D14 | データモデル・システムコンテキスト・API連携・画面・権限・セキュリティ・国際化 |
| D15〜D21 | 非機能・移行・品質・Prompt・アーキテクチャ・セキュア設計・CI/CD |

### qa/ と knowledge/ の使い分け

| フォルダ | 用途 |
|---------|------|
| `qa/` | 質問票・未回答・確認中の項目 |
| `knowledge/` | 確定済み・承認済みの要件・ナレッジ |

### ファイル命名規則

`knowledge/D{NN}-{文書名}.md`
- `{NN}` は2桁ゼロ埋め（例: `D01`, `D09`）
- スペース・スラッシュは `-` に変換
- 日本語文字はそのまま保持

## 入出力例

※ 以下は説明用の架空例です。

### 例1: qa/ → knowledge/ への昇格ケース

**入力**: `qa/UC-01-membership-flow.md` に記載された確定済み業務フローを `knowledge/` に昇格させたい。

**出力**:
- 対象カテゴリ判定: D05（ユースケース）
- 作成ファイル: `knowledge/D05-membership-flow.md`
- 昇格内容: qa/ の確定事項（Confirmed 状態の質問回答）のみを抽出し、TBD 項目（Unknown/Tentative）は除外して knowledge/ に記載

### 例2: 新規 knowledge/ ファイル作成ケース

**入力**: 新しいポイント還元ルール（業務ルール D06）を knowledge/ に追加したい。

**出力**:
- 対象カテゴリ判定: D06（業務ルール）
- 作成ファイル: `knowledge/D06-point-royalty-rule.md`
- 内容: ポイント還元率・上限・期限の確定ルールを記載
- 命名: スペースを `-` に変換、日本語文字はそのまま保持
