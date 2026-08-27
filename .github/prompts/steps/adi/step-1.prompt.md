{root_ref}
## 目的
`docs-original/` 配下の原本を決定的に走査・正規化し、`docs/original-design-doc-ingest/index.json` から人間可読な設計書インベントリを生成する。

## Custom Agent
`Doc-OriginalInventory`

## 実行パラメータ

| パラメータ | 値 |
|-----------|---|
| purpose | `{adi_purpose}` |

> `purpose` は Step 3（トリアージ）で使用する。本 Step では採否判定を行わない。

## 入力
- `docs-original/` 配下の原本（**読み取り専用**。本文は読まず、存在と属性のみ `index.json` 経由で扱う）
- `docs/original-design-doc-ingest/index.json`（本 Step が `python -m hve ingest-docs` で生成する）

## 出力
- `docs/catalog/design-doc-inventory.md`

{existing_artifact_policy}

## 完了条件
- `python -m hve ingest-docs` が終了コード 0 で完了している
- `docs/catalog/design-doc-inventory.md` が生成されている
- 第 1 列が `doc_id` のテーブルになっている（fan-out キー抽出の前提）
- 除外・重複が 0 件の場合も該当セクションに「なし」と明記されている
- `docs-original/` 配下に変更が無い{additional_section}
