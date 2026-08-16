{root_ref}
## 目的
設計書由来のアプリケーション候補・ドメイン知見・データモデル候補を AAS の 3 成果物へ追記する。AAS が正式な `APP-` / エンティティ定義を確定させる前提の、採番前の候補である。

## Custom Agent
`Doc-OriginalDownstreamSeed`

## 実行パラメータ

| パラメータ | 値 |
|-----------|---|
| purpose | `{adi_purpose}` |

## 入力
- `docs/catalog/design-doc-routing.md`（Step 4 のルーティング表）
- `docs/original-design-doc-ingest/*/card.md`（`doc_kind` / 文脈）
- `docs/catalog/app-catalog.md` / `docs/catalog/domain-analytics.md` / `docs/catalog/data-model.md`（**存在する場合は全文を読む**。既存記述は保持する）

## 出力
- `docs/catalog/app-catalog.md`
- `docs/catalog/domain-analytics.md`
- `docs/catalog/data-model.md`

## 対象文書の絞り込み（出力ファイルごとに異なる）

| 出力ファイル | 対象とする `doc_kind` | 候補の粒度 |
|---|---|---|
| `app-catalog.md` | `architecture-diagram` | 1 アプリケーション相当のまとまりにつき 1 候補。**`APP-` を含む名称を書かない** |
| `domain-analytics.md` | `business-flow` / `glossary` | 1 業務ドメイン／用語群につき 1 候補 |
| `data-model.md` | `data-model` | 1 エンティティにつき 1 候補。エンティティ名は原本の表記をそのまま使う |

いずれもルーティング表の判定が `must` / `should` の文書に限る。
該当が 0 件のファイルには、候補セクションに `なし` と明記する。**3 ファイルすべてにセクションを作る**。

{existing_artifact_policy}

## 完了条件
- 3 ファイルすべてに `## 設計書由来の候補（ADI）` セクションがある（0 件の場合も `なし` と明記）
- 候補行すべてに出典 `doc_id`（`DOC-NNNN`）と `content.md` のパスがある
- 候補列に `APP-` / `SVC-` 等の採番済み ID が含まれていない
- 候補セクション以外の既存記述が変更されていない
- 下流ワークフロー（AAS）を起動していない{additional_section}
