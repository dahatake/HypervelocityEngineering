# TDD テスト結果レポート

## 1.5) TDD テスト結果レポート（CLI / GUI 共通・必須）

TDD RED/GREEN Step は、テストコード（`src/test/`）や仕様書（`docs/`）ではなく、
実行ごとのテスト結果をルート直下 `tests/` 配下へ記録する。`src/test/` はテストコード専用、
`tests/` はテスト結果レポート専用として扱う。

`tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md`

- `<step-id>` は `.` と `/` を `-` に正規化する（例: `4.1` → `step-4-1`）。
- `<target-key>` は fan-out key を優先し、無ければ serviceId / screenId / jobId / agentId、取得不能なら `default` とする。
- `<phase>` は初回標準では `RED` または `GREEN` のみを使う。
- raw log を保存する場合は秘密情報を含めない。保存できない場合はサニタイズ済みの抜粋を `Log-Excerpt` に記録する。

必須ラベル（Markdown 固定スキーマ）:

| ラベル | 必須値 / 役割 |
|---|---|
| `Schema-Version` | `1` |
| `Workflow` | workflow id |
| `Step` | step id |
| `Agent` | Custom Agent 名 |
| `Target-Key` | fan-out key 等 |
| `Phase` | `RED` / `GREEN` |
| `Test-Code-Path` | `src/test/...` または verify script path |
| `Timestamp-UTC` | ISO-8601 UTC |
| `Evidence-Status` | `EXECUTED` / `NOT_EXECUTED_ENV_BLOCKED` |
| `TDD-Judgement` | `PASS` / `FAIL` / `BLOCKED` |
| `Secret-Redaction` | `confirmed` |
| `Test-Files-Changed` | `yes` / `no` / `N/A` |

GREEN Step では `Evidence-Status: EXECUTED` を必須とし、`TDD-Judgement` は原則 `PASS`（テストが実際に GREEN）とする。
テスト側または共有設定側の確定ブロッカーにより実装だけでは GREEN 化できない場合に限り、`BLOCKED`（正直なブロッカー記録。Skill `tdd-green-retry-strategy` §4 参照）を許容する。実装未達など自ステップ起因の失敗は `FAIL` とし、これは gate で拒否される。
RED Step では exit code の一律判定をしない。Step 固有の期待結果（例: baseline test は即 PASS し得る、
Azure 未認証時は `NOT_EXECUTED_ENV_BLOCKED` を許容する等）を `Expected Outcome` に明記する。

固定スキーマは以下を使用する。HVE の TDD report gate はラベルを `- Label: value` 形式で検出するため、
`Label: value` のようなプレーン行にしない。見出し名も固定し、`## Result` / `## Observed Result` /
`## Actual Outcome` / `## Changed Test Files` などの代替名にしない。
`TDD-Judgement: PASS` は RED フェーズのテストが成功したという意味ではなく、RED 期待結果どおりの
証跡として妥当であることを表す。

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
- TDD-Judgement: <PASS/FAIL/BLOCKED>
- Secret-Redaction: confirmed
- Test-Files-Changed: <yes/no/N/A>

## Command

- CWD: `<repository-root>`
- Command: `<test command>`
- Exit-Code: <exit-code>

## Expected Outcome

- Expected: <RED/GREEN の期待結果>
- Reason: <期待結果の根拠>

## Actual Result

- Test-Suites: <summary>
- Tests: <summary>
- Summary: <actual summary>

## Evidence

- Log-Excerpt: <sanitized excerpt or N/A>
- Raw-Log-Path: <path or N/A>
- Secret-Redaction: confirmed

## Failure Analysis

- Root-Cause: <expected RED failure / GREEN failure root cause>
- Next-Action: <next step>

## Test Protection

- Test-Files-Changed: <yes/no/N/A>
- Allowed-Test-Changes: <changed test files or N/A>
```

> **ASDW-WEB Step 1.2（DataTestCoding）の追加契約**: 上記の共通ラベルに加えて、Step 1.2 は 3 状態を分離して機械検証する。`Artifact-Contract-Status`（syntax/static validator/lint）、`Live-RED-Status`（live Azure verifier の expected-fail 実行 / `NOT_RUN` / `BLOCKED`）、`Focused-Regression-Status`（required focused pytest の exit code）を各1件記録する。static contract の PASS を live RED 実行として偽らず、live 未実行は `NOT_RUN`（`EXECUTED`/`PASS` にしない）、focused pytest 非ゼロは `FAIL`（単一 PASS へ畳み込まない）。これら3ラベルは HVE 所有の `machine-verification.log`（tool 実行結果から HVE が生成する正本）と一致する必要があり、不一致は gate で拒否される。詳細は `Dev-Microservice-Azure-DataTestCoding.prompt.md` を参照。
