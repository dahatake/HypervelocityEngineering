{root_ref}

{app_arch_scope_section}
## 目的
TDD GREEN フェーズ: テスト仕様書 (`docs/test-specs/`) を参照しながらテストファーストで実装する。
画面定義書に基づき、対象画面のUIを実装し、サービスカタログに基づくAPIクライアント層を整備する（APP-ID 指定時はスコープ内の画面のみ）。

## 入力
- `docs/screen/{画面ID}.md`（画面ID 例: `SCR-XXX-YYY`）
- `docs/catalog/screen-catalog-APP-*.md`（全 APP の per-APP 分割された画面カタログ。`Arch-UI-List` Step 1 の per-APP fan-out 出力。全 APP 分を集約読みする）
- `docs/catalog/service-catalog-matrix.md`
- UI実装技術: `HTML5/CSS/JavaScript（リポジトリ既存規約に合わせる）`
- `docs/catalog/use-case-catalog.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- `src/data/sample-data.json`
- TDD テストコード（RED状態）: `src/test/ui/`（Step.4.1 の成果物）
- テスト仕様書: `docs/test-specs/{screenId}-test-spec.md`（AAD-WEB Step 2.4 で事前生成済み。TDD RED フェーズのテストケース定義）

## 出力
- `src/app/` 配下にUI実装

## 生成テストの実行環境
- Step.4.1 が生成した UI テストはローカル端末 / CI で `npm test`、Jest、または Playwright により決定的に PASS すること。
- GREEN 化のためにテストコードを実 API / Azure Static Web Apps 固定へ変更しない。UI 単体・操作テストの API は mock/stub を使用し、E2E は `E2E_BASE_URL` 等の環境変数で base URL を注入する。
- 実装コードはデプロイ先でも動くよう、API base URL や認証モードを環境変数または設定ファイルから読み込む。秘密情報をコード、README、ログにハードコードしない。

## fan-out 共有設定ファイル保護
- 画面別 fan-out 子では、リポジトリルートの `package.json` / `jest.config.js` を作成・更新しない。
- `src/test/ui/` は Step.4.1 の成果物として参照し、GREEN フェーズでは原則変更しない。
- テスト側/共有設定側の確定ブロッカーで実装だけでは GREEN 化不能な場合は成功扱いせず、テスト側または共有設定側の不足を `{WORK}` に記録する。この場合、`tdd-test-report.md` は `TDD-Judgement: BLOCKED`（gate は受理し下流を止めない）とし、completion-report で部分完了を成功として主張しない。実装未達など自ステップ起因の失敗は `FAIL` とする。

{existing_artifact_policy}

## TDD GREEN フロー（反復）
1. Jest テストで全テスト FAIL（RED 状態）を確認する
2. テストケースを GREEN にするための最小 UI 実装を作成する
3. Jest テストを実行する
4. 全テスト PASS なら REFACTOR へ進む。FAIL があれば実装を修正して手順3に戻る
5. 最大 {tdd_max_retries} 回反復する（Skill `tdd-green-retry-strategy` 準拠：各回は前回と異なるアプローチを選び、失敗の都度に根本原因を特定し当該技術（JavaScript / TypeScript / Jest / 使用ライブラリ）の公式ドキュメント・API を提供する MCP で解決策を確認してから次手を決める）
6. {tdd_max_retries} 回で全 PASS にならない場合: `asdw-web:blocked` ラベルを付与し、未 PASS テスト一覧を Issue コメントで報告する

## テストコード保護ルール
- GREEN フェーズでは UI 実装コードのみを修正する（`src/test/ui/` のテストコードは原則変更禁止）

## Custom Agent
`Dev-Microservice-Azure-UICoding` を使用

## 依存
- Step.4.1（UI テストコード生成）が `asdw-web:done` であること
- Step.1.2（データストア検証テスト生成）が `asdw-web:done` であること（本 Step 完了で local generation checkpoint に到達する）

## 完了条件
- `src/app/` 配下にUI実装が完成している
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
- TDD-Judgement: <PASS/FAIL/BLOCKED>
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
