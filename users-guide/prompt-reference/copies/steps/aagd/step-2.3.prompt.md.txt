{root_ref}
## 目的
TDD GREEN フェーズ: Agent 詳細設計書から AI Agent を実装し、全テストを PASS させる。
Microsoft Foundry（Azure AI Foundry Agent Service）を使用して Agent を実装する（APP-ID 指定時はスコープ内の Agent のみ）。

## 重要
- **Azure AI Foundry Agent Service** を使用する
- チュートリアル参照: https://learn.microsoft.com/ja-jp/azure/foundry/quickstarts/get-started-code?tabs=python
  - ⚠️ チュートリアルのコードをそのままコピーしない
- **ユーザーが指定したプログラミング言語で最新の SDK** を使用する
  - Python: `azure-ai-projects`（最新版）
  - C#: `Azure.AI.Projects`（最新版）
- `DefaultAzureCredential` を使用して Azure に認証する

## 入力
- `docs/agent/agent-detail-{key}.md`（Agent 詳細設計書）
- `docs/ai-agent-catalog.md`
- TDD テストコード（RED状態）: `src/test/agent/{key}.Tests/`
- TDD テスト仕様書: `docs/test-specs/{key}-test-spec.md`
- `docs/catalog/service-catalog-matrix.md`
- `docs/azure/azure-services-additional.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

## 出力
- `src/agent/{key}/`

## 生成テストの実行環境
- `src/test/agent/{key}.Tests/` のテストはローカル端末 / CI で `pytest` または `dotnet test` により決定的に PASS すること。
- GREEN 化のためにテストコードを Azure AI Foundry Agent Service や外部 Tool API へ実接続する内容へ変更しない。Agent / Tool / RAG / HTTP 呼び出しは mock/stub で切り分ける。
- 実装コードは Azure AI Foundry へデプロイ可能にしつつ、Endpoint、モデル名、Tool サービス URL、認証情報は環境変数または設定ファイルから読み込む。秘密情報をコード、README、ログにハードコードしない。

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログ（work-status 系成果物）または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。必要に応じて `az ... -h` / パッケージマネージャ / 公式 CLI help を補助確認として使う。

{existing_artifact_policy}

## TDD GREEN フロー（反復）
1. build/collection成功後、未実装production behaviorのテストが1件以上FAILしてsuite全体がREDであることを確認する（既成立の不在・禁止契約テストはPASS可）
2. 最小限の Agent 実装を作成する
3. テストを実行する
4. 全テスト PASS なら REFACTOR へ進む。FAIL があれば実装を修正して手順3に戻る
5. 最大 {tdd_max_retries} 回反復する（Skill `tdd-green-retry-strategy` 準拠：各回は前回と異なるアプローチを選び、失敗の都度に根本原因を特定し実装言語に応じた公式技術情報 MCP（C#→Microsoft Learn MCP / Python→Python 技術情報 MCP）で解決策を確認してから次手を決める）
6. {tdd_max_retries} 回で全 PASS にならない場合: `aagd:blocked` ラベルを付与し、未 PASS テスト一覧を報告する

## Custom Agent
`Dev-Microservice-Azure-AgentCoding` を使用

## 依存
- Step.2.2（AI Agent テストコード生成）が `aagd:done` であること

## 完了条件
- `src/agent/` 配下に Agent 実装コードが存在する
- テストの全テストが PASS であること（TDD GREEN 確認）
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
