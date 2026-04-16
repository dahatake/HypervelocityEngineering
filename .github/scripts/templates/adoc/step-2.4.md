{root_ref}
## 目的
CI/CD ファイルをファイル単位で要約する。

## 実行パラメータ
- 対象ディレクトリ: `{target_dirs}`
- 除外パターン: `{exclude_patterns}`
- ドキュメント主目的: `{doc_purpose}`

## 入力
- `docs-generated/inventory.md`
- 対象 CI/CD 定義ファイル 1 つ

## 出力
- `docs-generated/files/{relative-path}.md`

## Custom Agent
`Doc-CICDSummary`

## 依存
- Step.1 が `adoc:done`

## 完了条件
- 対象ファイルのサマリーが `docs-generated/files/` に作成されている
- 完了時に自身に `adoc:done` ラベルを付与すること{additional_section}
