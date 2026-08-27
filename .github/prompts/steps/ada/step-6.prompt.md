{root_ref}
## 目的
ユースケースのアクター記述から、AI Agent の権限主体となるペルソナを抽出する。AG-CAP-07 の権限設計の入力となる。

## 入力
- `docs/catalog/use-case-catalog.md`（必須・一次ソース）
- `docs/catalog/app-catalog.md`（必須）

## 出力
- `docs/catalog/persona-catalog.md`

{existing_artifact_policy}

## Custom Agent
`Arch-PersonaCatalog` を使用

## 依存
- Step.5（データカタログ作成）が `ada:done` であること

## ADA 固有の注意
本ワークフローは画面を作らないため、ペルソナ別共通画面カタログ（AAS Step.8 相当）は生成しない。

## 完了条件
- `docs/catalog/persona-catalog.md` が作成されている
{completion_instruction}{additional_section}
