{root_ref}

{app_arch_scope_section}
## 目的
サービスカタログとデータモデルを根拠に、データフロー処理固有のテスト戦略書（冪等性テスト・データ品質テスト・大量データテスト・障害注入テスト・パフォーマンステスト方針）を作成する。

## 入力
- `docs/dataflow/dataflow-service-catalog.md`
- `docs/dataflow/dataflow-data-model.md`

## 出力
- `docs/dataflow/dataflow-test-strategy.md`

{existing_artifact_policy}

## Custom Agent
`Arch-Dataflow-TestStrategy` を使用

## 依存
- Step.4（サービスカタログ）が `adfd:done` であること

## 完了条件
- `docs/dataflow/dataflow-test-strategy.md` が作成されている
{completion_instruction}{additional_section}