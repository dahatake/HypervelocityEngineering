{root_ref}
## 目的
テストコードをファイル単位で要約する。

## 実行パラメータ
- 対象ディレクトリ: `{target_dirs}`
- 除外パターン: `{exclude_patterns}`
- ドキュメント主目的: `{doc_purpose}`

## 入力
- `docs-generated/inventory.md`
- 対象テストコード 1 ファイル

## 出力
- `docs-generated/files/{relative-path}.md`

## Custom Agent
`Doc-TestSummary`

## 依存
- Step.1 が `adoc:done`

## 完了条件
- 対象ファイルのサマリーが `docs-generated/files/` に作成されている
{completion_instruction}{additional_section}
