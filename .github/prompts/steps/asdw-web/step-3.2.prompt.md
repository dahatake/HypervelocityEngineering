{root_ref}

{app_arch_scope_section}
## 目的
TDD RED フェーズ: テスト仕様書（`docs/test-specs/{serviceId}-test-spec.md`）からテストコードのみを生成する（APP-ID 指定時はスコープ内のサービスのみ）。
全テストが FAIL（TDD RED 状態）であることを確認してから Step.3.3（GREEN フェーズ）へ進む。

## 入力
- `docs/test-specs/{serviceId}-test-spec.md`（AAD-WEB Step 2.3 で事前生成済みのサービス別テスト仕様書 — FULL_PIPELINE 順序保証に依存。単独実行時は手動配置）
- `docs/services/{serviceId}-*.md`（サービス定義書）
- `docs/catalog/service-catalog-matrix.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

## 出力
- `src/test/api/{サービス名}.Tests/` 配下に xUnit テストプロジェクト（テストコードのみ）

## 生成テストの実行環境
- 生成する xUnit テストはローカル端末 / CI で `dotnet build` と `dotnet test` が実行可能であること。
- RED フェーズでは Azure や外部 HTTP API へ実接続しない。外部 I/O はテスト仕様書のテストダブル設計に従い Mock / Stub / Emulator / Testcontainers に切り分ける。
- 設定キーは環境変数またはテスト設定ファイルで扱い、接続文字列・アカウントキー・SAS・Function Key・Bearer token 等の秘密情報をハードコードしない。

{existing_artifact_policy}

## Custom Agent
`Dev-Microservice-Azure-ServiceTestCoding` を使用

## TDD RED 確認手順（必須）
1. `cd src/test/api/{サービス名}.Tests` のように、生成したテストプロジェクトのディレクトリに移動する
2. 移動先ディレクトリで `dotnet build` を実行し、コンパイル成功を確認する
3. 同じディレクトリで `dotnet test` を実行し、そのテストプロジェクト内の全テストが FAIL であることを確認する（RED 状態）
4. RED 確認結果（テスト実行ログ）を Issue コメントに記録する

## 依存
- AAD-WEB Step 2.3（サービス別 TDD テスト仕様書）が事前完了していること（FULL_PIPELINE 順序保証）

## 完了条件
- `src/test/api/{サービス名}.Tests/` 配下にテストコードが生成されている
- `dotnet test` で全テストが FAIL（RED 状態）であることが確認されている
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

{completion_instruction}{app_id_section}{additional_section}