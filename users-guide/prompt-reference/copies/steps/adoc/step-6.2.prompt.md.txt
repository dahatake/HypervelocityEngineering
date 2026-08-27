{root_ref}
## 目的
リファクタリングガイドを生成する。

## 実行パラメータ
- ドキュメント主目的: `{doc_purpose}`

## 入力
- `docs-generated/architecture/dependency-map.md`
- `docs-generated/architecture/nfr-analysis.md`
- `docs-generated/components/tech-debt.md`

## 出力
- `docs-generated/guides/refactoring.md`

{existing_artifact_policy}

## Custom Agent
`Doc-Refactoring`

## 依存
- Step.5.2 / Step.5.4 / Step.3.5 が `adoc:done`

## 完了条件
- `docs-generated/guides/refactoring.md` が作成されている
{completion_instruction}{additional_section}
