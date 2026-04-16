{root_ref}
## 目的
移行アセスメントを生成する。

## 実行パラメータ
- ドキュメント主目的: `{doc_purpose}`

## 入力
- `docs-generated/architecture/overview.md`
- `docs-generated/architecture/infra-deps.md`
- `docs-generated/architecture/nfr-analysis.md`

## 出力
- `docs-generated/guides/migration-assessment.md`

## Custom Agent
`Doc-Migration`

## 依存
- Step.5.1 / Step.5.3 / Step.5.4 が `adoc:done`

## 完了条件
- `docs-generated/guides/migration-assessment.md` が作成されている
- 完了時に自身に `adoc:done` ラベルを付与すること{additional_section}
