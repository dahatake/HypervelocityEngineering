{root_ref}

{app_arch_scope_section}
## 目的
テスト戦略書・画面定義書を根拠に、TDD用テスト仕様書を画面ごとに作成する。

## 入力
- `docs/catalog/test-strategy.md`
- `docs/screen/{{screenId}}-{{screenNameSlug}}-description.md`
- `docs/catalog/screen-catalog-{{key}}.md`
- `docs/catalog/data-model.md`
- `docs/catalog/domain-analytics.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧）

## 出力
- `docs/test-specs/{{screenId}}-test-spec.md`（画面ごとに1ファイル）

{existing_artifact_policy}

## Custom Agent
`Arch-TDD-TestSpec` を使用

## 依存
- Step.2.1（画面定義書）が `aad-web:done` であること

## アプリケーション粒度
📋 各テスト仕様書の「§1 概要」に「対象アプリケーション」（APP-ID）を記載すること。`docs/catalog/app-catalog.md` の「アプリ一覧（アーキタイプ）概要」を参照。

## 完了条件
- テスト仕様書が画面カタログに基づいて全画面分作成されている
{completion_instruction}{additional_section}
