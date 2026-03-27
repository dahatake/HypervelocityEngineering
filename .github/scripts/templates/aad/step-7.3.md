{root_ref}
## 目的
テスト戦略書・画面定義書・サービス定義書を根拠に、TDD用テスト仕様書をサービスごと・画面ごとに作成する。

## 入力
- `docs/test-strategy.md`
- `docs/services/{{serviceId}}-{{serviceNameSlug}}-description.md`
- `docs/screen/{{screenId}}-{{screenNameSlug}}-description.md`
- `docs/service-catalog.md`
- `docs/data-model.md`
- `docs/domain-analytics.md`
- `docs/app-list.md`（アプリケーション一覧）

## 出力
- `docs/test-specs/{{serviceId}}-test-spec.md`（サービスごとに1ファイル）
- `docs/test-specs/{{screenId}}-test-spec.md`（画面ごとに1ファイル）

## Custom Agent
`Arch-TDD-TestSpec` を使用

## 依存
- Step.6（テスト戦略書）が `aad:done` であること（Step.6 がスキップされた場合は Step.5 が `aad:done` であること）
- Step.7.1（画面定義書）が `aad:done` であること
- Step.7.2（マイクロサービス定義書）が `aad:done` であること

## アプリケーション粒度
📋 各テスト仕様書の「§1 概要」に「対象アプリケーション」（APP-ID）を記載すること。`docs/app-list.md` の「アプリ一覧（アーキタイプ）概要」を参照。

## 完了条件
- テスト仕様書がサービスカタログに基づいて全サービス・全画面分作成されている
- 完了時に自身に `aad:done` ラベルを付与すること{additional_section}
