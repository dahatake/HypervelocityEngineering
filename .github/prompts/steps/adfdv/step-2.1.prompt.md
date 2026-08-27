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
- `src/test/dataflow/{jobId}-{jobNameSlug}.Tests/` 配下のテストコード（pytest / Python）

## 生成テストの実行環境
- 生成する pytest テストはローカル端末 / CI で `pytest` が実行可能であること。
- RED フェーズでは Azure データサービスへ実接続しない。外部 I/O はテスト仕様書のテストダブル設計に従い Azurite / Testcontainers / Mock / Stub に切り分ける。
- 構成済み外部サービスを使う Integration テストが必要な場合は Unit テストと分離し、接続先・認証・Resource 名を環境変数またはテスト設定ファイルで注入する。未設定を PASS 扱いしない。
- 接続文字列・アカウントキー・SAS・Bearer token 等の秘密情報をテストコード、README、ログにハードコードしない。

{existing_artifact_policy}

## Custom Agent
`Dev-Dataflow-TestCoding` を使用

## 依存
- {dep}

## 完了条件
- テストコードが作成され、`pytest` で失敗（TDD RED）が確認されている
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