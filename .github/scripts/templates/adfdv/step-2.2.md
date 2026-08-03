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

## 生成テストの実行環境
- `src/test/dataflow/{jobId}-{jobNameSlug}.Tests/` のテストはローカル端末 / CI で `dotnet test` により決定的に PASS すること。
- GREEN 化のために Azure Storage / SQL / Cosmos DB / Service Bus 等へ実接続するテストへ変更しない。外部 I/O は Azurite / Testcontainers / Mock / Stub に切り分ける。
- 実装コードは Azure Functions としてデプロイ可能にしつつ、接続先・認証・キュー名・コンテナ名・リソース名は環境変数または設定ファイルから読み込む。秘密情報をコード、README、ログにハードコードしない。

{existing_artifact_policy}

## Custom Agent
`Dev-Dataflow-ServiceCoding` を使用

## 依存
- Step.2.1（TDD RED: テストコード作成）が `adfdv:done` であること

## 完了条件
- `dotnet test` が全テスト PASS（TDD GREEN）になっている

## TDD GREEN リトライルール
- テストが PASS にならない場合、最大 {tdd_max_retries} 回まで実装を修正して再試行する（Skill `tdd-green-retry-strategy` 準拠：各回は前回と異なるアプローチを選び、失敗の都度に根本原因を特定し Microsoft Learn MCP（C# / .NET / SDK）で解決策を確認してから次手を決める）
- {tdd_max_retries} 回で全 PASS にならない場合: `adfdv:blocked` ラベルを付与し、未 PASS テスト一覧と試行回数を Issue コメントで報告する
- テストコード（`src/test/dataflow/`）は原則変更禁止
## TDD テスト結果レポート（必須）
- 出力先: `tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md`
- 必須ラベル: `Schema-Version`, `Evidence-Status`, `TDD-Judgement`, `Secret-Redaction`, `Test-Files-Changed`
- `src/test/` はテストコード専用、`tests/` はテスト結果レポート専用とする。
- 固定スキーマは Skill `tdd-red-green-reality` の `tdd-test-report.md` テンプレートに従う。ラベルは必ず `- Label: value` 形式で書き、`Label: value` のプレーン行にしない。
- 見出し名は `## Command`, `## Expected Outcome`, `## Actual Result`, `## Evidence`, `## Failure Analysis`, `## Test Protection` に固定する。

```markdown
# TDD Test Report - <target-key> <phase>

<!-- validation-confirmed -->

- Schema-Version: 1
- Workflow: <workflow-id>
- Step: <step-id>
- Agent: <custom-agent-name>
- Target-Key: <target-key>
- Phase: <RED/GREEN>
- Test-Code-Path: <src/test/...>
- Timestamp-UTC: <ISO-8601 UTC timestamp>
- Evidence-Status: EXECUTED
- TDD-Judgement: <PASS/FAIL>
- Secret-Redaction: confirmed
- Test-Files-Changed: <yes/no/N/A>

## Command

## Expected Outcome

## Actual Result

## Evidence

## Failure Analysis

## Test Protection
```

{completion_instruction}{rg_section}{job_section}{additional_section}