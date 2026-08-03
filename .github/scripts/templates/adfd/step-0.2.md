{root_ref}

{app_arch_scope_section}
## 目的
データフローデータモデルとサービスカタログマトリクスに基づき、データフローアプリ（ジョブ）カタログを作成する。

## 入力
- `docs/dataflow/dataflow-data-model.md`
- `docs/catalog/app-catalog.md`
- `docs/catalog/service-catalog-matrix.md`

## 出力
- `docs/dataflow/dataflow-app-catalog.md`

{existing_artifact_policy}

## Custom Agent
`Arch-Dataflow-AppCatalog` を使用

## 依存
- Step.0.1（データモデル定義書）が `adfd:done` であること

## 完了条件
- `docs/dataflow/dataflow-app-catalog.md` が作成され、`## 1. ジョブ一覧表` を含んでいる
{completion_instruction}{additional_section}
