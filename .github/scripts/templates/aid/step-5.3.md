{root_ref}
## 目的
テスト戦略書・画面定義書・サービス定義書を根拠に、IoT 固有テスト仕様書（デバイステスト・エッジ推論テスト・E2Eテスト含む）をサービスごと・画面ごとに作成する。

## 入力
- `docs/test-strategy.md`
- `docs/services/{{serviceId}}-{{serviceNameSlug}}-description.md`
- `docs/screen/{{screenId}}-{{screenNameSlug}}-description.md`
- `docs/service-catalog.md`
- `docs/data-model.md`
- `docs/domain-analytics.md`
- `docs/device-connectivity.md`

## 出力
- `docs/test-specs/{{serviceId}}-test-spec.md`（サービスごとに1ファイル）
- `docs/test-specs/{{screenId}}-test-spec.md`（画面ごとに1ファイル）

## Custom Agent
`Arch-TDD-TestSpec` を使用

## 依存
- Step.4.5（テスト戦略書）が `aid:done` であること
- Step.5.1（画面定義書）が `aid:done` であること
- Step.5.2（マイクロサービス定義書）が `aid:done` であること

## 完了条件
- テスト仕様書がサービスカタログに基づいて全サービス・全画面分作成されている
- 完了時に自身に `aid:done` ラベルを付与すること{additional_section}
