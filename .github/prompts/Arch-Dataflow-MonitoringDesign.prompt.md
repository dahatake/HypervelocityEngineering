> データフロー処理監視・運用設計書を docs/dataflow/dataflow-monitoring-design.md に作成

> **WORK**: `work/run/<run-id>/Arch-Dataflow-MonitoringDesign/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

- 完了報告には、実行したテストのコマンドと exit code を書いてください。HVE が合否の判定に使います。必要に応じて `<!-- validation-confirmed -->` または `## 検証` / `## 検証結果` / `## Validation` を含めます。

## Agent 固有の Skills 依存

- `dataflow-design-guide` — データフロー処理監視・運用設計の手順
- `work-artifacts-layout` — `work/` 配下の成果物ディレクトリ構造 (§4.1) に準拠
- `input-file-validation` — 必読ファイルの存在確認と欠損時の TBD 既定処理
- `app-scope-resolution` — APP-ID 指定時の対象サービス・画面・エンティティのスコープ判定
- `knowledge-lookup` — `knowledge/D01〜D21` の業務要件・ドメイン定義の参照

## 1) 目的と非目的

データフロー処理監視・運用設計書作成専用Agent。
バッチサービスカタログとジョブ設計カタログを根拠に、監視メトリクス・アラートルール・ダッシュボード設計・ログ設計・運用手順を **1ファイル** にまとめる。
コード実装は範囲外（`{WORK}` 配下の計画メモのみ可）。

## 2) 入力・出力

### 2.1 入力

- `docs/catalog/app-catalog.md`（AAS の SoT — APP-ID 一覧）
- `docs/catalog/service-catalog-matrix.md`（AAS の SoT — サービス × ジョブ DAG・スケジュール）

### 2.2 出力

- `docs/dataflow/dataflow-monitoring-design.md`

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D15-非機能-運用-監視-DR-仕様書.md` — 非機能・運用・監視・DR

## 4) 実行手順（順序固定）

### 3.0 依存確認（必須・最初に実行）

- 入力2ファイルを `read` で確認する。
- いずれかが存在しない、空、または見出し構造が不完全な場合：
  - **「依存 Step が未完了のため、このタスクは実行不可です。不足: <ファイル名>」** と出力して **即座に停止** する。
  - ⚠️ 他Agent呼出・不足ファイル自己作成は禁止（スコープ外）。
- 「見出し構造が不完全」の判定基準：
  - `docs/catalog/service-catalog-matrix.md`：「2. ジョブ → Azure サービスマッピング表」「4. 依存関係マトリクス」の見出しが存在しない
  - `docs/catalog/service-catalog-matrix.md`：「1. ジョブ一覧表」「2. ジョブ依存 DAG」の見出しが存在しない

### 3.1 Discovery（根拠の回収）

- 入力2ファイルから以下を抽出し、根拠（ファイルパス + 見出し/節）を控える：
  - `docs/catalog/app-catalog.md` から：APP-ID 一覧・主責務・所有 SoR・主要連携
  - `docs/catalog/service-catalog-matrix.md` から：サービス × ジョブ DAG・スケジュール・SLA/タイムアウト・リトライ戦略・エラーハンドリング方針・トリガー API 定義・依存関係マトリクス

### 3.2 計画・分割
- 計画を書く場合は Skill `task-dag-planning` に従う。

- `work/` 構造: Skill work-artifacts-layout に従う（`{WORK}`）

### 3.3 Execution

1. 入力2ファイルを `read` する。
2. 出力ディレクトリ `docs/dataflow/` が存在しない場合は作成する。
3. `docs/dataflow/dataflow-monitoring-design.md` を以下のチャンク方式で作成する：
   - **チャンク1**: ヘッダ＋「1. 概要」を新規作成 → `read` で空でないことを確認
   - **チャンク2**: 「2. 監視メトリクス定義」を `edit` で追記 → `read` 確認
   - **チャンク3**: 「3. アラートルール」「4. ダッシュボード設計」を `edit` で追記 → `read` 確認
   - **チャンク4**: 「5. ログ設計」「6. 運用手順書」「7. 参照」を `edit` で追記 → `read` 確認
   - 失敗/空になった場合：さらに小さく分割して再試行（最大3回）
4. べき等性（再実行耐性）：`docs/dataflow/dataflow-monitoring-design.md` は上書き更新（重複作成しない）。

## 4) 監視・運用設計書の作り方（ルール）

- **監視メトリクス定義**：Job-ID ごとに以下のメトリクスを定義する（根拠は `docs/catalog/service-catalog-matrix.md` のタイムアウト/SLA 設定）：
  - ジョブ実行時間（duration_ms）：正常範囲・警告閾値・エラー閾値
  - 処理レコード数（records_processed）：期待値・最低保証値
  - エラー率（error_rate）：許容最大値（%）
  - データ品質スコア（data_quality_score）：合格ライン（0〜100 スコア）
- **アラートルール**：メトリクス閾値ごとに通知先（Azure Monitor Action Group / Teams / メール）・重要度（Critical/Warning/Informational）・エスカレーション先を定義する。Azure Monitor のアラートルール名は `batch-<jobId>-<metric>-alert` の形式を推奨する。
- **ダッシュボード設計**：Azure Monitor / Application Insights を根拠にしたダッシュボードレイアウトを定義する。KQL クエリ例を各ウィジェットに付記する（クエリは動作検証不要だが構文的に正しいこと）。
- **ログ設計**：構造化ログ（JSON 形式）のフィールド定義・トレース ID 伝播設計・相関 ID（correlation_id）の生成・引き回し方針を記述する。Azure Application Insights の `customDimensions` への出力形式と整合させること。
- **運用手順書**：手動リトライ・スキップ・ロールバック・障害対応フローをフロー図または手順リストで記述する。`docs/catalog/service-catalog-matrix.md` のトリガー API 定義を根拠に、API エンドポイントを具体的に記載する。
- すべての定義は入力ファイルを根拠にする。根拠がない場合は `TBD` と明記する。

## 5) batch-monitoring-design.md の出力契約（章立て固定・順序固定）

以下の見出しをこの順序で含める（`docs-output-format` Skill §1 参照）。

### 出力見出し

1. 概要
   - 対象スコープ・前提/注意（推測禁止・TBD の扱い・参照できなかった資料）
2. 監視メトリクス定義
   - 表：Job-ID / メトリクス名 / 説明 / 単位 / 正常範囲 / 警告閾値 / エラー閾値 / 根拠
3. アラートルール
   - 表：アラート名 / 対象メトリクス / Job-ID / 閾値 / 重要度（Critical/Warning/Informational） / 通知先 / エスカレーション先 / 根拠
4. ダッシュボード設計
   - ダッシュボード名・レイアウト概要
   - 表：ウィジェット名 / 種別（折れ線/棒/数値/ログ） / データソース / KQL クエリ例 / 根拠
5. ログ設計
   - 表：フィールド名 / 型 / 説明 / 必須/任意 / customDimensions キー名 / 根拠
   - トレース ID 伝播設計（説明）
   - 相関 ID 生成・引き回し方針（説明）
6. 運用手順書
   - 手動リトライ手順（対象 API エンドポイント・手順リスト）
   - スキップ手順（条件・手順リスト）
   - ロールバック手順（条件・手順リスト）
   - 障害対応フロー（Mermaid `flowchart TD` またはフロー手順リスト）
7. 参照（必須）
   - 読んだファイルのパス一覧（例：`docs/catalog/service-catalog-matrix.md`）

## 6) 書き込み安全策（空ファイル/欠落対策）

`large-output-chunking` Skill §3 に従う（具体的なセクション順: 概要→メトリクス→アラート→ダッシュボード→ログ→運用手順→参照）。分割粒度: §5 の出力セクション単位。

## 7) 受入観点（完了条件の補足）

### 7.1 位置付け

以下のドメイン固有観点は成果物の受入条件であり、出力前に行う別の検証ステップでも、敵対的レビューの発動条件でもない。

### 7.2 ドメイン固有観点

- **網羅性・要件達成度**：全 Job-ID のメトリクスとアラートルールが定義され、§5 の全見出しが埋まっているか。KQL クエリ例が全ウィジェットに付記され、ログフィールド定義が揃っているか。
- **運用実用性・実装可能性**：アラートルールの通知先とエスカレーション先が具体的か。運用手順書の API エンドポイントが `docs/catalog/service-catalog-matrix.md` のトリガー API 定義と一致しているか。障害対応フローが実際の運用担当者に伝わる粒度か。
- **保守性・拡張性・安全性**：メトリクス定義と閾値の根拠が明記されているか。ログ設計が Application Insights の `customDimensions` と整合しているか。TBD の運用が適切か。

### 7.3 反映方法
観点を満たさない箇所は作業中に主成果物で直し、独立したレビュー成果物は作らない。完了報告の検証結果には結果を簡潔に含める。
