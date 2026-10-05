{root_ref}

{app_arch_scope_section}
## 目的
サービスカタログ準拠で Azure 依存（参照・設定・IaC）を証跡付きで点検し、必要なら最小差分で修正する（APP-ID 指定時はスコープ内の依存のみ）。

## 入力
- リソースグループ名: `{resource_group}`
- `docs/catalog/service-catalog-matrix.md`
- `docs/azure/azure-services-compute.md`
- `docs/azure/azure-services-data.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- `src/app/`, `src/api/`, `src/infra/`, `config/`, `.github/workflows/`

## 出力
- `docs/azure/dependency-review-report.md`

- Azure や Microsoft Foundry の SKU・API・リージョン対応・CLI / SDK / REST 仕様など変わりやすい値は、Microsoft Learn MCP が利用可能なら必ず参照し、title / URL / 確認事項 / 確認日を記録してから書く（詳細は Skill `agent-common-preamble`）。参照できない値は `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。

{existing_artifact_policy}

## Custom Agent
`QA-AzureDependencyReview` を使用

## 依存
- Step.4.4（Playwright E2E テスト）が `asdw-web:done` であること
- Step.5.1 と並列実行可能

## 完了条件
- `docs/azure/dependency-review-report.md` が作成されている
{completion_instruction}{app_id_section}{additional_section}
