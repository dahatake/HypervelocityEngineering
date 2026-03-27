{root_ref}
## 目的
サービスカタログのAPI一覧・依存関係マトリクス・データモデルを根拠に、IoT 固有テスト戦略（デバイスシミュレーター・プロトコルテスト・オフラインテスト戦略含む）を作成する。

## 入力
- `docs/service-catalog.md`
- `docs/data-model.md`
- `docs/domain-analytics.md`
- `docs/device-connectivity.md`

## 出力
- `docs/test-strategy.md`

## Custom Agent
`Arch-TDD-TestStrategy` を使用

## 依存
- Step.4（サービスカタログ）が `aid:done` であること

## 完了条件
- `docs/test-strategy.md` が作成されている
- 完了時に自身に `aid:done` ラベルを付与すること{additional_section}
