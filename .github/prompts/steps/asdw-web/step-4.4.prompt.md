{root_ref}

{app_arch_scope_section}
## 目的
Step.4.3 でデプロイ済みの Web アプリ（SWA URL）に対して、Playwright による E2E テストを実行する。

## 入力
- `E2E_BASE_URL`（未指定時は `docs/catalog/service-catalog-matrix.md` から SWA URL を抽出）
- `docs/catalog/service-catalog-matrix.md`
- `docs/test-specs/{screenId}-test-spec.md`
- `src/test/e2e/playwright/`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

## 出力
- Playwright 実行ログ
- 失敗時: HTML レポート / trace artifact

## 生成テストの実行環境
- Playwright E2E は、Azure Static Web Apps と依存 API が正しくデプロイ済み・構成済みであることを前提にした実環境検証である。
- ローカル端末 / CI / デプロイ先のいずれでも `E2E_BASE_URL` を優先して base URL を注入し、未設定時は service-catalog 等の根拠から取得する。根拠がなければ環境ブロッカーとして記録し、PASS 扱いしない。
- 認証トークン、Cookie、API Key 等の秘密情報は環境変数または実行環境の secret store から渡し、テストコード、README、ログにハードコードしない。
- 失敗時 artifact には秘密情報が含まれないよう、URL query、token、Cookie をログへ平文出力しない。

{existing_artifact_policy}

## 必須シナリオ（Issue で増減可）
1. ログイン / 認証導線（該当なしの場合は代表的な初期画面遷移）
2. 主要 CRUD 操作（リソース別に最低 1 件）
3. エラーハンドリング（不正入力 / 404 / API エラー）
4. API 連携（フロント → バックエンド `/api/*`）
5. レスポンシブ / アクセシビリティ最低限（viewport 切替で主要要素描画）

## Custom Agent
`E2ETesting-Playwright` を使用

## 依存
- Step.4.3（Web アプリ Deploy）が `asdw-web:done` であること

## 完了条件
- Playwright テストが全 PASS
- 失敗時に HTML レポート / trace artifact が保存される
- 失敗時は最大 5 回リトライし（Skill `tdd-green-retry-strategy` 準拠：各回は異なるアプローチを選び、失敗の都度に根本原因を特定して当該技術の公式ドキュメント MCP で解決策を確認する）、超過時は `asdw-web:blocked` を付与する
{completion_instruction}{app_id_section}{additional_section}
