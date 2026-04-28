{root_ref}

{app_arch_scope_section}
## 目的
サービス定義書の「外部依存・統合」から、追加で必要な Azure サービス（AI/認証/統合/運用等）を選定し、根拠（Microsoft Learn）付きで記録する（APP-ID 指定時はスコープ内のサービスのみ）。

## 入力
- リソースグループ名: `{resource_group}`
- `docs/catalog/use-case-catalog.md`
- `docs/catalog/service-catalog.md`
- `docs/services/{サービスID}-{サービス名}-description.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- 既存採用済み（追加提案から除外）:
  - `docs/azure/azure-services-compute.md`
  - `docs/azure/azure-services-data.md`

## 出力
- `docs/azure/azure-services-additional.md`

## Custom Agent
`Dev-Microservice-Azure-AddServiceDesign` を使用

## 依存
- Step.2.1（Azure コンピュート選定）が `asdw-web:done` であること

## 完了条件
- `docs/azure/azure-services-additional.md` が作成されている
{completion_instruction}{app_id_section}{additional_section}