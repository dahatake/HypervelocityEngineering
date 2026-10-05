{root_ref}

{app_arch_scope_section}
## 目的
テスト戦略書・ジョブ詳細仕様書・監視設計書を根拠に、注入された対象データフローアプリ（`{key}`）1件のTDD用テスト仕様書を作成する。

## 入力
- `docs/catalog/test-strategy.md`
- `docs/catalog/service-catalog-matrix.md`
- `docs/dataflow/apps/{key}-spec.md`（対象 APP の仕様書。`dataflow_catalog` の `{key}` は APP-ID で、`{appId}` がその別名。Job-ID とは区別する）
- `docs/dataflow/dataflow-monitoring-design.md`

## 出力
- `docs/test-specs/{key}-test-spec.md`（対象 `{key}` ごとに1ファイル）

{existing_artifact_policy}

## Custom Agent
`Arch-Dataflow-TDD-TestSpec` を使用

## 依存
- Step.1（ジョブ詳細仕様書）が `adfd:done` であること（AND依存）
- Step.2（監視・運用設計書）が `adfd:done` であること（AND依存）

## 完了条件
- 対象 APP `{key}` の仕様書に含まれるすべてのジョブのテストが、ジョブカタログの該当エントリに基づいて1ファイルへ記載されている
{completion_instruction}{additional_section}