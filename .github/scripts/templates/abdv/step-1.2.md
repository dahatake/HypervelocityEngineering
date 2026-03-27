{root_ref}
## 目的
データサービス選定結果を根拠に、Azure CLI で冪等的に Azure データ系リソースを作成する。

## 入力
- `docs/azure/AzureServices-data.md`
- `docs/batch/batch-service-catalog.md`
- `docs/batch/batch-monitoring-design.md`（監視設計: データリソースの冗長性・バックアップ要件）

## 出力
- `infra/azure/batch/create-batch-resources.sh`（Azure CLI スクリプト）

## Custom Agent
`Dev-Batch-Deploy` を使用

## 依存
- Step.1.1（データサービス選定）が `abdv:done` であること

## 完了条件
- Azure データ系リソースが作成/確認されている
- 完了時に自身に `abdv:done` ラベルを付与すること{rg_section}{job_section}{additional_section}