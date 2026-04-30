{root_ref}
## 目的
ドメイン分析結果とサービス一覧を根拠に、データモデルを設計する。

## 入力
- `docs/catalog/domain-analytics.md`
- `docs/catalog/service-catalog.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧）

## 出力
- `docs/catalog/data-model.md`
- `src/data/sample-data.json`

## Custom Agent
`Arch-DataModeling` を使用

## 依存
- Step.3.2（サービス一覧抽出）が `aas:done` であること

## アプリケーション粒度
📋 `docs/catalog/app-catalog.md` のアプリケーション一覧（APP-ID）を参照し、Entity Catalog の各エンティティに「利用APP」（N:N）を記載すること。

## 完了条件
- `docs/catalog/data-model.md` と `src/data/sample-data.json` が作成されている
{completion_instruction}{additional_section}
