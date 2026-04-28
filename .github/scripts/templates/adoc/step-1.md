{root_ref}
## 目的
対象範囲のファイルインベントリを作成し、後続ステップ用の入力一覧を確定する。

## 実行パラメータ
- 対象ディレクトリ: `{target_dirs}`
- 除外パターン: `{exclude_patterns}`
- ドキュメント主目的: `{doc_purpose}`
- 大規模ファイル閾値: `{max_file_lines}` 行

## 入力
- リポジトリのディレクトリツリー

## 出力
- `docs-generated/inventory.md`

## Custom Agent
`Doc-FileInventory`

## 依存
- なし（最初に実行）

## 完了条件
- `docs-generated/inventory.md` が作成されている
{completion_instruction}{additional_section}
