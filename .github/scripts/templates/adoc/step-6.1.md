{root_ref}
## 目的
オンボーディングガイドを生成する。

## 実行パラメータ
- ドキュメント主目的: `{doc_purpose}`

## 入力
- `docs-generated/architecture/overview.md`
- `docs-generated/architecture/dependency-map.md`

## 出力
- `docs-generated/guides/onboarding.md`

## Custom Agent
`Doc-Onboarding`

## 依存
- Step.5.1 / Step.5.2 が `adoc:done`

## 完了条件
- `docs-generated/guides/onboarding.md` が作成されている
- 完了時に自身に `adoc:done` ラベルを付与すること{additional_section}
