{root_ref}
## 目的
Doc Card 群を目的（`purpose`）に照らして 3 段階でトリアージし、採否と理由を明記した設計書カタログを生成する。

## Custom Agent
`Doc-OriginalTriage`

## 実行パラメータ

| パラメータ | 値 |
|-----------|---|
| purpose | `{adi_purpose}` |

> `purpose` が `未指定` の場合は目的非依存モードで実行し、**`must` を付与しない**（`should` / `may` / `out` の 3 値）。

## 入力
- `docs/catalog/design-doc-inventory.md`（全 `doc_id` の一覧）
- `docs/original-design-doc-ingest/*/card.md`（全 Doc Card）
- `docs/original-design-doc-ingest/index.json`（`excluded` / `duplicate_of`）

## 出力
- `docs/catalog/design-doc-catalog.md`

{existing_artifact_policy}

## 完了条件
- 目録の全 `doc_id` がいずれかの節に 1 回だけ掲載されている
- `out` 判定の全行に除外理由がある
- `purpose` が `未指定` のとき `must` 節に行が無い
- `must` の依存文書が `should` へ昇格されている
- 該当 0 件の節も「なし」と明記されている{additional_section}
