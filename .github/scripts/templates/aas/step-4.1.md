{root_ref}
## 目的
ドメイン分析結果とサービス一覧を根拠に、データモデル（概念モデル + 物理マッピング）を設計する。

## 入力
- `docs/catalog/domain-analytics.md`
- `docs/catalog/service-catalog.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧）

## 出力
- `docs/catalog/data-model.md`

{existing_artifact_policy}

## Custom Agent
`Arch-DataModeling` を使用

## 依存
- Step.3.2（サービス一覧抽出）が `aas:done` であること

## アプリケーション粒度
📋 `docs/catalog/app-catalog.md` のアプリケーション一覧（APP-ID）を参照し、Entity Catalog の各エンティティに「利用APP」（N:N）を記載すること。

## 完了条件
- `docs/catalog/data-model.md` が作成されている
- Sub-4 (B-1) で本ステップから `src/data/sample-data.json` の生成は Step 4.2 へ分離されている
{completion_instruction}{additional_section}
