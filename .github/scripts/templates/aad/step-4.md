<!-- DEPRECATED: このテンプレートは templates/aad-web/step-1.md に移動しました。 -->
{root_ref}
## 目的
ドメイン分析結果、サービス一覧、データモデルを根拠に画面一覧を設計する。

## 入力
- `docs/catalog/domain-analytics.md`
- `docs/catalog/service-catalog.md`
- `docs/catalog/data-model.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧）

## 出力
- `docs/catalog/screen-catalog.md`

## Custom Agent
`Arch-UI-List` を使用

## 依存
- Step.3（データカタログ）が `aad:done` であること（Step.3 がスキップ時は Step.2（データモデル）が `aad:done` であること）

## アプリケーション粒度
📋 `docs/catalog/app-catalog.md` のアプリケーション一覧（APP-ID）を参照し、各画面に「所属APP」（1:1）を記載すること。

## 完了条件
- `docs/catalog/screen-catalog.md` が作成されている
{completion_instruction}{additional_section}
