{root_ref}
## 目的
モデル関連サマリーからデータモデル定義書を生成する。

## 入力
- `docs-generated/files/*.md`（Step.2.x 成果物）

## 出力
- `docs-generated/components/data-model.md`

{existing_artifact_policy}

## Custom Agent
`Doc-DataModel`

## 依存
- Step.2.1〜Step.2.5 が `adoc:done`

## 完了条件
- `docs-generated/components/data-model.md` が作成されている
{completion_instruction}{additional_section}
