{root_ref}

{app_arch_scope_section}
## 目的
TDD RED フェーズ: 画面定義書・テスト戦略書に基づき、対象画面のTDD用テスト仕様書を生成する（APP-ID 指定時はスコープ内の画面のみ）。
テスト仕様書は Step.3.1 のUI実装（GREEN フェーズ）の前に作成し、テスト駆動開発を実現する。

## 入力
- `docs/catalog/test-strategy.md`（テスト戦略書）
- `docs/catalog/service-catalog-matrix.md`（API一覧・依存関係マトリクス）
- `docs/screen/{screenId}-*.md`（画面定義書）
- `docs/catalog/data-model.md`
- `docs/catalog/domain-analytics.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

## 出力
- `docs/test-specs/{screenId}-test-spec.md`（画面別テスト仕様書）

## Custom Agent
`Arch-TDD-TestSpec` を使用

## 依存
- Step.2.5（Azure Compute Deploy）が `asdw-web:done` であること
- `docs/catalog/test-strategy.md` が存在すること（設計ワークフローで作成済み）

## 完了条件
- `docs/test-specs/` 配下に画面別テスト仕様書が生成されている
{completion_instruction}{app_id_section}{additional_section}