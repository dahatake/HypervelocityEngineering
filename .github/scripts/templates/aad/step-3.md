<!-- DEPRECATED: このテンプレートは templates/aas/step-5.md に移動しました。 -->
{root_ref}
## 目的
データモデルとドメイン分析を根拠に、概念エンティティ × 物理テーブル/列のマッピングを記録するデータカタログを作成する。

## 入力
- `docs/catalog/data-model.md`（必須）
- `docs/catalog/domain-analytics.md`（必須）
- `docs/catalog/app-catalog.md`（アプリケーション一覧）
- `docs/catalog/service-catalog.md`（存在すれば参照）
- `docs/catalog/service-catalog-matrix.md`（存在すれば参照）

## 出力
- `docs/catalog/data-catalog.md`

## Custom Agent
`Arch-DataCatalog` を使用

## 依存
- Step.2（データモデル作成）が `aad:done` であること

## アプリケーション粒度
📋 `docs/catalog/app-catalog.md` のアプリケーション一覧（APP-ID）を参照し、Entity-Table Mapping および Ownership Matrix に「利用APP」（N:N）を記載すること。

## 完了条件
- `docs/catalog/data-catalog.md` が作成されている
{completion_instruction}{additional_section}
