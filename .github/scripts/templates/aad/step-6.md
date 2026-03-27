{root_ref}
## 目的
サービスカタログのAPI一覧・依存関係マトリクス・データモデルを根拠に、TDDのためのプロジェクト全体テスト戦略書を作成する。

## 入力
- `docs/service-catalog.md`
- `docs/data-model.md`
- `docs/domain-analytics.md`
- `docs/service-list.md`
- `docs/app-list.md`（アプリケーション一覧）
- `docs/data-catalog.md`（存在すれば参照）

## 出力
- `docs/test-strategy.md`

## Custom Agent
`Arch-TDD-TestStrategy` を使用

## 依存
- Step.5（サービスカタログ）が `aad:done` であること

## アプリケーション粒度
📋 `docs/app-list.md` のアプリケーション一覧（APP-ID）を参照し、テスト戦略書にアプリ単位のサービス分類を考慮すること。

## 完了条件
- `docs/test-strategy.md` が作成されている
- 完了時に自身に `aad:done` ラベルを付与すること{additional_section}
