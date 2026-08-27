> `docs-original/` 配下の原本を決定的に走査・正規化し、機械可読な目録（`docs/original-design-doc-ingest/index.json`）を人間可読な設計書インベントリへ変換する。

> **WORK**: `work/run/<run-id>/Doc-OriginalInventory/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

> 共通行動規約 (`.github/copilot-instructions.md` §0 / Skill `agent-common-preamble`) の禁止事項を本 Agent でも明示する。

- **`docs-original/` 書き込み禁止**: 読み取り専用（追記・削除・変更不可）。CI ジョブ `check-docs-original` が違反を fail させる。
- **捏造禁止**: 件数・ファイル名・拡張子を推測で書かない。すべて `index.json` の実値を転記する。
- **無関係変更禁止**: スコープ外のファイル整形・一括リファクタを行わない（最小差分）。
- **内容の要約禁止**: 本 Step では原本の**中身を読まない**。目録化のみを行う。要約は Doc Card（Step 2）の責務。
- **work/ 直接編集禁止**: 既存 `work/` ファイルは「削除 → 新規作成」（Skill `work-artifacts-layout` §4.1）。
- **ルート `README.md` 変更禁止**。
- **秘密情報禁止**: 鍵 / トークン / 個人情報 / 内部 URL 等を成果物に含めない。

## Agent 固有の Skills 依存

- `knowledge-lookup`: D01〜D21 の分類語彙を参照する場合のみ
- `work-artifacts-layout`: 出力先は Body テンプレートの `## 出力` に従う

## 1) 目的と非目的

### 目的（MUST）
- `python -m hve ingest-docs` を実行して `docs/original-design-doc-ingest/` を最新化する。
- `docs/original-design-doc-ingest/index.json` を人間可読な設計書インベントリ（`docs/catalog/design-doc-inventory.md`）へ変換する。
- 変換失敗・未対応形式・重複を**件数と理由付き**で明示する。

### 非目的
- 原本の内容分析・要約・分類（Doc Card = Step 2 の責務）
- 目的に基づく採否判定（トリアージ = Step 3 の責務）
- 図の解釈（Phase 3 の責務）

## 2) 入力（必ず参照）

- `docs/original-design-doc-ingest/index.json`（本 Step が生成する）
- （任意）`docs/original-design-doc-ingest/<slug>/provenance.json` — 変換来歴の確認が必要な場合のみ

> 原本（`docs-original/**`）の**本文は読まない**。ファイルの存在と属性は `index.json` から取得する。

## 3) 出力フォーマット（Markdown 固定スキーマ）

`docs/catalog/design-doc-inventory.md`

**第 1 列は必ず `doc_id`**（`hve/catalog_parsers.py` の `parse_design_doc_inventory` が第 1 列から `DOC-NNNN` を抽出して fan-out キーにするため。列順を変更してはならない）。

```
| doc_id | 原本パス | 拡張子 | 変換 | バイト数 | 重複元 | 備考 |
| --- | --- | --- | --- | --- | --- | --- |
| DOC-0001 | 30404_モデル作成.md | .md | passthrough | 8123 | — | — |
```

加えて以下のセクションを設ける。

- `## サマリー`: 取り込み件数 / 除外件数 / 重複件数
- `## 除外一覧`: `| 原本パス | 理由 | 推奨アクション |`（除外が 0 件なら「なし」と明記）
- `## 重複一覧`: `| doc_id | 原本パス | 重複元 doc_id |`（0 件なら「なし」と明記）

## 4) 実行手順（順序固定）

1. `python -m hve ingest-docs` を実行する。
   - 失敗した場合は標準エラー出力をそのまま completion report に転記し、**目録を捏造しない**。
   - `MaxDocsExceededError` が出た場合は fail-closed。対象の分割をユーザーへ促して中断する。   - **shell allowlist により当該コマンドを実行できない場合**は、代替実装を自作せずに
     `status: blocked` として中断し、実行できなかったコマンド名を completion report に記載する。
     （Agent が手作業で走査・変換すると決定性が失われ、FR-WF-ADI-01 に違反する）2. `docs/original-design-doc-ingest/index.json` を読む。
3. `docs` 配列を `doc_id` 昇順のまま §3 のテーブルへ転記する。
4. `excluded` 配列を「除外一覧」へ転記する。
5. `duplicate_of` が非 null の要素を「重複一覧」へ転記する。
6. サマリーの 3 件数を計上する。

## 5) 品質原則（必ず守る）

- 捏造は絶対に禁止。すべての行は `index.json` の実値に基づくこと。
- `index.json` に無い列（推測した文書種別・重要度など）を追加しないこと。
- 除外・重複が 0 件の場合も、セクションを省略せず「なし」と明記すること。
- 不明点は `TBD（推論: ...）` と明記すること。

## 6) 完了報告

以下を completion report（PR body または `completion-report.md`）に記載する。

```
status: success | partial | failed
summary: 取り込み {N} 件 / 除外 {M} 件 / 重複 {K} 件
next_actions: Step 2（Doc Card 生成）で確認すべき観点
artifacts:
  - docs/catalog/design-doc-inventory.md
  - docs/original-design-doc-ingest/index.json
```

`## 検証` セクションに、`python -m hve ingest-docs` の終了コードと件数を記載すること。
