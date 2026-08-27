{root_ref}

{app_arch_scope_section}
## 目的
TDD RED フェーズ（追加サービス枠）: Step.2.1（追加 Azure サービス選定）の**設計**から、追加サービス（例: AI 連携、認証、統合、運用基盤）向け integration テストコードのみを生成する。
本 Step は local-first / live-last DAG において Step.2.2（追加 Azure サービス Deploy）**より前**に実行される。したがってリソース未作成による FAIL は正常な RED であり、これを回避するために検証を弱めたり、テストを skip したりしない。Deploy 後の GREEN 化は Step.2.4（追加サービスのテスト実施）が担う。

## 入力
- `docs/azure/azure-services-additional.md`（Step.2.1 出力 — 追加 Azure サービス選定根拠。本 Step の唯一のサービス定義正本）
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠）

> deploy 済みリソースや `created-resources.json` 等の Step.2.2 成果物を入力にしない。未存在を前提に設計宣言値だけでテストを組み立てる。
## 出力
- `src/test/integration/add-service/` 配下に追加サービス向け統合テストプロジェクト（テストコードのみ）

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログ（work-status 系成果物）または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。必要に応じて `az ... -h` / パッケージマネージャ / 公式 CLI help を補助確認として使う。

## 生成テストの実行環境
- 生成する integration test は、追加 Azure サービスが正しくデプロイ済み・構成済みである場合に、ローカル端末 / CI / デプロイ先のいずれでも `dotnet test` で実行できる構造にする。
- 接続先 Endpoint、Namespace、Resource 名、認証方式は環境変数または `appsettings.Testing.json` 等のテスト設定ファイルから取得する。
- 必須設定が未設定の場合は環境ブロッカーとして失敗させ、未設定のまま PASS 扱いしない。
- 接続文字列・アカウントキー・SAS・Bearer token 等の秘密情報をテストコード、README、ログにハードコードしない。

{existing_artifact_policy}

## Custom Agent
`Dev-Microservice-Azure-AddServiceTestCoding` を使用

## テスト生成・確認手順（必須）
1. 生成したテストプロジェクトに移動し、ビルド成功を確認する
2. テスト実行コマンドを実行し、現状の PASS / FAIL 件数を記録する（本 Step は Deploy 前のためリソース未作成による FAIL が正常な RED。FAIL を避ける目的で検証を弱めず、恒真式アサーションも使わない）
3. 確認結果（テスト実行ログ）を Issue コメントに記録する

> AI/LLM（Microsoft Foundry）採用時は、resource type `Microsoft.CognitiveServices/accounts/projects` の **Foundry Project 子リソース**を公式 `GetCognitiveServicesProjects()` 等の管理 API でread-only取得し、account / Project名 / location / `Succeeded` を確認する独立テストと、デプロイ済みモデル 1 件以上を確認する独立テストを生成する。両テストは実行順序に依存させず、Project／deployment の create / update / delete を呼ばない。親 account や `created-resources.json` だけで Project 実在を PASS にしない。AI/LLM 非該当時は生成しない。

## 依存
- Step.2.1（追加 Azure サービス選定）が `asdw-web:done` であること

## 完了条件
- 追加サービス向けテストコードが生成されている（接続性 / 権限境界 / 基本 I/O / 設定整合性の 4 カテゴリを各 1 件以上）
- Foundry 採用時は Project 子リソースとモデル deployment を別テストで検証し、未存在を PASS にしない
- ビルドが成功し、テストが実行可能である（PASS/FAIL 件数を記録。Deploy 前の FAIL を RED として記録し、恒真式アサーションを使わない）
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
