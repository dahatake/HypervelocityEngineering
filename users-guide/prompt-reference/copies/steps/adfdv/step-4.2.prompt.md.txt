{root_ref}

{app_arch_scope_section}
## 目的
サービスカタログ準拠で Azure 依存（参照・設定・IaC）を証跡付きで点検し、設計書との整合性を確認する。

## 入力
- `docs/azure/azure-services-data.md`
- `docs/dataflow/dataflow-service-catalog.md`
- `docs/dataflow/dataflow-monitoring-design.md`（監視設計書: アラート・ダッシュボード設定の整合確認）
- `docs/azure/azure-services-compute.md`（存在する場合のみ参照）

## 出力
- 整合性チェックレポート（`docs/azure/dependency-review.md`）

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログ（work-status 系成果物）または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。必要に応じて `az ... -h` / パッケージマネージャ / 公式 CLI help を補助確認として使う。

{existing_artifact_policy}

## Custom Agent
`QA-AzureDependencyReview` を使用

## 依存
- Step.4.1 と同じ前段 Step が `adfdv:done` であること（Step.3 → 並列起動）

## 完了条件
- `docs/azure/dependency-review.md` が作成されている
{completion_instruction}{rg_section}{job_section}{additional_section}