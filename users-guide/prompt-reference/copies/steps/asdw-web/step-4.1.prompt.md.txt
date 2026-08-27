{root_ref}

{app_arch_scope_section}
## 目的
TDD RED フェーズ: 画面別テスト仕様書（`docs/test-specs/{screenId}-test-spec.md`）から UI テストコードのみを生成する（APP-ID 指定時はスコープ内の画面のみ）。
初回実行（実装なし）は全テスト FAIL（RED）を確認してから Step.4.2（GREEN フェーズ）へ進む。再実行で `src/app/{screenId}/` に実装が既存の場合は canonical スイートが PASS し得るため、RED を強制する失敗テストを捏造しない。

## 入力
- `docs/test-specs/{screenId}-test-spec.md`（AAD-WEB Step 2.4 で事前生成済みの画面別テスト仕様書 — FULL_PIPELINE 順序保証に依存。単独実行時は手動配置）
- `docs/screen/{screenId}-*.md`（画面定義書）
- `docs/catalog/service-catalog-matrix.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

## 出力
- `src/test/ui/` 配下に Jest + jsdom テストファイル（テストコードのみ）
- テスト仕様書に 1:1 対応する canonical なテスト群のみを生成し（`// 出典` で対応付け、カテゴリ別複数ファイル可）、RED を作るための spec 非対応 ad-hoc 失敗テスト（`*.red-gaps` 等）を追加しない。前 run の非対応/矛盾テストが累積している場合は canonical スイートへ再整合（置換）する。

## 生成テストの実行環境
- 生成する UI テストはローカル端末 / CI で Jest/jsdom または Playwright により実行可能であること。
- RED フェーズでは Azure Static Web Apps や実 API へ接続しない。API 呼び出しはテスト仕様書の API モック / テストダブル設計に従い mock/stub で置き換える。
- E2E テストを生成する場合も、base URL は `E2E_BASE_URL` などの環境変数または画面固有設定から取得し、未設定を PASS 扱いしない。
- 接続文字列・Function Key・Bearer token 等の秘密情報をテストコード、README、ログにハードコードしない。
- TBD（要確認）を含む未確定契約を GREEN 必達の実行テストとして生成しない。正式 API endpoint / event / schema / enum 値が未確定の場合は、契約確定待ちとして `{WORK}` に記録する。
- 完了前に `src/test/ui/{screenId}/` 配下の `.js` を確認し、非コメント行に `TBD（要確認` が残っていないことを確認する。検出した場合は実行コードから除去し、契約確定待ちとして `{WORK}` に記録する。

## fan-out 共有設定ファイル保護
- 画面別 fan-out 子では、リポジトリルートの `package.json` / `jest.config.js` を作成・更新しない。
- 画面固有の補助設定が必要な場合は `src/test/ui/{screenId}/` 配下に閉じる。
- ルート共有設定が不足して RED 確認できない場合は、共有設定を新規作成せず `{WORK}` にブロッカーとして記録する。

## ツール利用衛生（fan-out）
- Markdown 仕様参照は `markdown-query` を優先し、0件時のみ `read_file` / `grep` へフォールバックする。
- `read_file` / view の行範囲は実在行数が不明なまま大きく指定しない。`view_range out of bounds` 時は見出し検索または小範囲で再取得し、同じ範囲を繰り返さない。
- `{WORK}` / `work/run/...` / 任意入力パスは `Test-Path` / `[ -e ]` で確認してから検索・読取する。出力先ディレクトリのみ必要時に作成し、入力・仕様・参照パスが存在しない場合は作成せず「未作成」と記録する。
- Web docs は MCP 優先とし、redirect / 404 は最終 URL または別公式ソースへ一度だけ切り替える。

{existing_artifact_policy}

## Custom Agent
`Dev-Microservice-Azure-UITestCoding` を使用

## TDD RED 確認手順（必須）
1. Jest + jsdom テストを実行し、実結果を記録する（初回=実装なしのため全 FAIL＝RED、再実行=実装既存なら canonical スイートは PASS し得る。RED を作るための失敗テストは捏造しない）
2. RED 確認結果（テスト実行ログ）を Issue コメントに記録する

## 依存
- AAD-WEB Step 2.4（画面別 TDD テスト仕様書）が事前完了していること（FULL_PIPELINE 順序保証）

## 完了条件
- `src/test/ui/` 配下に UI テストコードが生成されている
- Jest テストが実行可能で実結果が記録されている（初回=全 FAIL＝RED、再実行=実装既存なら canonical スイートは PASS し得る。失敗テストの捏造なし）
## TDD テスト結果レポート（必須）
- 出力先: `tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md`
- `<workflow-id>` は HVE workflow id を指す。ASDW-WEB では `asdw-web` を使い、Agent 名 `Dev-Microservice-Azure-UITestCoding` を workflow id として使わない。
- HVE から `## TDD report 出力先（HVE gate 必須）` として具体パスが提示された場合は、その具体パスを必ず優先する。
- 必須ラベル: `Schema-Version`, `Evidence-Status`, `TDD-Judgement`, `Secret-Redaction`, `Test-Files-Changed`
- `src/test/` はテストコード専用、`tests/` はテスト結果レポート専用とする。
- 固定スキーマは Skill `tdd-red-green-reality` の `tdd-test-report.md` テンプレートに従う。ラベルは必ず `- Label: value` 形式で書き、`Label: value` のプレーン行にしない。
- 見出し名は `## Command`, `## Expected Outcome`, `## Actual Result`, `## Evidence`, `## Failure Analysis`, `## Test Protection` に固定する。`## Result` / `## Observed Result` / `## Actual Outcome` / `## Changed Test Files` などの代替名は禁止。

```markdown
# TDD Test Report - <target-key> RED

<!-- validation-confirmed -->

- Schema-Version: 1
- Workflow: <workflow-id>
- Step: <step-id>
- Agent: Dev-Microservice-Azure-UITestCoding
- Target-Key: <target-key>
- Phase: RED
- Test-Code-Path: <src/test/ui/...>
- Timestamp-UTC: <ISO-8601 UTC timestamp>
- Evidence-Status: EXECUTED
- TDD-Judgement: PASS
- Secret-Redaction: confirmed
- Test-Files-Changed: <yes/no/N/A>

## Command

- CWD: `<repository-root>`
- Command: `<jest/jsdom or playwright command>`
- Exit-Code: <exit-code>

## Expected Outcome

- Expected: 初回実行は UI 実装未完了により RED。再実行で実装既存なら canonical スイートは PASS し得る（実装先行として許容）
- Reason: <テスト仕様書と RED フェーズの根拠。再実行時は実装先行の旨>

## Actual Result

- Test-Suites: <summary>
- Tests: <summary>
- Summary: <actual summary>

## Evidence

- Log-Excerpt: <sanitized excerpt or N/A>
- Raw-Log-Path: <path or N/A>
- Secret-Redaction: confirmed

## Failure Analysis

- Root-Cause: <expected RED failure root cause>
- Next-Action: Dev-Microservice-Azure-UICoding で GREEN 化する

## Test Protection

- Test-Files-Changed: <yes/no/N/A>
- Allowed-Test-Changes: <changed test files or N/A>
```

{completion_instruction}{app_id_section}{additional_section}