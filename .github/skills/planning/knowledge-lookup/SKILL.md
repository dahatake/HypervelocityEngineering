---
name: knowledge-lookup
description: >
  knowledge/ 配下の確定済みドメイン知識ドキュメント（D01〜D21）を参照する。
  USE FOR: checking business rules, verifying glossary definitions, reviewing data model specifications,
  checking use case details, reviewing API integration specifications, checking non-functional requirements,
  reviewing secure design guardrails.
  DO NOT USE FOR: creating or updating knowledge/ files (use knowledge-management skill),
  creating questionnaires under qa/, implementation, deployment, testing,
  source-code-only tasks (file summarization, code quality scanning, inventory generation, etc.).
  WHEN: during task execution, business requirements, specifications, terminology, or rules are missing
  from the Agent input files,
  or the available description is ambiguous and allows multiple interpretations.
metadata:
  origin: user
  version: "0.1.0"
---

# knowledge-lookup

## 目的

Custom Agent がタスク実行中に不明瞭な点に遭遇した際、
`knowledge/` 配下の確定済みドキュメントを参照して正確な情報を取得する。

## Non-goals（このスキルの範囲外）

- **knowledge/ ファイルの作成・更新** → Skill `knowledge-management` が担当
- **docs/catalog/ の参照** → 各 Arch-* Agent が直接参照
- **original-docs/ の直接参照ガイド** → `copilot-instructions.md` §5 が規定
- **Agent の参照方式選択（直接/経由/ハイブリッド）の制約** → 本 Skill は knowledge/ 経由参照の手順を提供するのみ

## 既存の `### knowledge/ 参照` セクションとの関係

一部の Agent は既に `### knowledge/ 参照（任意・存在する場合のみ）` セクションで
具体的な D 番号ファイルを直接指定している（例: D06, D07, D08, D10, D17, D20, D21）。

- **既存の直接参照を優先する。** Agent が明示的に指定した D 番号は、本 Skill を経由せず従来通り参照される。
- **本 Skill は補完的に機能する。** 既存の直接参照がカバーしていない D 番号への動的参照が必要な場合に、本 Skill のルールに従って参照する。
- 既存の直接参照セクションは削除しない（破壊的変更の回避）。

## 「不明瞭」の判断基準

Agent が knowledge/ を参照すべき「不明瞭な状態」とは、以下のいずれかに該当する場合を指す:

1. **Agent の入力ファイル（定義書・分析書等）に該当情報が記載されていない**
2. **入力ファイルの記述が曖昧で、複数の解釈が可能**
3. **入力ファイル内の用語・数値・ルールに矛盾があり、正しい情報を判断できない**

以下の場合は「不明瞭」に該当 **しない**（knowledge/ 参照不要）:

- Agent の入力ファイルに十分な情報が記載されている
- コーディング規約・技術的な実装パターンの判断（→ `copilot-instructions.md` が担当）
- ソースコードの構造分析のみが目的のタスク

## 参照手順

### Step 1: 不明瞭な点を特定する

Agent の入力ファイルを読み込んだ結果、上記の判断基準に該当する不明点を特定する。

### Step 2: 該当カテゴリを特定する

1. `knowledge/business-requirement-document-status.md` が存在する場合:
   - このファイルで該当カテゴリ（D 番号）と状態を確認する
2. `knowledge/business-requirement-document-status.md` が存在しない場合（フォールバック）:
   - `knowledge/` ディレクトリを直接確認し、ファイル名の `D{NN}-` プレフィックスからカテゴリを判定する
3. `knowledge/` 自体が空または存在しない場合:
   - 「knowledge/ 未整備のため参照不可」と判断し、Step 5 に進む

### Step 3: 該当ドキュメントを読み込む

- 該当する `knowledge/D{NN}-*.md` を読み込む

### Step 4: 状態判定と採用ルール

- knowledge/ ファイル内に状態ラベル（Confirmed / Tentative / Unknown / Conflict 等）が存在する場合:
  - **Confirmed** の情報を採用する
  - **Tentative / Unknown / Conflict** の情報は「未確定」として扱い、`TBD（要確認）` と明示する
- 状態ラベルが存在しない場合:
  - 記載内容を全て参照可とする（ただし、`TBD` と明記された項目は未確定扱い）

### Step 5: 情報が見つからなかった場合の振る舞い（段階的ルール）

| 状況 | Agent の振る舞い |
|------|-----------------|
| Agent の入力ファイルに該当情報がある | **そのまま継続**（knowledge/ 参照不要） |
| 入力ファイルに記載なし、knowledge/ に Confirmed 情報あり | **knowledge/ から採用して継続** |
| 入力ファイルに記載なし、knowledge/ にも該当情報なし | **ユーザーに確認を求めて処理停止** |
| knowledge/ 自体が未整備（ファイルなし） | **入力ファイルの情報のみで継続し、不明点は `TBD（要確認）` として明示** |

## D01〜D21 カテゴリ参照ガイド

以下は、不明瞭な内容と参照先 D 番号の対応ガイドである。
1つの不明点が複数の D 番号にまたがる場合は、関連する全ての D 番号を参照する。

| 不明な内容の種類 | 参照先 D 番号 |
|-----------------|--------------|
| 事業目的・背景 | D01 |
| スコープ・制約 | D02 |
| ステークホルダー・組織 | D03 |
| 業務プロセス・業務フロー | D04 |
| ユースケース | D05 |
| 業務ルール・判定表 | D06 |
| 用語・ドメインモデル定義 | D07 |
| データモデル・SoR/SoT | D08 |
| システムコンテキスト | D09 |
| API・イベント・ファイル連携 | D10 |
| 画面仕様 | D11 |
| 権限・ロール | D12 |
| セキュリティ要件 | D13 |
| 国際化・多言語 | D14 |
| 非機能要件（性能・可用性等） | D15 |
| 移行要件 | D16 |
| 品質保証・UAT | D17 |
| Prompt ガバナンス | D18 |
| ソフトウェアアーキテクチャ・ADR | D19 |
| セキュア設計・実装ガードレール | D20 |
| CI/CD・ビルド・リリース | D21 |

> 上記マッピングで特定できない場合は、`knowledge/business-requirement-document-status.md` を参照して検索する。

## 制約

- **この Skill のスコープでは** knowledge/ は読み取り専用
- 該当ドキュメントが存在しない場合は「knowledge/ に該当情報なし」と明示し、**捏造しない**
- 本 Skill は Agent の参照方式選択（`copilot-instructions.md` §5 で定義された 直接参照/knowledge/ 経由参照/ハイブリッド）を制約しない

## 設計上の前提と注意事項

- **Skill 自動マッチングの精度は仮定に基づく設計である。** Copilot の description ベースのマッチングが期待通りに動作するかは、手動検証で確認が必要。
- knowledge/ のドキュメントが充実するにつれて、本 Skill の有用性が向上する。初期段階では Step 5 の「knowledge/ 未整備」パスが頻繁に使用される。

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `knowledge-management` | 補完 | knowledge/ の作成・更新を担当（本 Skill は読み取り専用参照） |
| `agent-common-preamble` | 被参照 | 全 Agent 共通ルールから本 Skill を参照 |
| `task-questionnaire` | 連携 | 不明点がユーザー確認を要する場合、質問票作成に連携 |
