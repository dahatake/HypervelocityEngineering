{root_ref}

{app_arch_scope_section}
## 目的
ユースケース内の対象マイクロサービスについて、最適な Azure コンピュート（ホスティング）を選定し、根拠・代替案・前提・未決事項を設計書に記録する（APP-ID 指定時はスコープ内のサービスのみ）。

## 入力
- リソースグループ名: `{resource_group}`
- `docs/azure/azure-services-data.md`（Step.1.1 出力 — データ系サービスの planned design）
- `docs/catalog/service-catalog.md`
- `docs/catalog/use-case-catalog.md`
- `docs/catalog/data-model.md`
- `docs/catalog/service-catalog-matrix.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

> 本 Step は local-first / live-last DAG の local フェーズに属し、Deploy 前に実行される。Step.1.3 が生成する `docs/azure/service-catalog.md` など deploy 後の live 成果物を入力にしない。planned design のみを根拠に選定し、未確定事項は推測せず未決事項として記録する。

## 出力
- `docs/azure/azure-services-compute.md`

- Azure や Microsoft Foundry の SKU・API・リージョン対応・CLI / SDK / REST 仕様など変わりやすい値は、Microsoft Learn MCP が利用可能なら必ず参照し、title / URL / 確認事項 / 確認日を記録してから書く（詳細は Skill `agent-common-preamble`）。参照できない値は `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。

{existing_artifact_policy}

## Custom Agent
`Dev-Microservice-Azure-ComputeDesign` を使用

## 依存
- Step.2.3（追加サービスのテストコード生成）が `asdw-web:done` であること

## 完了条件
- `docs/azure/azure-services-compute.md` が作成されている
{completion_instruction}{app_id_section}{additional_section}
