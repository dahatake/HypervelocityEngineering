{root_ref}

{app_arch_scope_section}
## 目的
バッチジョブ設計書・サービスカタログを根拠に、データ系 Azure サービスの選定と設計を行う。

## 入力
- `docs/batch/batch-domain-analytics.md`
- `docs/batch/batch-data-source-analysis.md`
- `docs/batch/batch-data-model.md`
- `docs/batch/batch-job-catalog.md`
- `docs/batch/batch-service-catalog.md`
- `docs/batch/batch-test-strategy.md`（テスト戦略書: データストア選定の参考）

## 出力
- `docs/azure/azure-services-data.md`（データストア設計）

## Custom Agent
`Dev-Batch-Deploy` を使用

## 依存
- 依存なし（最初の Step）

## 完了条件
- `docs/azure/azure-services-data.md` が作成または更新されている
{completion_instruction}{rg_section}{job_section}{additional_section}