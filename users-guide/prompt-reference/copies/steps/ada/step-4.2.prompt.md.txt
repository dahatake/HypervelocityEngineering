{root_ref}
## 目的
データモデルに整合するサンプルデータを生成し、後続のテスト・検索経路の実測に使える基準データを用意する。

## 入力
- `docs/catalog/data-model.md`（必須）
- `docs/catalog/domain-analytics.md`（必須）
- `docs/catalog/service-catalog.md`（必須）
- `docs/catalog/app-catalog.md`（必須）

## 出力
- `src/data/sample-data.json`

{existing_artifact_policy}

## Custom Agent
`Arch-DataModeling` を使用

## 依存
- Step.4.1（データモデル設計）が `ada:done` であること

## 完了条件
- `src/data/sample-data.json` が作成されている
{completion_instruction}{additional_section}
