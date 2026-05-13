{root_ref}

{app_arch_scope_section}
## 目的
バッチジョブ実装コードを Azure Functions またはコンテナとして Azure にデプロイする。

## 入力
- `src/` または `functions/` 配下の本実装コード
- `docs/azure/azure-services-data.md`（データストア設計）
- `docs/batch/batch-service-catalog.md`（サービスカタログ）
- `docs/batch/batch-monitoring-design.md`（監視設計書: アラート・ログ・スケーリング設定）
- `docs/azure/azure-services-compute.md`（コンピュート設計: 存在する場合のみ参照）

## 出力
- Azure Functions / コンテナのデプロイ完了
- CI/CD パイプライン設定（`.github/workflows/deploy-batch-functions.yml` 等）
- `infra/azure/batch/README.md`（インフラ手順・環境変数一覧・トラブルシューティング）

{existing_artifact_policy}

## Custom Agent
`Dev-Batch-FunctionsDeploy` を使用

## 依存
- {dep}

## 完了条件
- バッチジョブが Azure 上で稼働している
{completion_instruction}{rg_section}{job_section}{additional_section}