{root_ref}

{app_arch_scope_section}
## 目的
TDD GREEN フェーズ: Step.2.3 で生成された追加サービス向けテストコードを、デプロイ済みの追加 Azure サービス（Step.2.2 の成果物）に対して実行し、全テストが PASS する状態を達成する。
本 step では「テストの実施 + 失敗時の最小修正」を対象とする。アプリケーション側コードの本実装は Compute コンテナ（Step.3.x）で行うため、本 step での修正範囲は追加サービスの構成・接続設定・テストフィクスチャに限定する。

## 入力
- Step.2.3 で生成されたテストコード（`src/test/integration/add-service/`）
- Step.2.2 でデプロイ済みの追加 Azure サービス（実環境）
- `docs/azure/azure-services-additional.md`
- `docs/catalog/app-catalog.md`

## 出力
- 全テストが PASS する状態（テストコード本体の改変は最小限）
- テスト実行ログ（Issue コメント記録）

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログ（work-status 系成果物）または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。必要に応じて `az ... -h` / パッケージマネージャ / 公式 CLI help を補助確認として使う。

## 生成テストの実行環境
- 本 Step の `dotnet test` は、追加 Azure サービスが正しくデプロイ済み・構成済みであることを前提にした外部サービス検証である。
- ローカル端末 / CI / デプロイ先のいずれでも、同じ環境変数または `appsettings.Testing.json` 等のテスト設定ファイルで接続先・認証・Resource 名を注入する。
- 必須設定が未設定の場合は C1 接続設定不備または環境ブロッカーとして扱い、テストを弱めたり skip したりして PASS 扱いしない。
- 接続文字列・アカウントキー・SAS・Bearer token 等の秘密情報をコード、README、ログにハードコードしない。

{existing_artifact_policy}

## Custom Agent
`Dev-Microservice-Azure-AddServiceTesting` を使用

## TDD GREEN 確認手順（必須）
1. テスト実行コマンドを実行
2. FAIL があれば追加サービスの構成・接続設定・テストフィクスチャを修正（最大 3 回反復）
3. 全テストが PASS したことをログで確認
4. 3 回で全 PASS にならない場合: `asdw-web:blocked` ラベルを付与し未 PASS テスト一覧を報告

> Foundry のモデル未デプロイ（`az cognitiveservices account deployment list` が 0 件）はモデルデプロイ＝ Step.2.2 の責務のため、本 step では自己対応せず `asdw-web:blocked` で停止して RED を可視化し（自動再実行はしない）、Step.2.2 へフィードバックする。モデル SKU / 容量の不一致は Step.2.1 へフィードバックする。

> Foundry Project 未作成（`az cognitiveservices account project show` が NotFound / 非 `Succeeded`）は Project 作成＝ Step.2.2 の責務である。本 step では親 account や `created-resources.json` で代用せず、自己対応しないで `asdw-web:blocked` として RED を可視化し、Step.2.2 へフィードバックする。

> 本 step は Foundry Project／モデル deployment を作成・更新しない。Foundry 採用時は Project 実在テストとモデル実在テストが別々に生成・実行され、両方 PASS したことを完了条件に含める。

## 依存
- Step.2.3（追加サービスのテストコード生成）が `asdw-web:done` であること
- Step.2.2（追加 Azure サービス Deploy）が `asdw-web:done` であること

## 完了条件
- 全テストが PASS している（TDD GREEN 達成）
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
