{root_ref}

{app_arch_scope_section}
## 目的
バッチジョブ設計書・サービスカタログを根拠に、必要な Azure データ系リソースを特定し、リソース作成スクリプトと検証スクリプトを準備する。

## 入力
- `docs/batch/batch-domain-analytics.md`
- `docs/batch/batch-data-source-analysis.md`
- `docs/batch/batch-data-model.md`
- `docs/batch/batch-job-catalog.md`
- `docs/batch/batch-service-catalog.md`
- `docs/batch/batch-test-strategy.md`（テスト戦略書: データストア選定の参考）

## 出力
- `infra/azure/batch/create-batch-resources.sh`（Azure CLI リソース作成スクリプト）
- `infra/azure/batch/verify-batch-resources.sh`（Azure CLI リソース検証スクリプト）

## Custom Agent
`Dev-Batch-DataServiceSelect` を使用

## 依存
- 依存なし（最初の Step）

## 完了条件
- `infra/azure/batch/create-batch-resources.sh` が作成されている
- `infra/azure/batch/verify-batch-resources.sh` が作成されている
{completion_instruction}{rg_section}{job_section}{additional_section}