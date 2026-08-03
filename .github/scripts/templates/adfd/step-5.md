{root_ref}

{app_arch_scope_section}
## 目的
全社テスト戦略・データフローアプリカタログ・データフローサービスカタログに基づき、データフロー処理固有のテスト戦略書を作成する。

## 入力
- `docs/catalog/test-strategy.md`
- `docs/dataflow/dataflow-app-catalog.md`
- `docs/dataflow/dataflow-service-catalog.md`

## 出力
- `docs/dataflow/dataflow-test-strategy.md`

{existing_artifact_policy}

## Custom Agent
`Arch-Dataflow-TestStrategy` を使用

## 依存
- Step.4（データフローサービスカタログ）が `adfd:done` であること

## 完了条件
- `docs/dataflow/dataflow-test-strategy.md` が作成され、`## 4. テストダブル戦略` に Azurite / Testcontainers の利用有無が明記されている
{completion_instruction}{additional_section}
