{root_ref}
## 目的
データカタログ・サービス詳細・非構造化データ資産を根拠に、AI Agent 開発で用いるテスト戦略書を作成する。

## 入力
- `docs/catalog/data-model.md`（必須）
- `docs/catalog/domain-analytics.md`（必須）
- `docs/catalog/service-catalog.md`（必須）
- `docs/catalog/app-catalog.md`（必須）
- `docs/services/*-description.md`（Step.7 の出力）
- `docs/catalog/unstructured-data-catalog.md`（Step.8 の出力）

## 出力
- `docs/catalog/test-strategy.md`

{existing_artifact_policy}

## Custom Agent
`Arch-TDD-TestStrategy` を使用

## 依存
- Step.6（ペルソナカタログ）・Step.7（サービス詳細）・Step.8（非構造化データ資産カタログ）が `ada:done` であること

## ADA 固有の注意
- `docs/catalog/screen-catalog-APP-*.md` および `docs/catalog/service-catalog-matrix.md` は ADA では生成しない。存在しない前提で進め、E2E 画面テストの節は「対象なし（画面を持たないため）」と明記する。
- UI テスト種別（Component / Visual Regression / Accessibility）は対象外とする。

## 完了条件
- `docs/catalog/test-strategy.md` が作成されている
{completion_instruction}{additional_section}
