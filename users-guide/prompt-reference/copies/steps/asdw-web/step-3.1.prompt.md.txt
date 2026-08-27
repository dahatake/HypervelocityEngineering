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

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログ（work-status 系成果物）または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。必要に応じて `az ... -h` / パッケージマネージャ / 公式 CLI help を補助確認として使う。

{existing_artifact_policy}

## Custom Agent
`Dev-Microservice-Azure-ComputeDesign` を使用

## 依存
- Step.2.3（追加サービスのテストコード生成）が `asdw-web:done` であること

## 完了条件
- `docs/azure/azure-services-compute.md` が作成されている
{completion_instruction}{app_id_section}{additional_section}
