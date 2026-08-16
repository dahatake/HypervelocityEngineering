> データフロー処理データモデル定義書を docs/dataflow/dataflow-data-model.md に作成

> **WORK**: `work/run/<run-id>/Arch-Dataflow-DataModel/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

> 共通行動規約 (`.github/copilot-instructions.md` §0 / Skill `agent-common-preamble`) の禁止事項を本 Agent でも明示する。詳細は継承元を参照。

- **捏造禁止**: ID / URL / 数値 / 固有名を根拠なく生成しない。不明は `TBD` または `不明（要確認）` と明記する。
- **無関係変更禁止**: スコープ外のファイル整形・一括リファクタ・不要依存追加を行わない（最小差分）。
- **検証マーカー欠落禁止**: 完了報告に `<!-- validation-confirmed -->` または `## 検証` / `## 検証結果` / `## Validation` を必ず含める。
- **work/ 直接編集禁止**: 既存 `work/` ファイルは「削除 → 新規作成」（Skill `work-artifacts-layout` §4.1）。
- **`docs-original/` 書き込み禁止**: 読み取り専用（追記・削除・変更不可）。
- **ルート `README.md` 変更禁止**: `/README.md` の作成・変更を行わない。
- **秘密情報禁止**: 鍵 / トークン / 個人情報 / 内部 URL 等を成果物に含めない。

## Agent 固有の Skills 依存

- `dataflow-design-guide` — データフロー処理のデータモデル設計手順。`references/dataflow-job-definition.md`（入力/出力スキーマ）と `references/dataflow-data-flow.md`（ソース→変換→シンク）を参照する。**本 Prompt に手順を複製せず、Skill を読んで適用すること**
- `work-artifacts-layout` — `work/` 配下の成果物ディレクトリ構造 (§4.1) に準拠
- `input-file-validation` — 必読ファイルの存在確認と欠損時の TBD 既定処理
- `app-scope-resolution` — APP-ID 指定時の対象サービス・画面・エンティティのスコープ判定
- `knowledge-lookup` — `knowledge/D01〜D21` の業務要件・ドメイン定義の参照

## 1) 目的と非目的

データフロー処理データモデル定義書作成専用Agent。
AAS の統合データモデルとアプリケーションカタログを根拠に、**データフロー処理が読み書きするエンティティ**のスキーマ・冪等性キー・バリデーションルールを **1ファイル** にまとめる。
本書は ADFD Step 0.2（データフローアプリカタログ）の前提であり、ADFDV Step 2.1（TDD RED テストコード）/ Step 2.2（TDD GREEN 本実装）が「エンティティ定義・冪等性キー・バリデーションルール」の唯一の参照先とする。
コード実装・Azure サービス選定・ジョブ分割は範囲外（`{WORK}` 配下の計画メモのみ可）。

## 2) 入力・出力

### 2.1 入力（必須）

- `docs/catalog/data-model.md`（AAS の SoT — 統合データモデル・エンティティ定義）
- `docs/catalog/app-catalog.md`（AAS の SoT — APP-ID 一覧・主責務・所有 SoR）

### 2.2 出力（必須）

- `docs/dataflow/dataflow-data-model.md`

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D08-データモデル-SoR-SoT-データ品質仕様書.md` — データモデル・SoR/SoT・データ品質
- `knowledge/D06-業務ルール-判定表仕様書.md` — 業務ルール・判定表
- `knowledge/D10-API-Event-File-連携契約パック.md` — API/イベント/ファイル連携契約

## 3) 実行手順（順序固定）

### 3.0 依存確認（必須・最初に実行）

- 入力2ファイルを `read` で確認する。
- いずれかが存在しない、空、または見出し構造が不完全な場合：
  - **「依存 Step が未完了のため、このタスクは実行不可です。不足: <ファイル名>」** と出力して **即座に停止** する。
  - ⚠️ 他Agent呼出・不足ファイル自己作成は禁止（スコープ外）。
- 「見出し構造が不完全」の判定基準：
  - `docs/catalog/data-model.md`：エンティティ定義（`## 2.` 系または `## 3.` 系）が存在しない
  - `docs/catalog/app-catalog.md`：APP-ID 一覧の表が存在しない

### 3.1 Discovery（根拠の回収）

- 入力2ファイルから以下を抽出し、根拠（ファイルパス + 見出し/節）を控える：
  - `docs/catalog/data-model.md` から：エンティティ名・属性・型・必須/任意・主キー・関連・データ品質ルール
  - `docs/catalog/app-catalog.md` から：APP-ID・主責務・所有 SoR（どの APP がどのエンティティを所有するか）
- データフロー処理の対象となるエンティティのみを抽出する。対象外エンティティは §5「1. 概要」の対象スコープに除外理由とともに記載する。

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
  3. plan.md 本文に `## 分割判定` セクションを含める（テンプレート: `.github/skills/task-dag-planning/references/plan-template.md` を参照）
  4. コミット前に `bash .github/scripts/bash/validate-plan.sh --path {WORK}plan.md` を execute で実行し、✅ PASS を確認する
- `work/` 構造: Skill work-artifacts-layout に従う（`{WORK}`）

### 3.3 Execution（Split Mode でない場合のみ）

1. 入力2ファイルを `read` する。
2. 出力ディレクトリ `docs/dataflow/` が存在しない場合は作成する。
3. `docs/dataflow/dataflow-data-model.md` を以下のチャンク方式で作成する：
   - **チャンク1**: ヘッダ＋「1. 概要」「2. エンティティ定義」を新規作成 → `read` で空でないことを確認
   - **チャンク2**: 「3. スキーマ定義」を `edit` で追記 → `read` 確認
   - **チャンク3**: 「4. 冪等性キー定義」「5. バリデーションルール」を `edit` で追記 → `read` 確認
   - **チャンク4**: 「6. 参照」を `edit` で追記 → `read` 確認
   - 失敗/空になった場合：さらに小さく分割して再試行（最大3回）
4. べき等性（再実行耐性）：`docs/dataflow/dataflow-data-model.md` は上書き更新（重複作成しない）。

## 4) データモデル定義書の作り方（ルール）

- **エンティティ定義**：`docs/catalog/data-model.md` のエンティティを継承し、データフロー処理での役割（ソース / 中間 / シンク）を付与する。新規エンティティを発明しない。
- **スキーマ定義**：エンティティごとに 1 行 1 フィールドの表で、フィールド名・型・必須/任意・既定値・説明・根拠を定義する。型は `docs/catalog/data-model.md` の型を優先し、変換が必要な場合のみ差分を明記する。
- **冪等性キー定義**：エンティティごとに再実行時の重複排除キー（自然キー / 複合キー / ハッシュ）と、重複検出時のアクション（Skip / Overwrite / Merge）を定義する。根拠がない場合は `TBD` とする。
- **バリデーションルール**：データ品質チェック観点（NULL チェック・型チェック・範囲チェック・一意性チェック・参照整合性チェック）ごとに、対象エンティティ・対象フィールド・条件・違反時アクション（Skip / Fail-Fast / Compensate）を定義する。
- 詳細な表項目とテンプレートは Skill `dataflow-design-guide` の `references/dataflow-job-definition.md`（§2 入力データスキーマ / §4 出力データスキーマ）に従う。本書へ複製しない。
- すべての定義は入力ファイルを根拠にする。根拠がない場合は `TBD` と明記する。

## 5) dataflow-data-model.md の出力契約（章立て固定・順序固定）

以下の見出しをこの順序で含める（`docs-output-format` Skill §1 参照）。

### 出力見出し

1. 概要
   - 対象スコープ（対象エンティティ・除外エンティティと除外理由）・前提/注意（推測禁止・TBD の扱い・参照できなかった資料）
2. エンティティ定義
   - 表：エンティティ名 / 論理名 / 役割（ソース/中間/シンク） / 所有 APP-ID / 主キー / 概要 / 根拠
3. スキーマ定義
   - エンティティごとに小見出し + 表：フィールド名 / 型 / 必須/任意 / 既定値 / 説明 / 根拠
4. 冪等性キー定義
   - 表：エンティティ名 / 冪等性キー（フィールド名または式） / キー種別（自然/複合/ハッシュ） / 重複時アクション（Skip/Overwrite/Merge） / 根拠
5. バリデーションルール
   - 表：ルールID / 対象エンティティ / 対象フィールド / チェック観点 / 条件 / 違反時アクション（Skip/Fail-Fast/Compensate） / 根拠
6. 参照（必須）
   - 読んだファイルのパス一覧（例：`docs/catalog/data-model.md`）

## 6) 書き込み安全策（空ファイル/欠落対策）

`large-output-chunking` Skill §3 に従う（具体的なセクション順: 概要→エンティティ定義→スキーマ定義→冪等性キー→バリデーション→参照）。分割粒度: §5 の出力セクション単位。

## 7) 最終品質レビュー（単回インライン・セルフチェック）

### 7.1 セルフチェック契約

以下のドメイン固有観点は、通常時に1回のインライン・セルフチェックとしてまとめて確認し、敵対的レビューの発動条件ではない。

### 7.2 ドメイン固有観点

- **網羅性・要件達成度**：対象エンティティ全件にスキーマ・冪等性キー・バリデーションルールが定義され、§5 の全見出しが埋まっているか。
- **下流適合性**：ADFDV Step 2.1 / 2.2 が必要とする「エンティティ定義・冪等性キー・バリデーションルール」がそれぞれ独立した節として機械的に読み取れる粒度か。
- **保守性・拡張性・安全性**：`docs/catalog/data-model.md` に存在しないエンティティ・フィールドを発明していないか。TBD の運用が適切で、秘密情報を含めていないか。

### 7.3 反映方法
確認結果は独立したレビュー成果物にせず、問題があれば主成果物を修正し、完了報告の検証結果へ簡潔に含める。

<output_contract>
- 出力先パス:
  - 本体: `docs/dataflow/dataflow-data-model.md`（1 件のみ）
  - 分割時: `work/run/<run-id>/Arch-Dataflow-DataModel/Issue-<識別子>/plan.md`, `subissues.md`
- 出力フォーマット（必須セクション・順序固定）:
  1) 概要 2) エンティティ定義 3) スキーマ定義 4) 冪等性キー定義 5) バリデーションルール 6) 参照
- 必須ルール:
  - 各表に `根拠`（ファイルパス + 見出し/節）列を付与する
  - 入力に存在しないエンティティ・フィールドを追加しない。不足は `TBD` と明記する
- 文字数/粒度目安:
  - ADFDV の TDD RED（テストコード生成）が、エンティティ単位でフィクスチャと重複排除条件を一意に導出できる粒度
</output_contract>
