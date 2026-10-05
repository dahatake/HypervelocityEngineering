{root_ref}
## 目的
TDD RED フェーズ: Agent テスト仕様書（`docs/test-specs/{key}-test-spec.md`）からテストコードのみを生成する（APP-ID 指定時はスコープ内の Agent のみ）。
build/collection成功後、未実装production behaviorのテストが1件以上FAILしてsuite全体がREDであることを確認してから Step.2.3（GREEN フェーズ）へ進む。既成立の不在・禁止契約テストはPASSを許容する。

## 入力
- `docs/test-specs/{key}-test-spec.md`（Step.2.1 で生成済みの Agent テスト仕様書）
- `docs/agent/agent-detail-{key}.md`
- `docs/catalog/service-catalog-matrix.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

## 出力
- `src/test/agent/{key}.Tests/` 配下にテストプロジェクト（テストコードのみ）

## 生成テストの実行環境
- 生成する Agent テストはローカル端末 / CI で `pytest` または `dotnet test` により実行可能であること。
- RED フェーズでは Azure AI Foundry Agent Service、Azure OpenAI、外部 Tool API へ実接続しない。Agent / Tool / RAG / HTTP 呼び出しは mock/stub に置き換える。
- テストコードは環境変数またはテスト設定ファイルで設定キーだけを扱い、Endpoint URL、接続文字列、API キー、Bearer token 等の秘密情報をハードコードしない。

- Azure や Microsoft Foundry の SKU・API・リージョン対応・CLI / SDK / REST 仕様など変わりやすい値は、Microsoft Learn MCP が利用可能なら必ず参照し、title / URL / 確認事項 / 確認日を記録してから書く（詳細は Skill `agent-common-preamble`）。参照できない値は `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。

{existing_artifact_policy}

## Custom Agent
`Dev-Microservice-Azure-AgentTestCoding` を使用

## TDD RED 確認手順
1. build/collection成功後にテストを実行し、未実装production behaviorのテストが1件以上FAILしてsuite全体がREDであることを確認する
2. RED 確認結果（テスト実行ログ）を Issue コメントに記録する

## 依存
- Step.2.1（AI Agent テスト仕様書）が `aagd:done` であること

## 完了条件
- `src/test/agent/{key}.Tests/` 配下にテストコードが生成されている
- build/collection成功かつ未実装production behaviorのテストが1件以上FAILしてsuite全体がREDであることが確認されている
## TDD テスト結果レポート
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

{completion_instruction}{app_id_section}{additional_section}
