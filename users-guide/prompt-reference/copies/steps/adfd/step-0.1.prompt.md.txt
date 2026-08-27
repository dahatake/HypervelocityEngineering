{root_ref}

{app_arch_scope_section}
## 目的
AAS の統合データモデルとアプリケーションカタログに基づき、データフロー処理のデータモデル定義書を作成する。

## 入力
- `docs/catalog/data-model.md`
- `docs/catalog/app-catalog.md`

## 出力
- `docs/dataflow/dataflow-data-model.md`

{existing_artifact_policy}

## Custom Agent
`Arch-Dataflow-DataModel` を使用

## 依存
- なし（ADFD の DAG 根）

## 完了条件
- `docs/dataflow/dataflow-data-model.md` が作成されている
{completion_instruction}{additional_section}
