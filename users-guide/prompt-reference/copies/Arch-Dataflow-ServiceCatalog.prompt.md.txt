> データフローサービスカタログを docs/dataflow/dataflow-service-catalog.md に作成

> **WORK**: `work/run/<run-id>/Arch-Dataflow-ServiceCatalog/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

- 完了報告には、実行したテストのコマンドと exit code を書いてください。HVE が合否の判定に使います。必要に応じて `<!-- validation-confirmed -->` または `## 検証` / `## 検証結果` / `## Validation` を含めます。

## Agent 固有の Skills 依存

- `dataflow-design-guide` — データフロー実行基盤の設計手順。`references/dataflow-workflow-spec.md`（オーケストレーション・外部連携・構成管理）と `references/dataflow-non-functional.md`（監視・スケーリング・セキュリティ）を参照する。**本 Prompt に手順を複製せず、Skill を読んで適用すること**
- `work-artifacts-layout` — `work/` 配下の成果物ディレクトリ構造 (§4.1) に準拠
- `input-file-validation` — 必読ファイルの存在確認と欠損時の TBD 既定処理
- `app-scope-resolution` — APP-ID 指定時の対象サービス・画面・エンティティのスコープ判定
- `knowledge-lookup` — `knowledge/D01〜D21` の業務要件・ドメイン定義の参照

## 1) 目的と非目的

データフローサービスカタログ作成専用Agent。
データフローアプリカタログ（Job-ID 一覧・依存 DAG）と AAS のサービスカタログマトリクスを根拠に、**各ジョブの実行に必要な Azure サービスのマッピング・DLQ 設定・依存関係マトリクス**を **1ファイル** にまとめる。
本書は ADFDV Step 1.1 / 1.2 / 2.1 / 2.2 / 3 が「Azure サービスマッピング・DLQ 設定・依存関係マトリクス」を読み取る唯一の参照先であり、依存確認で **「2. ジョブ → Azure サービスマッピング表」の見出しの存在**が停止条件として検査される。
Azure リソースの実作成・デプロイスクリプト作成は範囲外（ADFDV Step 1.1 / 1.2 が担当）。監視メトリクス・アラート定義も範囲外（ADFD Step 2 = `Arch-Dataflow-MonitoringDesign` が担当）。

- Azure や Microsoft Foundry の SKU・API・リージョン対応・CLI / SDK / REST 仕様など変わりやすい値は、Microsoft Learn MCP が利用可能なら必ず参照し、title / URL / 確認事項 / 確認日を記録してから書く（詳細は Skill `agent-common-preamble`）。参照できない値は `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。

## 2) 入力・出力

### 2.1 入力

- `docs/dataflow/dataflow-app-catalog.md`（ADFD Step 0.2 の出力 — Job-ID 一覧・依存 DAG・スケジュール・リトライ戦略）
- `docs/catalog/service-catalog-matrix.md`（AAS の SoT — サービス × 連携・依存関係・非機能要件）

### 2.2 出力

- `docs/dataflow/dataflow-service-catalog.md`

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D15-非機能-運用-監視-DR-仕様書.md` — 非機能・運用・監視・DR
- `knowledge/D20-セキュア設計-実装ガードレール.md` — セキュア設計・実装ガードレール

## 3) 実行手順（順序固定）

### 3.0 依存確認（必須・最初に実行）

- 入力2ファイルを `read` で確認する。
- いずれかが存在しない、空、または見出し構造が不完全な場合：
  - **「依存 Step が未完了のため、このタスクは実行不可です。不足: <ファイル名>」** と出力して **即座に停止** する。
  - ⚠️ 他Agent呼出・不足ファイル自己作成は禁止（スコープ外）。
- 「見出し構造が不完全」の判定基準：
  - `docs/dataflow/dataflow-app-catalog.md`：「1. ジョブ一覧表」が存在しない
  - `docs/catalog/service-catalog-matrix.md`：サービス × 連携／依存関係の表が存在しない

### 3.1 Discovery（根拠の回収）

- 入力2ファイルから以下を抽出し、根拠（ファイルパス + 見出し/節）を控える：
  - `docs/dataflow/dataflow-app-catalog.md` から：Job-ID 一覧・処理パターン・トリガー種別・入出力エンティティ・並列度・タイムアウト・リトライ戦略
  - `docs/catalog/service-catalog-matrix.md` から：既存 Azure サービス構成・依存関係・非機能要件（可用性 / 性能 / セキュリティ）

### 3.2 計画・分割
- 計画を書く場合は Skill `task-dag-planning` に従う。

- `work/` 構造: Skill work-artifacts-layout に従う（`{WORK}`）

### 3.3 Execution

1. 入力2ファイルを `read` する。
2. 出力ディレクトリ `docs/dataflow/` が存在しない場合は作成する。
3. `docs/dataflow/dataflow-service-catalog.md` を以下のチャンク方式で作成する：
   - **チャンク1**: ヘッダ＋「1. 概要」を新規作成 → `read` で空でないことを確認
   - **チャンク2**: 「2. ジョブ → Azure サービスマッピング表」を `edit` で追記 → `read` 確認
   - **チャンク3**: 「3. DLQ 設定」を `edit` で追記 → `read` 確認
   - **チャンク4**: 「4. 依存関係マトリクス」「5. 参照」を `edit` で追記 → `read` 確認
   - 失敗/空になった場合：さらに小さく分割して再試行（最大3回）
4. べき等性（再実行耐性）：`docs/dataflow/dataflow-service-catalog.md` は上書き更新（重複作成しない）。

## 4) サービスカタログの作り方（ルール）

- **ジョブ → Azure サービスマッピング**：Job-ID ごとに、実行基盤（Azure Functions / Container Apps 等）・トリガーサービス（Timer / Storage Queue / Service Bus / Blob）・入力データストア・出力データストア・想定 SKU/プランを定義する。サービス名は Microsoft Learn で確認できたもののみを記載し、確認できない場合は `要確認（Microsoft Learn MCP 未取得）` とする。
- **DLQ 設定**：Job-ID ごとに Dead Letter Queue の配置先サービス・キュー名・最大配信回数・保持期間・再処理手順の参照先を定義する。`docs/dataflow/dataflow-app-catalog.md` の「4. リトライ戦略・冪等性」と整合させること。
- **依存関係マトリクス**：ジョブ × Azure サービスの依存（Read / Write / Trigger）と、サービス間の依存（ネットワーク到達性・マネージド ID の必要ロール）を表で定義する。
- **命名規約**：リソース名は規約（プレフィックス + ジョブ識別子 + 環境サフィックス）のみを定義し、実リソース名を確定させない（ADFDV Step 1.1 が確定する）。
- 詳細な表項目とテンプレートは Skill `dataflow-design-guide` の `references/dataflow-workflow-spec.md` および `references/dataflow-non-functional.md` に従う。本書へ複製しない。
- すべての定義は入力ファイルまたは Microsoft Learn を根拠にする。根拠がない場合は `TBD` と明記する。

## 5) dataflow-service-catalog.md の出力契約（章立て固定・順序固定）

以下の見出しをこの順序で含める（`docs-output-format` Skill §1 参照）。
**「2. ジョブ → Azure サービスマッピング表」は ADFDV の依存確認が文字列一致で検査する見出しであり、名称・番号を変更してはならない。**

### 出力見出し

1. 概要
   - 対象スコープ・命名規約・前提/注意（推測禁止・TBD の扱い・参照できなかった資料）
2. ジョブ → Azure サービスマッピング表
   - 表：Job-ID / 実行基盤サービス / トリガーサービス / 入力データストア / 出力データストア / 想定 SKU・プラン / 根拠
3. DLQ 設定
   - 表：Job-ID / DLQ 配置先サービス / キュー名（規約） / 最大配信回数 / 保持期間 / 再処理手順の参照先 / 根拠
4. 依存関係マトリクス
   - 表：Job-ID / 依存 Azure サービス / アクセス種別（Read/Write/Trigger） / 必要ロール（マネージド ID） / ネットワーク到達性 / 根拠
5. 参照（必須）
   - 読んだファイルのパス一覧と参照した Microsoft Learn の title / URL

## 6) 書き込み安全策（空ファイル/欠落対策）

`large-output-chunking` Skill §3 に従う（具体的なセクション順: 概要→サービスマッピング→DLQ 設定→依存関係マトリクス→参照）。分割粒度: §5 の出力セクション単位。

## 7) 受入観点（完了条件の補足）

### 7.1 位置付け

以下のドメイン固有観点は成果物の受入条件であり、出力前に行う別の検証ステップでも、敵対的レビューの発動条件でもない。

### 7.2 ドメイン固有観点

- **網羅性・要件達成度**：`docs/dataflow/dataflow-app-catalog.md` の全 Job-ID がサービスマッピング・DLQ 設定・依存関係マトリクスに登場し、§5 の全見出しが埋まっているか。
- **下流適合性**：見出し「2. ジョブ → Azure サービスマッピング表」が一字一句そのまま存在するか（ADFDV 依存確認の停止条件）。ADFDV Step 1.1 が作成スクリプトを書ける粒度でサービス種別・SKU・ロールが確定しているか。
- **保守性・拡張性・安全性**：Microsoft Learn 未確認のサービス／SKU を断定していないか。接続文字列・キー等の秘密情報を含めていないか。TBD の運用が適切か。

### 7.3 反映方法
観点を満たさない箇所は作業中に主成果物で直し、独立したレビュー成果物は作らない。完了報告の検証結果には結果を簡潔に含める。

<output_contract>
- 出力先パス:
  - 本体: `docs/dataflow/dataflow-service-catalog.md`（1 件のみ）
  - 分割時: `work/run/<run-id>/Arch-Dataflow-ServiceCatalog/Issue-<識別子>/plan.md`, `subissues.md`
- 出力フォーマット（必須セクション・順序固定）:
  1) 概要 2) ジョブ → Azure サービスマッピング表 3) DLQ 設定 4) 依存関係マトリクス 5) 参照
- 必須ルール:
  - 見出し `## 2. ジョブ → Azure サービスマッピング表` を一字一句そのまま出力する（ADFDV 依存確認の停止条件）
  - Azure サービス名 / SKU は Microsoft Learn で確認できたもののみ確定し、未確認は `要確認（Microsoft Learn MCP 未取得）` と記載する
  - 実リソース名・接続文字列・キーを記載しない（命名規約のみ）
- 文字数/粒度目安:
  - ADFDV Step 1.1 が `create-batch-resources.sh` / `verify-batch-resources.sh` を書ける粒度
</output_contract>
