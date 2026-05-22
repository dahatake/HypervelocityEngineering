{root_ref}

{app_arch_scope_section}
## 目的
サービスカタログとジョブ設計に基づき、ジョブ毎の詳細仕様書を作成する。

## 入力
- `docs/dataflow/dataflow-service-catalog.md`
- `docs/dataflow/dataflow-app-catalog.md`
- `docs/dataflow/dataflow-data-model.md`

## 出力
- `docs/dataflow/apps/{jobId}-{jobNameSlug}-spec.md`（ジョブごとに1ファイル）

{existing_artifact_policy}

## Custom Agent
`Arch-Dataflow-AppSpec` を使用

## 依存
- {dep}

## 完了条件
- 各ジョブの詳細仕様書が全て作成されている
{completion_instruction}{additional_section}