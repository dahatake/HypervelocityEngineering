{root_ref}

{app_arch_scope_section}
## 目的
TDD テスト仕様書を根拠に、データフローアプリの失敗するテストコード（TDD RED フェーズ）を作成する。

⚠️ **注意**: `{jobId}` はこの Issue の `## 対象データフローアプリ ID` セクションに記載のジョブ ID を使用すること（例: `BJ-001`）。

## 入力
- `docs/test-specs/{jobId}-test-spec.md`（TDD テスト仕様書。ADFD ワークフローの Arch-Dataflow-TDDTestSpec が生成）
- `docs/dataflow/dataflow-app-catalog.md`
- `docs/dataflow/dataflow-service-catalog.md`
- `docs/dataflow/dataflow-test-strategy.md`（テスト戦略書）
- `docs/dataflow/apps/{jobId}-{jobNameSlug}-spec.md`（ジョブ詳細仕様書）
- `docs/dataflow/dataflow-monitoring-design.md`（監視設計書）

## 出力
- `src/test/dataflow/{jobId}-{jobNameSlug}.Tests/` 配下のテストコード（xUnit / C#）

{existing_artifact_policy}

## Custom Agent
`Dev-Dataflow-TestCoding` を使用

## 依存
- {dep}

## 完了条件
- テストコードが作成され、`dotnet test` で失敗（TDD RED）が確認されている
{completion_instruction}{rg_section}{job_section}{additional_section}