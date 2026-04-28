{root_ref}

{app_arch_scope_section}
## 目的
TDD RED フェーズ: 画面別テスト仕様書（`docs/test-specs/{screenId}-test-spec.md`）から UI テストコードのみを生成する（APP-ID 指定時はスコープ内の画面のみ）。
全テストが FAIL（TDD RED 状態）であることを確認してから Step.3.1（GREEN フェーズ）へ進む。

## 入力
- `docs/test-specs/{screenId}-test-spec.md`（Step.3.0T で生成済みの画面別テスト仕様書）
- `docs/screen/{screenId}-*.md`（画面定義書）
- `docs/catalog/service-catalog-matrix.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

## 出力
- `test/ui/` 配下に Jest + jsdom テストファイル（テストコードのみ）

## Custom Agent
`Dev-Microservice-Azure-UITestCoding` を使用

## TDD RED 確認手順（必須）
1. Jest + jsdom テストを実行し、全テストが FAIL であることを確認する（RED 状態）
2. RED 確認結果（テスト実行ログ）を Issue コメントに記録する

## 最小スタブの配置（RED 状態維持のため）
- Jest テストを実行可能にするため、`src/app/` 配下に以下の最小スタブのみ配置してよい:
  - 空の HTML エントリポイント（`index.html` 等）
  - 空のモジュールファイル（`.js` 等）

## 依存
- Step.3.0T（UI テスト仕様書）が `asdw-web:done` であること

## 完了条件
- `test/ui/` 配下に UI テストコードが生成されている
- Jest テストで全テストが FAIL（RED 状態）であることが確認されている
{completion_instruction}{app_id_section}{additional_section}