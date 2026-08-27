{root_ref}
## 目的
設計書由来のデータフローアプリ（ジョブ）候補を `docs/dataflow/dataflow-app-catalog.md` へ追記する。ADFD Step 0.2 が本表を確定させる前提の候補である。

## Custom Agent
`Doc-OriginalDownstreamSeed`

## 実行パラメータ

| パラメータ | 値 |
|-----------|---|
| purpose | `{adi_purpose}` |

## 入力
- `docs/catalog/design-doc-routing.md`（Step 4 のルーティング表。`→ ADFD（Job-ID）` 列を使う）
- `docs/original-design-doc-ingest/*/card.md`（`doc_kind` / `job_ids` / 文脈）
- `docs/dataflow/dataflow-app-catalog.md`（**存在する場合は全文を読む**。既存記述は保持する）

## 出力
- `docs/dataflow/dataflow-app-catalog.md`

## 対象文書の絞り込み
ルーティング表の判定が `must` / `should` で、かつ Doc Card の `doc_kind` が `batch-job-spec` である文書のみを対象とする。
該当が 0 件の場合は候補セクションに `なし` と明記する。

## Job-ID の扱い
Doc Card の `job_ids` は**原本に記載されていた識別子**であり、ADI が採番したものではない。
`job_ids` がある場合は `根拠` 列に「原本記載の Job-ID: `<値>`」として記録する。
**`候補` 列には書かない**（採番済み ID とみなされ検証で拒否されるため）。
`job_ids` が空の文書は、業務名で候補を立てる。

{existing_artifact_policy}

## 完了条件
- `docs/dataflow/dataflow-app-catalog.md` に `## 設計書由来の候補（ADI）` セクションがある
- 候補行すべてに出典 `doc_id`（`DOC-NNNN`）と `content.md` のパスがある
- 候補列に採番済み ID が含まれていない（原本の Job-ID は `根拠` 列に記録する）
- 候補セクション以外の既存記述が変更されていない
- 下流ワークフロー（ADFD）を起動していない{additional_section}
