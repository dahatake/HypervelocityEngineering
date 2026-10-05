{root_ref}

{app_arch_scope_section}
## 目的
デプロイ済みAzureリソースを棚卸しし、Azure Well-Architected Framework（5本柱）と Azure Security Benchmark v3 を根拠にアーキテクチャ/セキュリティをレビューして、日本語のMermaid図付きレポートを生成する（APP-ID 指定時はスコープ内のリソースのみ）。

## 入力
- リソースグループ名: `{resource_group}`
- `docs/catalog/use-case-catalog.md`
- `docs/catalog/service-catalog-matrix.md`
- `docs/azure/azure-services-compute.md`
- `docs/azure/azure-services-data.md`
- `docs/azure/azure-services-additional.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

## 出力
- `docs/azure/azure-architecture-review-report.md`

- Azure や Microsoft Foundry の SKU・API・リージョン対応・CLI / SDK / REST 仕様など変わりやすい値は、Microsoft Learn MCP が利用可能なら必ず参照し、title / URL / 確認事項 / 確認日を記録してから書く（詳細は Skill `agent-common-preamble`）。参照できない値は `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。

{existing_artifact_policy}

## Custom Agent
`QA-AzureArchitectureReview` を使用

## 依存
- Step.4.4（Playwright E2E テスト）が `asdw-web:done` であること
- Step.5.2 と並列実行可能

## 完了条件
- `docs/azure/azure-architecture-review-report.md` が作成されている
{completion_instruction}{app_id_section}{additional_section}
