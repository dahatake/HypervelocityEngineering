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

- Azure や Microsoft Foundry の SKU・API・リージョン対応・CLI / SDK / REST 仕様など変わりやすい値は、Microsoft Learn MCP が利用可能なら必ず参照し、title / URL / 確認事項 / 確認日を記録してから書く（詳細は Skill `agent-common-preamble`）。参照できない値は `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。

{existing_artifact_policy}

## Custom Agent
`Dev-Dataflow-FunctionsDeploy` を使用

## 依存
- {dep}

## 完了条件
- データフローアプリが Azure 上で稼働している
{completion_instruction}{rg_section}{job_section}{additional_section}