{root_ref}

{app_arch_scope_section}
## 目的
テストコードを通過させるデータフローアプリ本実装（TDD GREEN フェーズ）を行う。

## 入力
- `src/test/dataflow/{jobId}-{jobNameSlug}.Tests/`（テストコード）
- `docs/dataflow/apps/{jobId}-{jobNameSlug}-spec.md`（ジョブ詳細仕様書）
- `docs/dataflow/dataflow-service-catalog.md`
- `docs/dataflow/dataflow-test-strategy.md`（テスト戦略書）
- `docs/dataflow/dataflow-monitoring-design.md`（監視設計書: 構造化ログ・アラート要件）
- `docs/azure/azure-services-data.md`（データストア接続情報）

## 出力
- `src/dataflow/{jobId}-{jobNameSlug}/` 配下の本実装コード

{existing_artifact_policy}

## Custom Agent
`Dev-Dataflow-ServiceCoding` を使用

## 依存
- Step.2.1（TDD RED: テストコード作成）が `adfdv:done` であること

## 完了条件
- `dotnet test` が全テスト PASS（TDD GREEN）になっている

## TDD GREEN リトライルール
- テストが PASS にならない場合、最大 {tdd_max_retries} 回まで実装を修正して再試行する
- {tdd_max_retries} 回で全 PASS にならない場合: `adfdv:blocked` ラベルを付与し、未 PASS テスト一覧と試行回数を Issue コメントで報告する
- テストコード（`src/test/dataflow/`）は原則変更禁止
{completion_instruction}{rg_section}{job_section}{additional_section}