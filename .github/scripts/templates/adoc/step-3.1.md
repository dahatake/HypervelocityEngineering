{root_ref}
## 目的
ファイルサマリー群からコンポーネント設計書を生成する。

## 実行パラメータ
- ドキュメント主目的: `{doc_purpose}`

## 入力
- `docs-generated/files/*.md`（Step.2.x 成果物）

## 出力
- `docs-generated/components/{module-name}.md`

{existing_artifact_policy}

## Custom Agent
`Doc-ComponentDesign`

## 依存
- Step.2.1〜Step.2.5 が `adoc:done`

## 完了条件
- コンポーネント設計書が `docs-generated/components/` に作成されている
{completion_instruction}{additional_section}
