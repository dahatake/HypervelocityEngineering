{root_ref}
## 目的
正規化済みの設計書 1 件（`{key}`）について、文脈カード（Doc Card）を生成する。

## Custom Agent
`Doc-OriginalDocCard`

## 実行パラメータ

| パラメータ | 値 |
|-----------|---|
| purpose | `{adi_purpose}` |

> `purpose` は Step 3（トリアージ）で使用する。本 Step では採否判定を行わない。

## 入力
- `docs/original-design-doc-ingest/index.json`（ 担当 `{key}` のエントリ）
- `docs/original-design-doc-ingest/<slug>/content.md`（担当文書の正規化済み本文）
- `template/business-requirement-document-master-list.md`（D01〜D21 の分類基準）

## 出力
- `docs/original-design-doc-ingest/<slug>/card.md`

{existing_artifact_policy}

## 完了条件
- `card.md` の front matter に `doc_id` / `source_path` / `source_sha256` / `d_classes` / `confidence` が揃っている
- `confidence` が `high` / `medium` / `low` のいずれかである
- `## 文脈` セクションに 200〜400 字の位置づけ説明がある
- 原文に無い依存関係・ID を書いていない{additional_section}
