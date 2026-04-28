{root_ref}
## 目的
サービス一覧、データモデル、画面一覧、ドメイン分析を統合してサービスカタログを作成する。

## 入力
- `docs/catalog/service-catalog.md`
- `docs/catalog/data-model.md`
- `docs/catalog/screen-catalog.md`
- `docs/catalog/domain-analytics.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧）

## 出力
- `docs/catalog/service-catalog-matrix.md`

## Custom Agent
`Arch-Microservice-ServiceCatalog` を使用

## 依存
- Step.4（画面一覧と遷移図）が `aas:done` であること

## アプリケーション粒度
📋 `docs/catalog/app-catalog.md` のアプリケーション一覧（APP-ID）を参照し、Table A（画面→API）に「所属APP」（1:1）、Table C（サービス責務）に「利用APP」（N:N）を記載すること。

## 完了条件
- `docs/catalog/service-catalog-matrix.md` が作成されている
{completion_instruction}{additional_section}
