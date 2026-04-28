---
name: knowledge-management
description: >
  knowledge/ 配下のファイル管理ルールを提供する。業務要件・判定表・連携契約等の
  ドメイン知識ドキュメントの分類・命名・更新手順を定義する。
  qa/ と knowledge/ の使い分けと整合性管理を含む。
  USE FOR: knowledge/ file management, D01-D21 classification,
  domain knowledge organization, business requirements structuring,
  qa/ vs knowledge/ separation, original-docs/ file format rules,
  folder responsibility matrix, SoT priority resolution,
  content synthesis from qa/original-docs into knowledge documents,
  incremental merge of new information into existing knowledge files.
  DO NOT USE FOR: qa/ file creation (use work-artifacts-layout),
  implementation, deployment, testing.
  WHEN: knowledge/ 配下にファイルを作成・更新する、ドメイン知識を整理する、
  業務要件を構造化する、qa/ と knowledge/ の使い分けを判断する、
  qa/ や original-docs/ の内容を knowledge/ ドキュメントとして合成・構築する。
metadata:
  origin: user
  version: "2.0.0"
---

# knowledge-management

## 目的

`knowledge/` 配下のドメイン知識ドキュメントの分類・**内容合成**・構造化・**マージ管理を行う**。

> **重要**: 本 Skill の主目的は qa/ や original-docs/ の入力を D クラス別の **要求定義書ドラフト** として再構築することである。単なるマッピング表の作成ではない。

## Non-goals（このスキルの範囲外）

- **qa/ 配下のファイル作成** — Skill `work-artifacts-layout` が担当
- **ドキュメント内容の品質評価** — Skill `adversarial-review` が担当
- **実装・デプロイ・テスト** — 各 Agent / harness Skill が担当

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/knowledge-management-guide.md` | D01〜D21 完全分類ルール・状態判定・内容合成手順・ステータス管理テンプレート |

## 中核ワークフロー（4段階）

本 Skill に基づく作業は、以下の 4 段階で構成される。**段階 2（内容合成）が最も重要であり、省略してはならない。**

```
[段階1: 分類] → guide §2, §6, §9
[段階2: 内容合成] ← 主目的 → guide §11（内容合成プロセス）
[段階3: マージ] → guide §12（差分マージ戦略）
[段階4: 整合性検証] → guide §3, §4, §5, §8, §10
```

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
| `knowledge/` | qa/ + original-docs/ から合成された要求定義書ドラフト（出力） |

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

### 例1: qa/ + original-docs/ → knowledge/ への内容合成ケース

**入力**:
- `qa/UC-01-membership-flow.md` に会員フロー関連の Confirmed / Tentative / Unknown 回答が存在する
- `original-docs/membership-spec.md` にフロー仕様の記述がある

**出力**:
- 対象カテゴリ判定: D05（ユースケース）
- 作成ファイル: `knowledge/D05-会員フロー-ユースケースシナリオ集.md`
- **合成内容（§2 確定事項）の例**:
  ```
  ## 2. 確定事項（Confirmed）

  ### 2.1 original-docs/ 由来の確定事項
  membership-spec.md §3 によれば、会員登録フローは「メールアドレス確認→本人確認→ポイント初期付与」の
  3ステップで構成される。各ステップは同期処理であり、いずれかのステップが失敗した場合は登録全体を
  ロールバックしなければならない。

  > 出典: original-docs/membership-spec.md §3

  ### 2.2 qa/ 由来の確定事項
  UC-01 の質問 No.12 への回答によれば、既存会員がメールアドレスを変更する場合も同一フローを経由する
  ことが確定している。変更後 24 時間は旧アドレスと新アドレスの両方でログインできなければならない。

  > 出典: qa/UC-01-membership-flow.md No.12
  ```

### 例2: 既存 knowledge/ ファイルへの差分マージケース

**入力**: `qa/UC-01-membership-flow.md` に追加回答（No.15: 退会フロー追加）が発生した。
`knowledge/D05-会員フロー-ユースケースシナリオ集.md` が既に存在する。

**出力**:
- 差分検出: No.15（退会フロー）は既存ファイルに未記載のため追加対象
- 影響セクション: §2.2（qa/ 由来の確定事項）と §5（最低内容カバー状況）を更新
- 散文更新: 「qa/ 由来の確定事項」に退会フローの要件を散文で追記
- 付録 A: No.15 のマッピング行を追加
- メタブロック: `generated_at` および `sources` を最新化
