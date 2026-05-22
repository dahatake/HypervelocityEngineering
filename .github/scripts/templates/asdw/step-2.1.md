<!-- DEPRECATED: このテンプレートは templates/asdw-web/step-2.1.md に移動しました。 -->
{root_ref}
## 目的
ユースケース内の対象マイクロサービスについて、最適な Azure コンピュート（ホスティング）を選定し、根拠・代替案・前提・未決事項を設計書に記録する（APP-ID 指定時はスコープ内のサービスのみ）。

## 入力
- リソースグループ名: `{resource_group}`
- `docs/catalog/service-catalog.md`
- `docs/catalog/use-case-catalog.md`
- `docs/catalog/data-model.md`
- `docs/catalog/service-catalog-matrix.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

## 出力
- `docs/azure/azure-services-compute.md`

## Custom Agent
`Dev-Microservice-Azure-ComputeDesign` を使用

## 依存
- Step.1（データコンテナ）が `asdw:done` であること

## 完了条件
- `docs/azure/azure-services-compute.md` が作成されている
{completion_instruction}{app_id_section}{additional_section}