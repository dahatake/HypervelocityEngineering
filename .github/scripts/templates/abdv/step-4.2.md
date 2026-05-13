{root_ref}

{app_arch_scope_section}
## 目的
サービスカタログ準拠で Azure 依存（参照・設定・IaC）を証跡付きで点検し、設計書との整合性を確認する。

## 入力
- `docs/azure/azure-services-data.md`
- `docs/batch/batch-service-catalog.md`
- `docs/batch/batch-monitoring-design.md`（監視設計書: アラート・ダッシュボード設定の整合確認）
- `docs/azure/azure-services-compute.md`（存在する場合のみ参照）

## 出力
- 整合性チェックレポート（`docs/azure/dependency-review.md`）

{existing_artifact_policy}

## Custom Agent
`QA-AzureDependencyReview` を使用

## 依存
- Step.4.1 と同じ前段 Step が `abdv:done` であること（Step.3 → 並列起動）

## 完了条件
- `docs/azure/dependency-review.md` が作成されている
{completion_instruction}{rg_section}{job_section}{additional_section}