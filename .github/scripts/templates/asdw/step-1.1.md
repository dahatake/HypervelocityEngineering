{root_ref}
## 目的
Polyglot Persistenceに基づき、対象エンティティの最適Azureデータストア選定と根拠/整合性方針を文書化する（APP-ID 指定時はスコープ内のエンティティのみ）。

## 入力
- `docs/data-model.md`
- `docs/service-list.md`
- `docs/domain-analytics.md`
- `docs/app-list.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- （任意）`docs/templates/agent-playbook.md`

## 出力
- `docs/azure/AzureServices-data.md`

## Custom Agent
`Dev-Microservice-Azure-DataDesign` を使用

## 完了条件
- `docs/azure/AzureServices-data.md` が作成されている
- 完了時に自身に `asdw:done` ラベルを付与すること{app_id_section}{additional_section}