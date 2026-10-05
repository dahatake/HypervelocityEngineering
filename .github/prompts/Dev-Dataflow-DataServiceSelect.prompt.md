> バッチサービスカタログを読み、必要な Azure データサービスを特定して src/infra/azure/dataflow/ スクリプトを作成する（Step 1.1: データサービス選定）

> **WORK**: `work/run/<run-id>/Dev-Dataflow-DataServiceSelect/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

- 完了報告には、実行したテストのコマンドと exit code を書いてください。HVE が合否の判定に使います。必要に応じて `<!-- validation-confirmed -->` または `## 検証` / `## 検証結果` / `## Validation` を含めます。

## 1) 目的と非目的

データフローアプリ デプロイ & CI/CD 構築専用Agent の **Step 1.1: データサービス選定** 担当。
バッチサービスカタログ・ジョブカタログ・ジョブ詳細仕様書を根拠に、
データフローアプリに必要な **Azure データサービスを特定** し、**Azure リソース作成スクリプト・検証スクリプト** を作成する。
リソースの実行（デプロイ）は範囲外（Step 1.2 で行う）。
"全ジョブ横断設計刷新" や "アーキテクチャ変更" は範囲外（必要なら別タスク化）。

## 2) 変数

- 対象ジョブID: {対象ジョブID（省略時は `batch-job-catalog.md` の全ジョブ）}
- リソースグループ名: {リソースグループ名}
- リージョン: `azure-region-policy` Skill §1 標準リージョン優先順位に従う

## 3) 入力・出力

### 3.1 入力

- `docs/dataflow/dataflow-service-catalog.md`（Arch-Dataflow-ServiceCatalog の出力 — Azure サービスマッピング・DLQ 設定・依存関係マトリクス）
- `docs/dataflow/dataflow-app-catalog.md`（Arch-Dataflow-AppCatalog の出力 — Job-ID 一覧・スケジュール・リトライ戦略）

### 3.2 入力（補助）

- `docs/dataflow/apps/{jobId}-{jobNameSlug}-spec.md`（ジョブ詳細仕様書 — 設定値一覧・環境変数）
- `docs/dataflow/dataflow-monitoring-design.md`（監視・運用設計書 — メトリクス定義・アラートルール）
- `src/infra/azure/` 配下の既存スクリプト（既存パターンがあれば踏襲する）

### 3.3 出力

- `src/infra/azure/dataflow/create-batch-resources.sh`（Azure CLI でデータフロー用リソースを冪等作成）
- `src/infra/azure/dataflow/verify-batch-resources.sh`（作成したリソースの存在・状態検証）
- 作業ログ: `{WORK}` 配下

- Azure や Microsoft Foundry の SKU・API・リージョン対応・CLI / SDK / REST 仕様など変わりやすい値は、Microsoft Learn MCP が利用可能なら必ず参照し、title / URL / 確認事項 / 確認日を記録してから書く（詳細は Skill `agent-common-preamble`）。参照できない値は `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D15-非機能-運用-監視-DR-仕様書.md` — 非機能・運用・監視・DR
- `knowledge/D20-セキュア設計-実装ガードレール.md` — セキュア設計・実装ガードレール
- `knowledge/D21-CI-CD-ビルド-リリース-供給網管理仕様書.md` — CI/CD・ビルド・リリース

## 4) 依存確認（必須・最初に実行）

入力ファイルを `read` で確認し、以下の条件を満たさない場合は **即座に停止** する：

> 停止メッセージ共通: 「依存Step未完了。不足: {ファイル名}」

| 確認対象 | 停止条件 |
|---|---|
| `docs/dataflow/dataflow-service-catalog.md` | 存在しない・空・「2. ジョブ → Azure サービスマッピング表」がない |
| `docs/dataflow/dataflow-app-catalog.md` | 存在しない・空・「1. ジョブ一覧表」がない |

- ⚠️ 他Agent呼出・不足ファイル自己作成は禁止（スコープ外）。

### 5) 実行フロー（DAG）

このエージェントは以下のステップを実行する：

```
A) Azure 作成スクリプト作成（src/infra/azure/dataflow/）
→ E) 進捗ログ（随時更新）
```

※ Azure リソースの実行（A-exec）は Step 1.2（Dev-Dataflow-DataDeploy）が担当する。

## 4) 実行手順（順序固定）

### 6.1 計画・分割
- 計画を書く場合は Skill `task-dag-planning` に従う。

- `batch-job-catalog.md` から Job-ID 一覧を抽出し、ジョブ数を確定する。
- `work/` 構造: Skill work-artifacts-layout に従う（`{WORK}`）

### 6.2 ステップ A: Azure 作成スクリプト作成

1. `batch-service-catalog.md` の「2. ジョブ → Azure サービスマッピング表」と「依存関係マトリクス」から、作成が必要な Azure リソースを一覧化する（根拠を控える）。
2. `src/infra/azure/dataflow/create-batch-resources.sh` を作成する（`azure-cli-deploy-scripts` Skill §1「3点セットテンプレート」および §2「冪等性パターン」に準拠）：
   - 対象リソースグループが存在するか確認し、存在しない場合は冪等に作成する（`azure-cli-deploy-scripts` Skill §1.2 および `azure-region-policy` Skill §1 に準拠）
   - リソース種別の根拠は `batch-service-catalog.md` と、**Microsoft Learn MCP**（Microsoft 公式ドキュメント検索ツール。利用可能なら必ず参照）で確認する。Azure 実リソース操作が必要な場合のみ **Azure MCP**（Azure サービス操作のための Model Context Protocol ツール）を併用する。Microsoft Learn MCP 利用不可時は `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。
3. `src/infra/azure/dataflow/verify-batch-resources.sh` を作成する（`azure-cli-deploy-scripts` Skill §1.4 テンプレートに準拠）：
   - `create-batch-resources.sh` が作成する全リソースの存在を Azure CLI で検証するスクリプト。

## 7) 書き込み安全策（空ファイル/欠落対策）

`large-output-chunking` Skill §3 に従う（具体的なセクション順: ヘッダ → リソースグループ作成 → Function App 作成 → ...）。

## 8) タスク固有の禁止事項

- シークレット情報（接続文字列・APIキー・パスワード）をコードやスクリプトにハードコードしない。
- データフロー設計ドキュメント（`docs/dataflow/`）を変更しない。
- ジョブ詳細仕様書（`docs/dataflow/apps/`）を変更しない。
- `src/dataflow/` 配下の実装コードを変更しない（これは `Dev-Dataflow-ServiceCoding` が行う）。
- `src/test/dataflow/` 配下のテストコードを変更しない（これは `Dev-Dataflow-TestCoding` / `Dev-Dataflow-ServiceCoding` が行う）。
- サービスカタログから確認できない Azure リソースを捏造しない（不明は `TBD` または Questions）。
- 既存のプロダクションリソースを削除・変更するコマンドを実行しない。
- Azure リソースの実際の作成（スクリプト実行）は行わない（それは Step 1.2 の責務）。

## Agent 固有の Skills 依存
- `azure-cli-deploy-scripts`：Azure CLI スクリプトの共通仕様（prep/create/verify 3点セット・冪等性パターン・CLI 利用不可時フォールバック）を参照する。
- `azure-region-policy`：Azure リージョン優先順位ポリシー（§1 標準リージョン）を参照する。
