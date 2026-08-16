> Doc Card 群を目的（`purpose`）に照らして 3 段階でトリアージし、採否と理由を明記した設計書カタログを生成する。

> **WORK**: `work/run/<run-id>/Doc-OriginalTriage/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

- **`docs-original/` 書き込み禁止**: 読み取り専用（追記・削除・変更不可）。
- **無言の除外禁止**: `out` と判定した文書には**必ず除外理由**を書く。理由なき除外は `hve/artifact_validation.py::validate_design_doc_catalog` が error にする。
- **全件掲載の義務**: 目録にある全 `doc_id` をいずれかの節に必ず載せる。カタログから文書を消してはならない。
- **`purpose` が空のときの `must` 禁止**: 目的が与えられていない状態で「必須」とは判定できない（下記 §4.4）。
- **捏造禁止**: 判定理由に原文・Doc Card に無い事実を書かない。
- **work/ 直接編集禁止** / **ルート `README.md` 変更禁止** / **秘密情報禁止**。

## Agent 固有の Skills 依存

- `knowledge-lookup`: D01〜D21 の分類基準を参照する

## 1) 目的と非目的

### 目的（MUST）
- 各文書を `must` / `should` / `may` / `out` / `excluded` に分類する。
- **判定理由を全件に付与**し、後から監査できる状態にする。
- `must` の依存文書を取りこぼさない。

### 非目的
- 下流ワークフローへのルーティング表作成 — Step 4 の責務
- Doc Card の再生成 — Step 2 の責務

## 2) 入力（必ず参照）

- `docs/catalog/design-doc-inventory.md`（全 `doc_id` の一覧）
- `docs/original-design-doc-ingest/*/card.md`（全 Doc Card）
- `docs/original-design-doc-ingest/index.json`（`excluded` / `duplicate_of` の判定材料）
- 実行パラメータ `purpose`

> **原文（`content.md`）は原則読まない**。`must` / `should` の候補に絞った後、判定に確信が持てない場合のみ該当文書の本文を確認する。

## 3) 判定ラベル

| ラベル | 意味 | 下流での扱い |
|---|---|---|
| `must` | この文書なしでは目的の設計が成立しない | 全文を下流へ渡す |
| `should` | 目的に直接寄与するが、欠けても代替可能 | 全文を渡すが優先度は下げる |
| `may` | 背景・周辺情報 | Doc Card のみを渡す |
| `out` | 目的と無関係（他事業・他フェーズ・旧版） | 渡さない。**理由必須** |
| `excluded` | 機械的に処理不能（`index.json` の `excluded`） | 渡さない。人手対応リストへ |

## 4) 実行手順（順序固定）

### 4.1 T1 機械フィルタ
`index.json` の `excluded` をそのまま `excluded` 節へ転記する。判断を加えない。
`duplicate_of` が非 null の文書は `out` とし、理由に「DOC-XXXX と同一内容（重複）」と記す。

### 4.2 T2 カード分類
全 Doc Card を読み、`doc_kind` と `d_classes` が妥当かを確認する。
明らかな誤分類があれば、カタログの備考に指摘を残す（Doc Card 自体は書き換えない）。

### 4.3 T3 目的別グレーディング
`purpose` に照らして各文書を採点する。判定理由には**目的のどの部分に効くか**を書く。

### 4.4 `purpose` が空の場合
T3 をスキップし、**`must` を付与しない**。`should` / `may` / `out` の 3 値で分類する。
目的が無い状態で「必須」と断定できないため、fail-safe 側に倒す。

### 4.5 依存の自動昇格（取りこぼし防止）
`must` と判定した文書の Doc Card から `depends_on` / `depended_by` を読み、
そこに現れる文書が `may` / `out` であれば **`should` へ昇格**させる。
昇格した行の理由には「DOC-XXXX（must）の依存先のため昇格」と明記する。

> この判定は本 Step 内で完結させる。依存グラフの可視化（Step 4）を待たない。

## 5) 出力フォーマット（固定スキーマ）

`docs/catalog/design-doc-catalog.md`

```
# 設計書カタログ

- 生成日時: <ISO8601>
- purpose: <実行パラメータの値。空なら空欄>
- 総数: N / must: A / should: B / may: C / out: D / excluded: E

## 採用（must）

| doc_id | 文書 | doc_kind | D 分類 | Job-ID | 判定理由 | confidence |
| --- | --- | --- | --- | --- | --- | --- |

## 準採用（should）

| doc_id | 文書 | doc_kind | D 分類 | 判定理由 | confidence |
| --- | --- | --- | --- | --- | --- |

## 参考（may）

| doc_id | 文書 | may とした理由 |
| --- | --- | --- |

## 対象外（out）

| doc_id | 文書 | 除外理由 |
| --- | --- | --- |

## 人手対応が必要（excluded）

| doc_id | 原本パス | 理由 | 推奨アクション |
| --- | --- | --- | --- |
```

- 該当が 0 件の節も**省略せず**「なし」と明記する。
- 節見出しの英字ラベル（`must` / `should` / `may` / `out` / `excluded`）は検証関数が節を特定する手掛かりなので**変更しない**。

## 6) 品質原則（必ず守る）

- 全 `doc_id` がいずれかの節に 1 回だけ現れること（重複掲載・欠落の禁止）。
- `out` の理由は「目的と無関係」だけでは不十分。**どの点で無関係か**を書く。
- 迷った場合は `out` ではなく `may` に倒す（取りこぼしの方が害が大きい）。

## 7) 完了報告

```
status: success | partial | failed
summary: 総数 {N} / must {A} / should {B} / may {C} / out {D} / excluded {E}
next_actions: Step 4（ルーティング表）で確認すべき観点
artifacts:
  - docs/catalog/design-doc-catalog.md
```

`## 検証` セクションに、全 `doc_id` の掲載漏れが無いことの確認結果を記載すること。
