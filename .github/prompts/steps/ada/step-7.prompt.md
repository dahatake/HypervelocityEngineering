{root_ref}
## 目的
各サービスの API I/O・バリデーション・イベント・権限を詳細化する。AI Agent の Tool 定義（AG-CAP-04 REST CRUD Matrix）の根拠となる。

## 入力
- `docs/catalog/service-catalog.md`（必須）
- `docs/catalog/data-catalog.md`（必須）
- `docs/catalog/data-model.md`（必須）
- `docs/catalog/domain-analytics.md`（必須）
- `docs/catalog/app-catalog.md`（必須）

## 出力
- `docs/services/{serviceId}-{serviceNameSlug}-description.md`（サービスごとに 1 ファイル）

{existing_artifact_policy}

## Custom Agent
`Arch-Microservice-ServiceDetail` を使用

## 依存
- Step.5（データカタログ作成）が `ada:done` であること

## ADA 固有の注意
`docs/catalog/screen-catalog-APP-*.md` は ADA では生成しない。画面起点の記述を求められても、**画面を根拠に API を導出しない**。API の導出根拠はユースケース・ドメイン分析・データカタログとする。

## 完了条件
- 対象サービスの詳細仕様ファイルが作成されている
{completion_instruction}{additional_section}
