{root_ref}

{app_arch_scope_section}
## 目的
テスト戦略書・ジョブ詳細仕様書・監視設計書を根拠に、TDD用テスト仕様書をジョブごとに作成する。

## 入力
- `docs/dataflow/dataflow-test-strategy.md`
- `docs/dataflow/dataflow-service-catalog.md`
- `docs/dataflow/apps/{jobId}-*-spec.md`（ジョブ詳細仕様書）
- `docs/dataflow/dataflow-monitoring-design.md`

## 出力
- `docs/test-specs/{jobId}-test-spec.md`（ジョブごとに1ファイル）

{existing_artifact_policy}

## Custom Agent
`Arch-Dataflow-TDD-TestSpec` を使用

## 依存
- Step.6.1（ジョブ詳細仕様書）が `adfd:done` であること（AND依存）
- Step.6.2（監視・運用設計書）が `adfd:done` であること（AND依存）

## 完了条件
- テスト仕様書がジョブカタログに基づいて全ジョブ分作成されている
{completion_instruction}{additional_section}