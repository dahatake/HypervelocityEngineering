> トリアージ結果を下流ワークフロー（AKM / ARD / AAS / ADFD）の入力へ対応づけるルーティング表と、設計書間の依存図を生成する。

> **WORK**: `work/run/<run-id>/Doc-OriginalRouting/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

- **`docs-original/` 書き込み禁止**: 読み取り専用。
- **捏造禁止**: Doc Card に無い依存関係を図に描かない。推測でエッジを追加しない。
- **判定のやり直し禁止**: 採否は Step 3 の結果をそのまま使う。本 Step で `must` / `out` を変更しない。
- **work/ 直接編集禁止** / **ルート `README.md` 変更禁止** / **秘密情報禁止**。

## Agent 固有の Skills 依存

- `knowledge-lookup`: D01〜D21 の対応付けに使用する

## 1) 目的と非目的

### 目的（MUST）
- どの文書が**どの下流ワークフローの入力になるか**を表で明示する。
- Doc Card の `depends_on` / `depended_by` から設計書間の依存図（Mermaid）を生成する。

### 非目的
- 採否の再判定 — Step 3 の責務
- 下流ワークフローの実行 — 本ワークフローの範囲外

## 2) 入力（必ず参照）

- `docs/catalog/design-doc-catalog.md`（Step 3 の判定結果）
- `docs/original-design-doc-ingest/*/card.md`（`d_classes` / `job_ids` / `depends_on` / `depended_by`）

## 3) 出力フォーマット（固定スキーマ）

`docs/catalog/design-doc-routing.md`

```
# 設計書ルーティング表

- 生成日時: <ISO8601>
- 対象: design-doc-catalog.md の must / should

## ルーティング

| doc_id | 判定 | D 分類 | → AKM | → ARD | → AAS | → ADFD（Job-ID） | → 反映先成果物 |
| --- | --- | --- | --- | --- | --- | --- | --- |

## 依存図

（Mermaid。Doc Card に記載がある依存のみを描く）

## D 分類別の担当文書

| D 番号 | 担当する doc_id |
| --- | --- |
```

### 各列の意味

| 列 | 埋め方 |
|---|---|
| `→ AKM` | Doc Card の `d_classes` をそのまま列挙（AKM の fan-out キー `D01`〜`D21` に対応） |
| `→ ARD` | `must` の文書に `content.md` のパスを記す（ARD の `attached_docs` 生成用）。それ以外は `—` |
| `→ AAS` | `doc_kind` が `architecture-diagram` / `business-flow` / `data-model` のとき `app-catalog 候補` |
| `→ ADFD（Job-ID）` | Doc Card の `job_ids` をそのまま列挙。無ければ `—` |
| `→ 反映先成果物` | Step 5.x が候補を追記するファイル名を `doc_kind` から引いて列挙する。`business-flow` / `ops-runbook` → `use-case-skeleton.md`、`architecture-diagram` → `app-catalog.md`、`glossary` → `domain-analytics.md`（`business-flow` も含む）、`data-model` → `data-model.md`、`batch-job-spec` → `dataflow-app-catalog.md`。該当なしは `—` |

## 4) 実行手順（順序固定）

1. カタログから `must` / `should` の `doc_id` を取得する。
2. 各 `doc_id` の Doc Card から `d_classes` / `job_ids` / `depends_on` / `depended_by` を読む。
3. ルーティング表を埋める。
4. 依存図を生成する。**Doc Card に記載がある依存のみ**を描く。
5. 「D 分類別の担当文書」を D01〜D21 の順で埋める。該当なしの D 番号は `—`。

## 5) 品質原則（必ず守る）

- 依存図のエッジは Doc Card の `depends_on` / `depended_by` に**明示されているものだけ**。
  「関連しそう」という理由でエッジを足さない。
- 「D 分類別の担当文書」は AKM の21並列子が直接参照する。D01〜D21を**すべて行として出す**（該当なしも明示）。
- カタログの判定と矛盾する記載をしない。

## 6) 完了報告

```
status: success | partial | failed
summary: must {A} / should {B} をルーティング。依存エッジ {E} 本
next_actions: AKM 実行時の参照方法
artifacts:
  - docs/catalog/design-doc-routing.md
```
