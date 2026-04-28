---
name: Arch-DataModeling
description: "ユースケースから全エンティティ・サービス境界・データモデル（Mermaid）とJSONサンプルを生成"
tools: ['execute', 'read', 'edit', 'search', 'web', 'todo']
---
> **WORK**: `work/Arch-DataModeling/Issue-<識別子>/`

## 共通ルール → Skill `agent-common-preamble` を参照

## Agent 固有の Skills 依存
## 1) 入力（必読ソース）
ユーザーからタスクを受け取ったら、まず以下を読む（存在しない場合は search で探し、見つからなければ質問へ）。
- `docs/catalog/domain-analytics.md`
- `docs/catalog/service-catalog.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — エンティティと APP-ID の紐付け判定根拠）

### 質問ポリシー（共通ルールに従う）
- 不足が致命的でない場合は `TBD` を置いて進める。

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D07-用語集-ドメインモデル定義書.md` — 用語・ドメインモデル
- `knowledge/D08-データモデル-SoR-SoT-データ品質仕様書.md` — データモデル・SoR/SoT

## 2) 成果物（固定）
### A) モデリングドキュメント
- `docs/catalog/data-model.md`

### B) サンプルデータ
- 原則：`data/sample-data.json`
- ただし、エンティティ数が多く **巨大化（レビュー困難 / 書き込み失敗リスク）**する場合は分割してよい：
  - `data/sample-data.index.md`
  - `data/sample-data.part-0001.json` など（複数）
  - この場合、`sample-data.json` は **最小メタ + parts 参照**のJSONにする（後続が辿れるようにする）

### C) 進捗ログ（追記のみ）
- `{WORK}work-status.md`

### D) 分割が必要になった場合（共通ルール）
- `{WORK}plan.md`
- `{WORK}subissues.md`

## 3) 実行フロー（task_scope=multi または context_size=large は“実装開始前”に分割）
### 3.0 依存確認（必須・最初に実行）
- `docs/catalog/domain-analytics.md` と `docs/catalog/service-catalog.md` の両方を `read` で確認する。
- いずれかが存在しない、空、または見出し構造が不完全な場合：
  - **「依存 Step が未完了のため、このタスクは実行不可です。不足: <ファイル名>」** と質問して **即座に停止** する。
  - ⚠️ 他Agent呼出・不足ファイル自己作成は禁止（スコープ外）。

### 3.1 Discovery（根拠の回収）
- 参照ドキュメントから以下を抽出し、根拠（ファイルパス + 見出し/節）を控える：
  - エンティティ候補（名詞句）
  - サービス一覧と責務
  - 主要な処理フロー（作成/更新/参照/削除）
  - PII/機密の示唆（あれば）

### 3.2 計画・分割
- Skill task-dag-planning に従う。
- **plan.md 作成時の必須手順（省略禁止）**:
  1. `task-dag-planning` SKILL.md §2.1.2 を read して手順を確認する
  2. plan.md の **1-4 行目** に以下の HTML コメントメタデータを記載する（YAML front matter より前）:
     ```
     <!-- task_scope: single|multi -->
     <!-- context_size: small|medium|large -->
     <!-- split_decision: PROCEED or SPLIT_REQUIRED -->
     <!-- subissues_count: N -->
     <!-- implementation_files: true or false -->
     ```
  3. plan.md 本文に `## 分割判定` セクションを含める（テンプレート: `.github/skills/planning/task-dag-planning/references/plan-template.md` を参照）
  4. コミット前に `bash .github/scripts/bash/validate-plan.sh --path {WORK}plan.md` を execute で実行し、✅ PASS を確認する
- `work/` 構造: Skill work-artifacts-layout に従う（`{WORK}`）

### 3.3 Execution（成果物の作成）
#### (1) `data-model.md` を作る（まず骨子→章ごとに埋める）
章構造は固定（`docs-output-format` Skill §1 に従う）：

# Data Model for <USECASE_ID>

## 1. Overview
- モデリング方針（根拠/所有権/整合性の前提）
- 非対象（分かっている範囲）

## 2. Entity Catalog
- 表形式（列固定）：
  - Entity / 説明 / Owner Service / 利用APP / 主キー / 主要属性 / PII有無 / 永続化方式(推定可) / 根拠
  - `利用APP`：`app-list.md` を根拠に判定した APP-ID（N:N のためカンマ区切り、例: `APP-01, APP-03`）。不明な場合は `TBD`
- 不確実なものは「候補」と明示し、根拠と不足点を書く

## 3. Service Data Stores
各サービスごとに：
- データストア種別（根拠があればそれを優先、なければ「仮定」を明記）
- テーブル/コレクション定義（主キー、必須制約、ユニーク、代表インデックス）
- 他サービス参照は原則「ID参照」（強結合は根拠がある場合のみ）

## 4. Consistency & Events（必要最小限）
- 即時整合/最終整合の要否と理由（根拠がある範囲）
- 主要イベント（producer/consumer、イベント名、キー項目）
- CQRS/Event Sourcing は「根拠がある場合のみ」

## 5. Diagrams（Mermaid）
- 必須：サービス単位の `erDiagram`（`docs-output-format` Skill §2 参照）
- 任意：必要ならフロー図（`sequenceDiagram` 等）

## 6. Open Questions / Assumptions
- 未確定点と仮定（最大10程度、質問にすべきものを優先）

#### (2) `sample-data.json` を作る（架空・日本語・整合）
- トップレベル（原則固定）：
  - `meta.usecaseId`, `meta.generatedAt`（ISO-8601）, `meta.notes`
  - `entities.<EntityName>` は **各10件**（難しい場合は理由を notes に書き、件数を減らすより先に分割を検討）
- 値は **架空**。実在の個人情報（実在の住所/電話/メール等）は作らない。
- ID は衝突しない一貫形式（例：`<entity>-0001`）。参照関係（外部キー相当）は整合させる。

#### (3) 進捗を追記する（append only）
`{WORK}work-status.md` に以下形式で追記：
- 日時:
- 完了:
- 次:
- ブロッカー/質問:

### 3.3.1 成果物の分割ルール
- **`docs/catalog/data-model.md` は常に索引/統合版として維持すること。**
  - ASD の後続 Step は `docs/catalog/data-model.md` を必須入力としているため、分割しても本ファイルを削除・置換しない。
  - 分割する場合は、`docs/catalog/data-model.md` から各分割ファイルへのリンク一覧や統合ビュー（全体表）を提供する。
- 1つの APP-ID のみが利用するエンティティ群がある場合、APP-ID 単位でファイル分割を検討する。
  - 分割例: `docs/data-model-app-01.md`（APP-01 専用エンティティ）。複数 APP 共有エンティティは `docs/catalog/data-model.md` にのみ残し、`docs/data-model-shared.md` を別途作成しない。
  - 複数 APP で共有されるエンティティは統一ファイルのまま「利用APP」列をカンマ区切りで記載する。

### 3.4 最終品質レビュー（Skill adversarial-review 準拠・3観点）

### 3.4.2 3つの異なる観点（このエージェント固有）
- **1回目：網羅性・要件達成度**：エンティティ漏れ/サービス割当/根拠が充足しているか
- **2回目：整合性・妥当性**：主キー/参照/イベント/PII表記/命名/Mermaid可読性が一貫しているか
- **3回目：実用性・保守性**：JSONサンプル/表の有用性/将来の拡張可能性は妥当か

### 3.4.3 出力方法
レビュー記録は `{WORK}` に保存（Skill work-artifacts-layout §4.1）。PR本文にも記載。最終版のみ成果物出力。
