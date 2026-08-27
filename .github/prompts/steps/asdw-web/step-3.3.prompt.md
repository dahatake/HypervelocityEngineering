{root_ref}

{app_arch_scope_section}
## 目的
TDD GREEN フェーズ: テスト仕様書 (`docs/test-specs/`) を参照しながらテストファーストで実装する。
マイクロサービス定義書から対象サービスの Azure Functions を実装し、テスト/最小ドキュメント/設定雛形まで揃える（APP-ID 指定時はスコープ内のサービスのみ）。

## 入力
- `docs/services/{serviceId}-*.md`（サービス定義書）
- Azure Functions プログラミング言語: `C#（最新版のAzure Functionsでサポートされているもの）`
- `docs/catalog/service-catalog.md`
- `docs/catalog/data-model.md`
- `docs/catalog/service-catalog-matrix.md`
- `docs/azure/azure-services-*.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- TDD テストコード（RED状態）: `src/test/api/{サービス名}.Tests/`（Step.3.2 の成果物）
- テスト仕様書: `docs/test-specs/{serviceId}-test-spec.md`（AAD-WEB Step 2.3 で事前生成済み。TDD RED フェーズのテストケース定義）

## 出力
- `src/api/{サービスID}-{サービス名}/` 配下に Azure Functions を作成/更新
- （任意推奨）`src/test/api/smoke-ui/index.html`

## 生成テストの実行環境
- `src/test/api/` の単体テストはローカル端末 / CI で `dotnet test` により決定的に PASS すること。
- GREEN 化のために Azure や外部 HTTP API へ実接続するテストへ変更しない。外部 I/O は interface / wrapper / Mock / Stub / Emulator / Testcontainers に切り分ける。
- 実装コードは Azure Functions としてデプロイ可能にしつつ、接続先・認証・base URL・リソース名は環境変数または設定ファイルから読み込む。秘密情報をコード、README、ログにハードコードしない。

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログ（work-status 系成果物）または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。必要に応じて `az ... -h` / パッケージマネージャ / 公式 CLI help を補助確認として使う。

{existing_artifact_policy}

## TDD GREEN フロー（反復）
1. `dotnet test` で全テスト FAIL（RED 状態）を確認する
2. テストケースを GREEN にするための最小実装を作成する
3. `dotnet test` を実行する
4. 全テスト PASS なら REFACTOR へ進む。FAIL があれば実装を修正して手順3に戻る
5. 最大 {tdd_max_retries} 回反復する（Skill `tdd-green-retry-strategy` 準拠：各回は前回と異なるアプローチを選び、失敗の都度に根本原因を特定し Microsoft Learn MCP（C# / .NET / Azure Functions / SDK）で解決策を確認してから次手を決める）
6. {tdd_max_retries} 回で全 PASS にならない場合: `asdw-web:blocked` ラベルを付与し、未 PASS テスト一覧を Issue コメントで報告する

## テストコード保護ルール
- GREEN フェーズでは実装コードのみを修正する（`src/test/api/` のテストコードは原則変更禁止）

## Custom Agent
`Dev-Microservice-Azure-ServiceCoding-AzureFunctions` を使用

## 依存
- Step.3.2（サービス テストコード生成）が `asdw-web:done` であること

## 完了条件
- `src/api/` 配下に Azure Functions が実装されている
- `dotnet test` の全テストが PASS であること（TDD GREEN 確認）
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
