---
name: knowledge-management
description: >
  knowledge/ 配下のファイル管理ルールを提供する。業務要件・判定表・連携契約等の
  ドメイン知識ドキュメントの分類・命名・更新手順を定義する。
  qa/ と knowledge/ の使い分けと整合性管理を含む。
  USE FOR: knowledge/ file management, D01-D21 classification,
  domain knowledge organization, business requirements structuring,
  qa/ vs knowledge/ separation, original-docs/ file format rules,
  folder responsibility matrix, SoT priority resolution.
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

### original-docs/ と qa/ と knowledge/ と docs/catalog/ の責務分担

| フォルダー | 責務 | SoT 対象 | 書き込み主体 |
|-----------|------|----------|-------------|
| `original-docs/` | ユーザー提供の原本（テキスト形式: `.md` / `.txt` / `.csv`） | 原本そのもの | ユーザー手動 |
| `qa/` | Copilot が生成した質問票・チェックリスト | QA プロセスの証跡 | 各 Agent（task-questionnaire 経由） |
| `knowledge/` | qa/ + original-docs/ 由来の構造化ドキュメント（D01〜D21） | セッション間の参照ハブ | KnowledgeManager / KnowledgeManager |
| `docs/catalog/` | 確定済みの正式仕様（app-catalog, use-case-catalog 等） | アプリ仕様・アーキテクチャ仕様の正本 | Arch-* Agent 群 |

#### SoT 優先順位（矛盾時の解決ルール）
1. `original-docs/` のユーザー原本が最優先（ユーザーが提供した事実）
2. `qa/` のユーザー回答（Confirmed）が次に優先
3. `knowledge/` の構造化ドキュメント（1, 2 から派生）
4. `docs/catalog/` の設計仕様（3 から派生）

### original-docs/ のファイル形式ルール

- Copilot が読み取り可能な **テキスト形式のみ** を配置する（`.md`, `.txt`, `.csv`）
- Word / Excel / PDF 等のバイナリは **Markdown に変換してから配置** する
- 変換前の原本を保管する場合は `original-docs/binary-originals/` に配置し、変換後ファイルの冒頭に以下を付与する:
  ```
  <!-- source: binary-originals/{filename}, converted: {YYYY-MM-DD} -->
  ```

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
