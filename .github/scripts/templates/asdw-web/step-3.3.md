{root_ref}

{app_arch_scope_section}
## 目的
Step.3.2 でデプロイ済みの Web アプリ（SWA URL）に対して、Playwright による E2E テストを実行する。

## 入力
- `E2E_BASE_URL`（未指定時は `docs/catalog/service-catalog-matrix.md` から SWA URL を抽出）
- `docs/catalog/service-catalog-matrix.md`
- `docs/test-specs/{screenId}-test-spec.md`
- `tests/e2e/playwright/`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

## 出力
- Playwright 実行ログ
- 失敗時: HTML レポート / trace artifact

## 必須シナリオ（Issue で増減可）
1. ログイン / 認証導線（該当なしの場合は代表的な初期画面遷移）
2. 主要 CRUD 操作（リソース別に最低 1 件）
3. エラーハンドリング（不正入力 / 404 / API エラー）
4. API 連携（フロント → バックエンド `/api/*`）
5. レスポンシブ / アクセシビリティ最低限（viewport 切替で主要要素描画）

## Custom Agent
`E2ETesting-Playwright` を使用

## 依存
- Step.3.2（Web アプリ Deploy）が `asdw-web:done` であること

## 完了条件
- Playwright テストが全 PASS
- 失敗時に HTML レポート / trace artifact が保存される
- 失敗時は最大 3 回リトライし、超過時は `asdw-web:blocked` を付与する
{completion_instruction}{app_id_section}{additional_section}
