{root_ref}

{app_arch_scope_section}
## 目的
テストコードを通過させるバッチジョブ本実装（TDD GREEN フェーズ）を行う。

## 入力
- `test/batch/{jobId}-{jobNameSlug}.Tests/`（テストコード）
- `docs/batch/jobs/{jobId}-{jobNameSlug}-spec.md`（ジョブ詳細仕様書）
- `docs/batch/batch-service-catalog.md`
- `docs/batch/batch-test-strategy.md`（テスト戦略書）
- `docs/batch/batch-monitoring-design.md`（監視設計書: 構造化ログ・アラート要件）
- `docs/azure/azure-services-data.md`（データストア接続情報）

## 出力
- `src/batch/{jobId}-{jobNameSlug}/` 配下の本実装コード

## Custom Agent
`Dev-Batch-ServiceCoding` を使用

## 依存
- Step.2.1（TDD RED: テストコード作成）が `abdv:done` であること

## 完了条件
- `dotnet test` が全テスト PASS（TDD GREEN）になっている

## TDD GREEN リトライルール
- テストが PASS にならない場合、最大 {tdd_max_retries} 回まで実装を修正して再試行する
- {tdd_max_retries} 回で全 PASS にならない場合: `abdv:blocked` ラベルを付与し、未 PASS テスト一覧と試行回数を Issue コメントで報告する
- テストコード（`test/batch/`）は原則変更禁止
{completion_instruction}{rg_section}{job_section}{additional_section}