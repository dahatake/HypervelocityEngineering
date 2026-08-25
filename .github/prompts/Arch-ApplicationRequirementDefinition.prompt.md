> Use this when ARD Step 4.2 must create or update one canonical requirement document for every APP in app-catalog.

## 共通ルール

`.github/copilot-instructions.md` と Skill `agent-common-preamble` を継承する。

## 目的

`docs/catalog/app-catalog.md` の APP を出現順に処理し、各 APP の要求定義書を単一エージェントで順次 upsert する。

## 必須入力

- `docs/catalog/app-catalog.md`
- `docs/catalog/use-case-catalog.md`
- 存在する `docs/architectural-requirements-app-NNN.md`
- 明示添付資料と回答済み QA（存在する場合）
- staleness 合格済み `knowledge/` 文書（必要な場合のみ）

## 出力契約

APP-ID `APP-NNN` ごとに `docs/architectural-requirements-app-NNN.md` を出力する。各文書は次を正確に持つ。

- `Schema-Version: 1`
- `APP-ID: APP-NNN`
- `APP名: <app-catalogの名称>`
- `Document-Status: active`
- 見出し `## Requirements`
- 固定表:

| Requirement ID | Status | Requirement | Source | Acceptance Criteria | Blocker |
|---|---|---|---|---|---|

Requirement ID は `APP-NNN-FR-NNN` / `APP-NNN-NFR-NNN` / `APP-NNN-C-NNN` のいずれかとし、kindごとに `001`〜`999` を使う。Status は `confirmed` / `source-backed` / `TBD`、Blocker は `yes` / `no` だけを使う。

## 根拠の優先順位

既存 confirmed > 明示添付 / 回答済み QA > ARD 成果物 > staleness 合格済み knowledge > 推論 TBD

- 上位根拠と競合する場合は上書きせず Blocker として停止する。
- Source は実在する文書・節・回答を記録し、根拠が無い場合は `TBD` とする。
- `TBD` を確定要件として書かない。

## upsert 規則

- 既存 confirmed 行の ID と内容を変更しない。
- 既存 source-backed 行の IDを変更しない。
- 人手追記を削除しない。
- 既存IDを再番号付けしない。
- 新規IDは同じAPP・kindの最大番号の次を割り当てる。999超過時は停止する。
- app-catalogから消えたAPPのorphan文書を削除せず、完了報告へ警告として列挙する。

## 実行手順

1. app-catalogからAPP-IDとAPP名を出現順に抽出する。
2. 単一エージェント内で1 APPずつ処理する。fan-out しない。
3. 既存文書があれば検証してからupsertし、なければschemaに従って新規作成する。
4. 全APPのcanonical fileが存在し、schemaを満たすことを確認する。
5. orphanは保持して警告する。

## 禁止事項

- APP間の並列書込み
- 根拠のないID、要件、数値、Sourceの生成
- 既存confirmed内容、source-backed ID、人手追記、orphan文書の削除
- 要求表以外の非決定的な独自schema追加

## 完了報告

- 処理APP数、作成数、更新数、競合Blocker数、orphan数を記録する。
- 検証マーカーを含める。
