{root_ref}

{app_arch_scope_section}
## 目的
データフローアプリカタログに基づき、各ジョブの実行に必要な Azure サービスマッピング・DLQ 設定・依存関係マトリクスを作成する。

## 入力
- `docs/dataflow/dataflow-app-catalog.md`
- `docs/catalog/service-catalog-matrix.md`

## 出力
- `docs/dataflow/dataflow-service-catalog.md`

{existing_artifact_policy}

## Custom Agent
`Arch-Dataflow-ServiceCatalog` を使用

## 依存
- Step.0.2（データフローアプリカタログ）が `adfd:done` であること

## 完了条件
- `docs/dataflow/dataflow-service-catalog.md` が作成され、`## 2. ジョブ → Azure サービスマッピング表` を含んでいる
{completion_instruction}{additional_section}
