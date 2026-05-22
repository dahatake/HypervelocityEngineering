{root_ref}

{app_arch_scope_section}
## 目的
ジョブ設計書・データモデル・ドメイン分析を統合してデータフローアプリ版サービスカタログを作成する。

## 入力
- `docs/dataflow/dataflow-app-catalog.md`
- `docs/dataflow/dataflow-data-model.md`
- `docs/dataflow/dataflow-domain-analytics.md`

## 出力
- `docs/dataflow/dataflow-service-catalog.md`

{existing_artifact_policy}

## Custom Agent
`Arch-Dataflow-ServiceCatalog` を使用

## 依存
- Step.3（ジョブ設計書）が `adfd:done` であること

## 完了条件
- `docs/dataflow/dataflow-service-catalog.md` が作成されている
{completion_instruction}{additional_section}