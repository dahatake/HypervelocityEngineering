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

## Custom Agent
`QA-AzureArchitectureReview` を使用

## 依存
- Step.3.2（Web アプリ Deploy）が `asdw-web:done` であること
- Step.4.2 と並列実行可能

## 完了条件
- `docs/azure/azure-architecture-review-report.md` が作成されている
{completion_instruction}{app_id_section}{additional_section}
