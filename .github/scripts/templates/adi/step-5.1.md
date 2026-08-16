{root_ref}
## 目的
設計書由来のユースケース候補を `docs/catalog/use-case-skeleton.md` へ追記する。ARD Step 3.1 が正式な `UC-` を採番して本表へ統合する前提の、採番前の候補である。

## Custom Agent
`Doc-OriginalDownstreamSeed`

## 実行パラメータ

| パラメータ | 値 |
|-----------|---|
| purpose | `{adi_purpose}` |

## 入力
- `docs/catalog/design-doc-routing.md`（Step 4 のルーティング表）
- `docs/original-design-doc-ingest/*/card.md`（`doc_kind` / 文脈）
- `docs/catalog/use-case-skeleton.md`（**存在する場合は全文を読む**。既存記述は保持する）

## 出力
- `docs/catalog/use-case-skeleton.md`

## 対象文書の絞り込み
ルーティング表の判定が `must` / `should` で、かつ Doc Card の `doc_kind` が
`business-flow` / `ops-runbook` のいずれかである文書のみを対象とする。
該当が 0 件の場合は候補セクションに `なし` と明記する。

## 候補の粒度
1 つの業務フローにつき 1 候補。**`UC-` を含む名称を書かない**（採番は ARD の責務）。

{existing_artifact_policy}

## 完了条件
- `docs/catalog/use-case-skeleton.md` に `## 設計書由来の候補（ADI）` セクションがある
- 候補行すべてに出典 `doc_id`（`DOC-NNNN`）と `content.md` のパスがある
- 候補列に `UC-` 等の採番済み ID が含まれていない
- 候補セクション以外の既存記述が変更されていない
- 下流ワークフロー（ARD）を起動していない{additional_section}
