{root_ref}

{app_arch_scope_section}
## 目的
Step.1.1 で作成したリソース作成スクリプトを実行し、Azure データ系リソースを冪等的に作成・検証する。

## 入力
- `infra/azure/batch/create-batch-resources.sh`（Step.1.1 の成果物）
- `infra/azure/batch/verify-batch-resources.sh`（Step.1.1 の成果物）
- `docs/batch/batch-service-catalog.md`
- `docs/batch/batch-monitoring-design.md`（監視設計: データリソースの冗長性・バックアップ要件）

## 出力
- Azure データ系リソースの作成・検証完了
- 実行・検証ログ（`{WORK}deploy-work-status.md`）

## Custom Agent
`Dev-Batch-DataDeploy` を使用

## 依存
- Step.1.1（データサービス選定）が `abdv:done` であること

## 完了条件
- Azure データ系リソースが作成/確認されている
- `infra/azure/batch/verify-batch-resources.sh` の実行結果が全項目 PASS であること
{completion_instruction}{rg_section}{job_section}{additional_section}