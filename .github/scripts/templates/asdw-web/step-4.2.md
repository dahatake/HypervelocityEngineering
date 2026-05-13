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
- `src/app/`, `src/api/`, `infra/`, `config/`, `.github/workflows/`

## 出力
- `docs/azure/dependency-review-report.md`

{existing_artifact_policy}

## Custom Agent
`QA-AzureDependencyReview` を使用

## 依存
- Step.3.3（Playwright E2E テスト）が `asdw-web:done` であること
- Step.4.1 と並列実行可能

## 完了条件
- `docs/azure/dependency-review-report.md` が作成されている
{completion_instruction}{app_id_section}{additional_section}
