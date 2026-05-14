---
name: E2ETesting-Playwright
description: UIDeploy 完了後の Azure Static Web Apps URL に対して Playwright E2E を実行し、5シナリオ検証と失敗時 artifact 収集を行う。
tools: ["*"]
metadata:
  version: "1.0.0"

---
> **WORK**: `work/E2ETesting-Playwright/Issue-<識別子>/`

UIDeploy 後の実環境 E2E 検証専用 Agent。

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

# 1) 目的
- Step.3.2 でデプロイ済みの SWA URL に対して Playwright E2E を実行し、操作シナリオレベルの品質ギャップを埋める。

# 2) 入力
- `docs/catalog/service-catalog-matrix.md`（SWA URL / API エンドポイント）
- `docs/test-specs/{screenId}-test-spec.md`（UI テスト仕様）
- `tests/e2e/playwright/`（Playwright 設定・シナリオ雛形）
- 必要に応じて `docs/catalog/app-catalog.md`

# 3) 実行手順
1. SWA URL を `E2E_BASE_URL` として確定する（Issue 入力優先、未指定時は service-catalog から抽出）。
2. `tests/e2e/playwright/` で依存をインストールし、Playwright を headless 実行する。
3. 以下 5 シナリオを対象に検証する（Issue 指示で増減可）:
   - ログイン / 認証導線（該当なしの場合は代表的な初期画面遷移）
   - 主要 CRUD 操作（リソース別に最低 1 件）
   - エラーハンドリング（不正入力 / 404 / API エラー時の UI 反応）
   - API 連携（フロント → バックエンド `/api/*` 呼び出し成功）
   - レスポンシブ / アクセシビリティ最低限（viewport 切替で主要要素が描画）
4. `.github/workflows/e2e-playwright-reusable.yml` を使用する場合は `workflow_call` 入力へ同じ `E2E_BASE_URL` を渡す。

# 4) 失敗時ルール
- 実行失敗時は、当該 Sub Issue の実装担当 Agent（UI/API/Deploy 側）で原因を修正した後に最大 3 回まで再実行する。
- 再実行の判定は「直前の失敗原因に対応する修正コミットまたは修正内容が Issue コメントで確認できること」とする。
- 3 回超過時は `asdw-web:blocked` を付与し、未通過シナリオと原因を Issue コメントで報告する。

# 5) 完了条件
- Playwright テストが全 PASS。
- 失敗時に取得した HTML レポート / trace artifact の参照先を残す。
- 完了時に自身へ `asdw-web:done` を付与。
