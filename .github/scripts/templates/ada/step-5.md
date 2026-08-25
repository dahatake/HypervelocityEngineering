{root_ref}
## 目的
データモデルとドメイン分析を根拠に、概念エンティティ × 物理テーブル/列のマッピング、所有権、PII 区分、ライフサイクルを記録するデータカタログを作成する。AI Agent の構造化データ側の正本となる。

## 入力
- `docs/catalog/data-model.md`（必須）
- `docs/catalog/domain-analytics.md`（必須）
- `docs/catalog/app-catalog.md`（必須）
- `docs/catalog/service-catalog.md`（必須）

## 出力
- `docs/catalog/data-catalog.md`

{existing_artifact_policy}

## Custom Agent
`Arch-DataCatalog` を使用

## 依存
- Step.4.1（データモデル設計）が `ada:done` であること

## ADA 固有の注意
`docs/catalog/service-catalog-matrix.md` は ADA では生成しない（画面キーの表のため）。存在しない前提で進め、参照しない。

## アプリケーション粒度
📋 `docs/catalog/app-catalog.md` のアプリケーション一覧（APP-ID）を参照し、Entity-Table Mapping および Ownership Matrix に「利用APP」（N:N）を記載すること。

## 完了条件
- `docs/catalog/data-catalog.md` が作成されている
{completion_instruction}{additional_section}
