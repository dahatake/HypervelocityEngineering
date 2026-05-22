{root_ref}

{app_arch_scope_section}
## 目的
TDD RED フェーズ: サービス定義書・テスト戦略書に基づき、対象サービスのTDD用テスト仕様書を生成する（APP-ID 指定時はスコープ内のサービスのみ）。
テスト仕様書は Step.2.4 のサービスコード実装（GREEN フェーズ）の前に作成し、テスト駆動開発を実現する。

## 入力
- `docs/catalog/test-strategy.md`（テスト戦略書）
- `docs/catalog/service-catalog-matrix.md`（API一覧・依存関係マトリクス）
- `docs/services/{serviceId}-*.md`（サービス定義書）
- `docs/catalog/data-model.md`
- `docs/catalog/domain-analytics.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- `test/api/`（既存テストパターン確認）

## 出力
- `docs/test-specs/{serviceId}-test-spec.md`（サービス別テスト仕様書）

{existing_artifact_policy}

## Custom Agent
`Arch-TDD-TestSpec` を使用

## 依存
- Step.2.3（追加 Azure サービス Deploy）が `asdw-web:done` であること
- `docs/catalog/test-strategy.md` が存在すること（設計ワークフローで作成済み）

## 完了条件
- `docs/test-specs/` 配下にサービス別テスト仕様書が生成されている
- 生成したテスト仕様書（`docs/test-specs/{serviceId}-test-spec.md`）へのリンクを Issue コメントに記載している
{completion_instruction}{app_id_section}{additional_section}
