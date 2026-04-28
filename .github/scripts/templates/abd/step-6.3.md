{root_ref}

{app_arch_scope_section}
## 目的
テスト戦略書・ジョブ詳細仕様書・監視設計書を根拠に、TDD用テスト仕様書をジョブごとに作成する。

## 入力
- `docs/batch/batch-test-strategy.md`
- `docs/batch/batch-service-catalog.md`
- `docs/batch/jobs/{jobId}-*-spec.md`（ジョブ詳細仕様書）
- `docs/batch/batch-monitoring-design.md`

## 出力
- `docs/test-specs/{jobId}-test-spec.md`（ジョブごとに1ファイル）

## Custom Agent
`Arch-Batch-TDD-TestSpec` を使用

## 依存
- Step.6.1（ジョブ詳細仕様書）が `abd:done` であること（AND依存）
- Step.6.2（監視・運用設計書）が `abd:done` であること（AND依存）

## 完了条件
- テスト仕様書がジョブカタログに基づいて全ジョブ分作成されている
{completion_instruction}{additional_section}