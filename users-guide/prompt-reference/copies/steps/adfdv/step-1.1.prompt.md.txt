{root_ref}

{app_arch_scope_section}
## 目的
データフローアプリ設計書・サービスカタログを根拠に、必要な Azure データ系リソースを特定し、リソース作成スクリプトと検証スクリプトを準備する。

## 入力
- `docs/dataflow/dataflow-domain-analytics.md`
- `docs/dataflow/dataflow-data-source-analysis.md`
- `docs/dataflow/dataflow-data-model.md`
- `docs/dataflow/dataflow-app-catalog.md`
- `docs/dataflow/dataflow-service-catalog.md`
- `docs/dataflow/dataflow-test-strategy.md`（テスト戦略書: データストア選定の参考）

## 出力
- `src/infra/azure/dataflow/create-batch-resources.sh`（Azure CLI リソース作成スクリプト）
- `src/infra/azure/dataflow/verify-batch-resources.sh`（Azure CLI リソース検証スクリプト）

- Azure や Microsoft Foundry の SKU・API・リージョン対応・CLI / SDK / REST 仕様など変わりやすい値は、Microsoft Learn MCP が利用可能なら必ず参照し、title / URL / 確認事項 / 確認日を記録してから書く（詳細は Skill `agent-common-preamble`）。参照できない値は `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。

{existing_artifact_policy}

## Custom Agent
`Dev-Dataflow-DataServiceSelect` を使用

## 依存
- 依存なし（最初の Step）

## 完了条件
- `src/infra/azure/dataflow/create-batch-resources.sh` が作成されている
- `src/infra/azure/dataflow/verify-batch-resources.sh` が作成されている
{completion_instruction}{rg_section}{job_section}{additional_section}