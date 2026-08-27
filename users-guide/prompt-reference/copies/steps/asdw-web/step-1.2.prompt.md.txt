{root_ref}

{app_arch_scope_section}
## 目的
Step.1.1 で選定したデータストアに対する検証スクリプト `src/infra/azure/verify-data-resources.sh` を生成する（TDD RED フェーズ）。リソース作成・データ登録は行わない。

## 入力
- `docs/azure/azure-services-data.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない・空・対象 APP-ID 解決不能・サービス／エンティティとの交差結果 0 件なら verifier 生成前に停止する）
- （任意）`src/data/sample-data.json`（期待データ件数の算出源。無ければ件数検証は TBD）

## 出力
- `src/infra/azure/verify-data-resources.sh`（各データストアのリソース存在 / サービス別正常状態 / データ件数を検証。PostgreSQL Flexible Server は `state=Ready`、Cosmos DB / Storage / ADX は `provisioningState=Succeeded`、Azure SQL Database は `status=Online` を確認する。読み取り専用・冪等。1 件でも失敗があれば非ゼロ終了）
   - LF 改行（CRLF 禁止、UTF-8 BOM なし）で保存する。Windows/PowerShell から書き込む場合も `\r\n` を混入させない。
- `tests/run/<run-id>/asdw-web/step-1-2/<target-app-id>/RED/tdd-test-report.md`（RED フェーズのテスト結果レポート。必須ラベル・固定見出しは下記「## TDD テスト結果レポート（必須）」に従う）
- `tests/run/<run-id>/asdw-web/step-1-2/<target-app-id>/RED/static-verification.log`（`bash -n` / ShellCheck / artifact validator / focused pytest / LF・BOM 確認の実コマンドと終了コード。`tdd-test-report.md` の `Raw-Log-Path` が指す実在ファイル）

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティを扱う場合の **Microsoft Learn MCP が利用可能なら必ず参照** する規律、**title / URL / 確認事項** の記録、`要確認（Microsoft Learn MCP 未取得）` と記録して **推測で確定しない** 原則は、Agent 仕様 `.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md` の `## Azure 公式情報参照（Microsoft Learn MCP 必須）` に従う。

## 生成テストの実行環境

- `verify-data-resources.sh` は `bash -n` による構文確認をローカル端末 / CI で実行可能にする。RED 証跡は実行前提が揃う場合のみ記録し、実行不能時は `TBD（実行環境なし）` とする。
- 実行ホスト要件・環境変数の受領方法・秘密情報の非ハードコード、および ASDW data network contract（委譲先 Skill・対象エンティティ集合・期待件数の算出源）は Agent 仕様 `.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md` の同名セクションに従う。

{existing_artifact_policy}

## TDD RED フロー（必須）
- **出力前倒し（最優先）**: 必須成果物（`static-verification.log` → `tdd-test-report.md`）をできるだけ早いターンで確定する。既存 `verify-data-resources.sh` の適合性は逐次手読みではなく `bash -n` / artifact validator / LF・BOM で機械的に確認し、その直後に（追加の手読みレビューより前に）レポートを作成する（準拠・未変更なら `Test-Files-Changed: no`）。stale・不適合なら設計書＋契約から再生成してから同様に報告する。
1. `docs/azure/azure-services-data.md` で選定された各データストア（PostgreSQL Flexible Server / Cosmos DB / SQL / Storage / ADX 等）の検証ブロックを生成する（`az ... show` でリソース存在・サービス別正常状態・`sample-data.json` 由来の期待件数を比較する。PostgreSQL Flexible Server に `provisioningState=Succeeded` を一律適用せず、`state=Ready` を確認する）
   - 既存 `src/infra/azure/verify-data-resources.sh` が存在しても、PostgreSQL Flexible Server が `provisioningState=Succeeded` 判定のままなら stale とみなし、`state=Ready` 契約を満たす内容へ更新する。
   - network route、topology、passwordless認証、一時検証workload、cleanup、fail-closed規則は上記委譲契約に従う。
2. `bash -n src/infra/azure/verify-data-resources.sh` で構文確認（可能なら `shellcheck`）
3. RED 確認: リソース未作成の状態でスクリプトを実行すると `[FAIL]` で非ゼロ終了することを確認（`az` 認証が無い等で実行不能な場合は `TBD（実行環境なし）`）。**スクリプトを非ゼロ終了させること自体は本 Step の失敗ではない（スクリプト生成をもって成功とする）**
4. リソース作成・データ登録は行わない（Step.1.3 の責務）
5. `docs/` の構成整理、`docs/README.md` 作成提案、カタログ再編成は本 Step の範囲外。実施・提案しない。

## Custom Agent
`Dev-Microservice-Azure-DataTestCoding` を使用

## 依存
- Step.1.1（Azure データストア選定）が `asdw-web:done` であること

## 完了条件
- `src/infra/azure/verify-data-resources.sh` が作成され `bash -n` が成功している
- 選定された全データストアに対する検証ブロックが存在する
- リソース作成・データ登録を含まない（読み取り専用）
- `tdd-test-report.md` / `verify-data-resources.sh` / `static-verification.log` を作成しないままターンを終えない（ブロッカー・タイムアウト・ツール不安定時も、確認できた情報で verifier を生成し、レポートに `Evidence-Status: BLOCKED` / `TDD-Judgement: FAIL` と理由を記録して必ず作成。未作成は TDD report gate がファイル不在で fail 降格）。
## TDD テスト結果レポート（必須）
- 共通出力パス: `tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md`
- 出力先: `tests/run/<run-id>/asdw-web/step-1-2/<target-app-id>/RED/tdd-test-report.md`
- `<target-app-id>` は実行対象の APP-ID（例: `APP-009`）を使用する。Custom Agent 名を Workflow に使用しない。
- `Workflow` ラベルは必ず `- Workflow: asdw-web`、`Step` は `- Step: 1.2`、`Phase` は `- Phase: RED` とする。
- 本 Step は live Azure verifier を実行しないため `- Live-RED-Status: NOT_RUN` とする。
- 必須ラベル・3 状態証跡ラベルの判定規則・固定見出し・`Evidence-Status` / `TDD-Judgement` の記録可否・`Test-Files-Changed` の判定、および出力形式そのもの（固定ラベルと固定見出しの並び）は、Agent 仕様 `.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md` の同名セクション（固定スキーマの正本は Skill `tdd-red-green-reality`）に従い、本 Step では重複記載しない。
- `tests/run/<run-id>/asdw-web/step-1-2/<target-app-id>/RED/static-verification.log` に `bash -n`、ShellCheck、artifact validator、focused pytest、LF/BOM確認の実コマンド・終了コード・必要最小限の出力を記録する。Azure CLI / REST / live commandを実行していないことを明記し、`tdd-test-report.md` の `Raw-Log-Path` はこの実在pathを指す。`N/A`を記録しない。

## Step 1.2 実行時必須契約

- 生成する`Raw-Log-Path`は、Windows環境でもrepository-relativeの`/`区切りを必ず使用し、`\`区切りを書かないこと。値は単一のバッククォート1組で囲んでもよい。
- focused pytestには`hve/tests/test_runner_tdd_report_gate.py`を必ず含める。
- `read_file` / view の行範囲は実在行数が不明なまま大きく指定しないこと。`view_range out of bounds`時は見出し検索または小範囲で再取得し、同じ範囲を繰り返さないこと。

{completion_instruction}{app_id_section}{additional_section}