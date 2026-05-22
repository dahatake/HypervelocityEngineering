<!-- DEPRECATED: このテンプレートは templates/aas/step-7.md に移動しました。 -->
{root_ref}
## 目的
サービスカタログのAPI一覧・依存関係マトリクス・データモデルを根拠に、TDDのためのプロジェクト全体テスト戦略書を作成する。

## 入力
- `docs/catalog/service-catalog-matrix.md`
- `docs/catalog/data-model.md`
- `docs/catalog/domain-analytics.md`
- `docs/catalog/service-catalog.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧）
- `docs/catalog/data-catalog.md`（存在すれば参照）

## 出力
- `docs/catalog/test-strategy.md`

## Custom Agent
`Arch-TDD-TestStrategy` を使用

## 依存
- Step.5（サービスカタログ）が `aad:done` であること

## アプリケーション粒度
📋 `docs/catalog/app-catalog.md` のアプリケーション一覧（APP-ID）を参照し、テスト戦略書にアプリ単位のサービス分類を考慮すること。

## 完了条件
- `docs/catalog/test-strategy.md` が作成されている
{completion_instruction}{additional_section}
