{root_ref}

{app_arch_scope_section}
## 目的
Step.1.1 で作成したリソース作成スクリプトを実行し、Azure データ系リソースを冪等的に作成・検証する。

## 入力
- `src/infra/azure/dataflow/create-batch-resources.sh`（Step.1.1 の成果物）
- `src/infra/azure/dataflow/verify-batch-resources.sh`（Step.1.1 の成果物）
- `docs/dataflow/dataflow-service-catalog.md`
- `docs/dataflow/dataflow-monitoring-design.md`（監視設計: データリソースの冗長性・バックアップ要件）

## 出力
- Azure データ系リソースの作成・検証完了
- 実行・検証ログ（`{WORK}deploy-work-status.md`）

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログ（work-status 系成果物）または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。必要に応じて `az ... -h` / パッケージマネージャ / 公式 CLI help を補助確認として使う。

{existing_artifact_policy}

## Custom Agent
`Dev-Dataflow-DataDeploy` を使用

## 依存
- Step.1.1（データサービス選定）が `adfdv:done` であること

## 完了条件
- Azure データ系リソースが作成/確認されている
- `src/infra/azure/dataflow/verify-batch-resources.sh` の実行結果が全項目 PASS であること
{completion_instruction}{rg_section}{job_section}{additional_section}