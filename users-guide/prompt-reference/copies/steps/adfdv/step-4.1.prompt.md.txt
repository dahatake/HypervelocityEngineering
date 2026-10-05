{root_ref}

{app_arch_scope_section}
## 目的
デプロイ済みの Azure リソース構成を Azure Well-Architected Framework（WAF）5本柱で評価する。

## 入力
- デプロイ済みの Azure リソース（Azure Portal / CLI で確認）
- `docs/azure/azure-services-data.md`
- `docs/dataflow/dataflow-service-catalog.md`
- `docs/dataflow/dataflow-monitoring-design.md`（監視設計書: WAF「運用の優秀性」柱の根拠）
- `docs/azure/azure-services-compute.md`（存在する場合のみ参照）

## 出力
- WAF レビューレポート（`docs/azure/waf-review.md`）

- Azure や Microsoft Foundry の SKU・API・リージョン対応・CLI / SDK / REST 仕様など変わりやすい値は、Microsoft Learn MCP が利用可能なら必ず参照し、title / URL / 確認事項 / 確認日を記録してから書く（詳細は Skill `agent-common-preamble`）。参照できない値は `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。

{existing_artifact_policy}

## Custom Agent
`QA-AzureArchitectureReview` を使用

## 依存
- {dep}

## 完了条件
- `docs/azure/waf-review.md` が作成されている
{completion_instruction}{rg_section}{job_section}{additional_section}