# AQOD Fan-out per-D{{key}} 追加指示

このサブタスクは AQOD ワークフロー Step 1 の fan-out 子であり、
**ドキュメント `{{key}}` のみ** を対象として original-docs 質問票を生成する。

## 必須参照

1. `template/business-requirement-document-master-list.md` の `{{key}}.` セクション
2. `knowledge/{{key}}-*.md`（あれば）
3. `original-docs/` 配下で `{{key}}` 関連と思われる資料（読み取り専用）

## 成果物

- `qa/{{key}}-original-docs-questionnaire.md` を新規作成（既存があれば work-artifacts-layout §4.1 で削除→新規作成）

## 並列実行ルール

- 他 D## の質問票には触らない。
- `original-docs/` への書き込みは禁止（`.github/copilot-instructions.md` §0）。


## オーバーエンジニアリング禁止（共通ルール）

- **オーバーエンジニアリングは絶対に禁止**です。
- 指示・要件にない未来予測的な汎用化・抽象化・将来拡張点の先回り追加を行わないこと。
- YAGNI（必要になるまで実装しない原則）に違反する設計・記述を行わないこと。
- 未使用の設定オプション・フラグ・抽象レイヤー・予防的なエラーハンドリングを追加しないこと。
- 禁止事項の優先順位: 捏造禁止 > オーバーエンジニアリング禁止 > 最小差分原則。
