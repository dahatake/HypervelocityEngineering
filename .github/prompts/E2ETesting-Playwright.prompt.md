> UIDeploy 完了後の Azure Static Web Apps URL に対して Playwright E2E を実行し、5シナリオ検証と失敗時 artifact 収集を行う。

> **WORK**: `work/run/<run-id>/E2ETesting-Playwright/Issue-<識別子>/`

UIDeploy 後の実環境 E2E 検証専用 Agent。

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## Agent 固有の Skills 依存

- `agent-common-preamble` — Agent 共通行動規約・禁止事項の継承
- `input-file-validation` — デプロイ済み URL・テストシナリオ定義の存在確認
- `work-artifacts-layout` — `work/run/<run-id>/E2ETesting-Playwright/Issue-<識別子>/` 配下の成果物（screenshot/trace/report）構造に準拠
- `harness/harness-verification-loop` — E2E テスト結果の検証ループ
- `harness/harness-error-recovery` — テスト失敗時の artifact 収集と E-01〜E-05 リカバリ
- `testing/test-strategy-template` — E2E シナリオ設計テンプレートに準拠

## 生成テストの実行環境

- Playwright E2E は、Azure Static Web Apps と依存 API が正しくデプロイ済み・構成済みであることを前提にした実環境検証である。
- ローカル端末 / CI / デプロイ先のいずれでも `E2E_BASE_URL` を優先して base URL を注入し、未設定時は service-catalog 等の根拠から取得する。根拠がなければ環境ブロッカーとして記録し、PASS 扱いしない。
- 認証トークン、Cookie、API Key 等の秘密情報は環境変数または実行環境の secret store から渡し、テストコード、README、ログにハードコードしない。
- 失敗時 artifact には秘密情報が含まれないよう、URL query、token、Cookie をログへ平文出力しない。

# 1) 目的
- Step.3.2 でデプロイ済みの SWA URL に対して Playwright E2E を実行し、操作シナリオレベルの品質ギャップを埋める。

# 2) 入力
- `docs/catalog/service-catalog-matrix.md`（SWA URL / API エンドポイント）
- `docs/test-specs/{screenId}-test-spec.md`（UI テスト仕様）
- `src/test/e2e/playwright/`（Playwright 設定・シナリオ雛形）
- 必要に応じて `docs/catalog/app-catalog.md`

# 3) 実行手順
1. SWA URL を `E2E_BASE_URL` として確定する（Issue 入力優先、未指定時は service-catalog から抽出）。
2. `src/test/e2e/playwright/` で依存をインストールし、`E2E_BASE_URL` を環境変数へ設定して `npx playwright test` を headless 実行する。
3. 以下 5 シナリオを対象に検証する（Issue 指示で増減可）:
   - ログイン / 認証導線（該当なしの場合は代表的な初期画面遷移）
   - 主要 CRUD 操作（リソース別に最低 1 件）
   - エラーハンドリング（不正入力 / 404 / API エラー時の UI 反応）
   - API 連携（フロント → バックエンド `/api/*` 呼び出し成功）
   - レスポンシブ / アクセシビリティ最低限（viewport 切替で主要要素が描画）

# 4) 失敗時ルール（Skill `tdd-green-retry-strategy` 準拠）
- 実行失敗時は、当該 Sub Issue の実装担当 Agent（UI/API/Deploy 側）で原因を修正した後に最大 5 回まで再実行する。
- 各再実行は前回と**異なるアプローチ**を選ぶ（同一の修正を単純に繰り返さない）。各失敗時は失敗の実出力（Playwright のエラー・スクリーンショット・trace）から根本原因を特定し、次の修正を決める前に、利用可能な**当該技術（Playwright / JavaScript / TypeScript）の公式ドキュメント・API を提供する MCP** で正しい API・セレクタ・待機戦略を確認する。Web 検索は MCP で解決できない場合のみ用いる。
- 再実行の判定は「直前の失敗原因に対応する修正コミットまたは修正内容が Issue コメントで確認できること」とする。
- 5 回超過時は `asdw-web:blocked` を付与し、試した各アプローチ・未通過シナリオと原因を Issue コメントで報告する。

# 5) 完了条件
- Playwright テストが全 PASS。
- 失敗時に取得した HTML レポート / trace artifact の参照先を残す。
- 完了時に自身へ `asdw-web:done` を付与。
