{root_ref}
## 目的
TDD テスト仕様書を根拠に、バッチジョブの失敗するテストコード（TDD RED フェーズ）を作成する。

⚠️ **注意**: `{jobId}` はこの Issue の `## 対象バッチジョブ ID` セクションに記載のジョブ ID を使用すること（例: `BJ-001`）。

## 入力
- `docs/test-specs/{jobId}-test-spec.md`（TDD テスト仕様書。ABD ワークフローの Arch-Batch-TDDTestSpec が生成）
- `docs/batch/batch-job-catalog.md`
- `docs/batch/batch-service-catalog.md`
- `docs/batch/batch-test-strategy.md`（テスト戦略書）
- `docs/batch/jobs/{jobId}-{jobNameSlug}-spec.md`（ジョブ詳細仕様書）
- `docs/batch/batch-monitoring-design.md`（監視設計書）

## 出力
- `test/batch/{jobId}-{jobNameSlug}.Tests/` 配下のテストコード（xUnit / C#）

## Custom Agent
`Dev-Batch-TestCoding` を使用

## 依存
- {dep}

## 完了条件
- テストコードが作成され、`dotnet test` で失敗（TDD RED）が確認されている
- 完了時に自身に `abdv:done` ラベルを付与すること{rg_section}{job_section}{additional_section}