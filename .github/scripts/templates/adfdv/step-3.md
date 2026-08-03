{root_ref}

{app_arch_scope_section}
## 目的
データフローアプリ実装コードを Azure Functions またはコンテナとして Azure にデプロイする。

## 入力
- `src/` または `functions/` 配下の本実装コード
- `docs/azure/azure-services-data.md`（データストア設計）
- `docs/dataflow/dataflow-service-catalog.md`（サービスカタログ）
- `docs/dataflow/dataflow-monitoring-design.md`（監視設計書: アラート・ログ・スケーリング設定）
- `docs/azure/azure-services-compute.md`（コンピュート設計: 存在する場合のみ参照）

## 出力
- Azure Functions / コンテナのデプロイ完了
- CI/CD パイプライン設定（`.github/workflows/deploy-batch-functions.yml` 等）
- `src/infra/azure/dataflow/README.md`（インフラ手順・環境変数一覧・トラブルシューティング）

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログ（work-status 系成果物）または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。必要に応じて `az ... -h` / パッケージマネージャ / 公式 CLI help を補助確認として使う。

{existing_artifact_policy}

## Custom Agent
`Dev-Dataflow-FunctionsDeploy` を使用

## 依存
- {dep}

## 完了条件
- データフローアプリが Azure 上で稼働している
{completion_instruction}{rg_section}{job_section}{additional_section}