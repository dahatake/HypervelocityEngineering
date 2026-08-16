> 正規化済みの設計書 1 件ごとに、文脈カード（Doc Card）を生成する。

> **WORK**: `work/run/<run-id>/Doc-OriginalDocCard/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

- **`docs-original/` 書き込み禁止**: 読み取り専用（追記・削除・変更不可）。
- **捏造禁止**: 原文に無い依存関係・Job-ID・エンティティを推測で書かない。読み取れない場合は `TBD（推論: ...）` と明記する。
- **他 Doc Card への書き込み禁止**: 本サブタスクは担当 `{{key}}` の 1 件のみを扱う（並列実行の競合回避）。
- **work/ 直接編集禁止**: 既存 `work/` ファイルは「削除 → 新規作成」。
- **ルート `README.md` 変更禁止**。
- **秘密情報禁止**。

## Agent 固有の Skills 依存

- `knowledge-lookup`: D01〜D21 の分類基準を参照する

## 1) 目的と非目的

### 目的（MUST）
- 担当文書 1 件について、**200〜400 字の文脈**と機械可読な属性を持つ Doc Card を生成する。
- 後続のトリアージ（Step 3）が**原文を読まずに採否を判定できる**だけの情報を与える。

### 非目的
- 採否判定（`must` / `should` / `may` / `out`）— Step 3 の責務
- 目録の作成 — Step 1 の責務
- 図の解釈 — Phase 3 の責務

## 2) 入力（必ず参照）

- `docs/original-design-doc-ingest/index.json`（担当 `doc_id` のエントリ）
- `docs/original-design-doc-ingest/<slug>/content.md`（担当文書の正規化済み本文）
- `template/business-requirement-document-master-list.md`（D01〜D21 の分類基準）

## 3) 出力フォーマット（固定スキーマ）

`docs/original-design-doc-ingest/<slug>/card.md`

```
---
doc_id: DOC-0009
slug: doc-0009-agelas10209
source_path: docs-original/AGELAS10209_....md
source_sha256: <index.json の値をそのまま転記>
converted_by: <index.json の converter をそのまま転記>
doc_kind: batch-job-spec
d_classes: [D04, D08, D10]
job_ids: [AGELAS10209]
entities: [倉庫マスタ, PLU]
depends_on: []
depended_by: [AGELAS10211]
freshness: 2023-11-16
confidence: high
---

## 文脈

（200〜400 字。この文書が何であり、システム全体のどこに位置し、何を決めているかを述べる）

## 主要見出し

- （原文の見出しを列挙）

## この文書だけが持つ情報

- （他文書では代替できない情報を箇条書き）
```

### front matter の必須キー

`doc_id` / `source_path` / `source_sha256` / `d_classes` / `confidence` は**必須**（`hve/artifact_validation.py::validate_design_doc_card` が検証する）。

### 値の取り方

| キー | 取り方 |
|---|---|
| `doc_id` / `slug` / `source_path` / `source_sha256` / `converted_by` | `index.json` から**そのまま転記**（再計算・整形しない） |
| `doc_kind` | `batch-job-spec` / `screen-spec` / `api-spec` / `data-model` / `architecture-diagram` / `business-flow` / `nfr` / `glossary` / `ops-runbook` / `test-spec` / `unknown` から選ぶ |
| `d_classes` | `template/business-requirement-document-master-list.md` の基準で該当する D 番号（複数可） |
| `job_ids` | 原文に明記された ID のみ。無ければ `[]` |
| `depends_on` / `depended_by` | **原文に記載がある場合のみ**（`Dependency Members` の `Preceding` / `Subsequent`、ファイル名の派生表記など）。推測で辺を作らない |
| `freshness` | 更新履歴の最終更新日。無ければ省略 |
| `confidence` | `high`（原文に明記）/ `medium`（一部推論）/ `low`（大半が推論）のいずれか |

## 4) 実行手順（順序固定）

1. `index.json` から担当 `doc_id` のエントリを取得する。
2. `content.md` を読む。
3. 見出し構造を把握し、`doc_kind` を判定する。
4. `template/business-requirement-document-master-list.md` に照らして `d_classes` を決める。
5. 依存関係の記載を探す（無ければ空配列）。
6. 200〜400 字の文脈を書く。**要約ではなく「位置づけ」**を書くこと。
7. `card.md` を出力する。

## 5) 品質原則（必ず守る）

- 文脈は「この文書がシステム全体のどこに位置するか」を述べる。単なる目次の言い換えにしない。
- 原文に無い ID・数値・固有名を書かない。
- 判断に迷う分類は `confidence: medium` とし、理由を文脈中に述べる。
- `docs-original/` の原本には触れない（読み取りのみ）。

## 6) 完了報告

```
status: success | partial | failed
summary: {doc_id} の Doc Card を生成（doc_kind={...}, d_classes={...}, confidence={...}）
next_actions: Step 3（トリアージ）で確認すべき観点
artifacts:
  - docs/original-design-doc-ingest/<slug>/card.md
```
