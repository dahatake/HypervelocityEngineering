# ADI Fan-out per-document 追加指示

このサブタスクは ADI ワークフローの fan-out 子ステップであり、
**設計書 `{{key}}` のみ** を対象とする。他の `DOC-` 文書には触らない。

## 対象の特定

1. `docs/catalog/design-doc-inventory.md` の第 1 列から `{{key}}` の行を探す。
2. `docs/original-design-doc-ingest/index.json` の `docs` 配列から `doc_id == "{{key}}"` のエントリを取得する。
3. そのエントリの `slug` が担当ディレクトリ （`docs/original-design-doc-ingest/<slug>/`）である。

## 必須参照

1. `docs/original-design-doc-ingest/<slug>/content.md`（担当文書の正規化済み本文）
2. `template/business-requirement-document-master-list.md` の D01〜D21 分類基準
3. `docs-original/` 配下の原本は**読み取り専用**（変更・削除禁止 — `.github/copilot-instructions.md` §0）

## 並列実行ルール（厳守）

- 担当 `<slug>` 以外のディレクトリへの書き込みは禁止（並列実行中の競合回避）。
- `docs/catalog/` 配下の共通カタログへは書き込まない（Step 3 / Step 4 の責務）。
- 既存ファイルの更新は「削除 → 新規作成」（Skill `work-artifacts-layout` §4.1）。

## 捏造の禁止

- `index.json` から転記すべき値（`doc_id` / `slug` / `source_path` / `source_sha256` / `converted_by`）は
  **再計算・整形せず、そのまま写す**。
- 原文に記載が無い依存関係・Job-ID・エンティティを推測で追加しない。
- 判読できない箇所は `TBD（推論: ...）` と明記する。

## 出力フォーマット

完了時、以下を必ず完了報告に記載する。

```
status: success | partial | failed
summary: {{key}} の Doc Card を生成（doc_kind / d_classes / confidence）
next_actions: トリアージで確認すべき観点（存在すれば）
artifacts:
  - docs/original-design-doc-ingest/<slug>/card.md
```

## オーバーエンジニアリング禁止（共通ルール）

- **オーバーエンジニアリングは絶対に禁止**です。
- 指示・要件にない未来予測的な汎用化・抽象化・将来拡張点の先回り追加を行わないこと。
- YAGNI（必要になるまで実装しない原則）に違反する設計・記述を行わないこと。
- 未使用の設定オプション・フラグ・抽象レイヤー・予防的なエラーハンドリングを追加しないこと。
- 禁止事項の優先順位: 捏造禁止 > オーバーエンジニアリング禁止 > 最小差分原則。
