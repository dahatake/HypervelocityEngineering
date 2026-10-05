{root_ref}

{app_arch_scope_section}
## 目的
Polyglot Persistenceに基づき、対象エンティティの最適Azureデータストア選定と根拠/整合性方針を文書化する（APP-ID 指定時はスコープ内のエンティティのみ）。

## 入力
- `docs/catalog/data-model.md`
- `docs/catalog/service-catalog.md`
- `docs/catalog/domain-analytics.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- （任意）`docs/templates/agent-playbook.md`

## 出力
- `docs/azure/azure-services-data.md`

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure や Microsoft Foundry の SKU・API・リージョン対応・CLI / SDK / REST 仕様など変わりやすい値は、Microsoft Learn MCP が利用可能なら必ず参照し、title / URL / 確認事項 / 確認日を記録してから書く（詳細は Skill `agent-common-preamble`）。参照できない値は `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。

{existing_artifact_policy}

## Custom Agent
`Dev-Microservice-Azure-DataDesign` を使用

## 完了条件
- `docs/azure/azure-services-data.md` が作成されている
{completion_instruction}{app_id_section}{additional_section}