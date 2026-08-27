{root_ref}
## 目的
大規模ファイルを分割して要約し、統合サマリーを作成する。

## 実行パラメータ
- 対象ディレクトリ: `{target_dirs}`
- 除外パターン: `{exclude_patterns}`
- 大規模ファイル閾値: `{max_file_lines}` 行

## 入力
- `docs-generated/inventory.md`
- 閾値超過のファイル分割セクション

## 出力
- `docs-generated/files/{relative-path}.md`

{existing_artifact_policy}

## Custom Agent
`Doc-LargeFileSummary`

## 依存
- Step.1 が `adoc:done`

## 完了条件
- 対象ファイルの統合サマリーが `docs-generated/files/` に作成されている
{completion_instruction}{additional_section}
