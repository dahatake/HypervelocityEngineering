{root_ref}
## 目的
データモデルとドメイン分析を根拠に、概念エンティティ × 物理テーブル/列のマッピングを記録するデータカタログを作成する。

## 入力
- `docs/data-model.md`（必須）
- `docs/domain-analytics.md`（必須）
- `docs/app-list.md`（アプリケーション一覧）
- `docs/service-list.md`（存在すれば参照）
- `docs/service-catalog.md`（存在すれば参照）

## 出力
- `docs/data-catalog.md`

## Custom Agent
`Arch-DataCatalog` を使用

## 依存
- Step.2（データモデル作成）が `aad:done` であること

## アプリケーション粒度
📋 `docs/app-list.md` のアプリケーション一覧（APP-ID）を参照し、Entity-Table Mapping および Ownership Matrix に「利用APP」（N:N）を記載すること。

## 完了条件
- `docs/data-catalog.md` が作成されている
- 完了時に自身に `aad:done` ラベルを付与すること{additional_section}
