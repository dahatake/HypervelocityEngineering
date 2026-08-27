# ADI Fan-out per-D{{key}} 追加指示

このサブタスクは ADI ワークフロー Step 1.1 の fan-out 子であり、
**業務分類 `{{key}}` のみ** を対象として正規化済み原本から質問票を生成する。

## 必須参照

1. `template/business-requirement-document-master-list.md` の `{{key}}.` セクション
2. `docs/original-design-doc-ingest/index.json`
3. `docs/original-design-doc-ingest/<slug>/content.md`（`index.json` に列挙された正規化済み本文）
4. `knowledge/{{key}}-*.md`（あれば）

## 対象選定

- `index.json` に列挙された文書を起点とし、各 `content.md` を読んで `{{key}}` の分類基準に照らして関連文書だけを採用する。
- `target_scope` は `\\` を `/` へ変換して末尾 `/` 付きのリポジトリ相対パスへ正規化し、`docs-original/` またはその配下だけを許可する。
- `target_scope` が指定されている場合は、`index.json` の `source_path` が正規化済みスコープで前方一致する文書だけを対象にする。範囲外の値は `status: 失敗` で終了する。
- `docs-original/` を直接走査してはならない。

## 成果物

- `qa/{{key}}-original-docs-questionnaire.md` を新規作成（既存があれば work-artifacts-layout §4.1 で削除→新規作成）

## 並列実行ルール

- 他 D## の質問票には触らない。
- `docs/original-design-doc-ingest/` 配下および `docs-original/` 配下へ書き込まない。


## オーバーエンジニアリング禁止（共通ルール）

- **オーバーエンジニアリングは絶対に禁止**です。
- 指示・要件にない未来予測的な汎用化・抽象化・将来拡張点の先回り追加を行わないこと。
- YAGNI（必要になるまで実装しない原則）に違反する設計・記述を行わないこと。
- 未使用の設定オプション・フラグ・抽象レイヤー・予防的なエラーハンドリングを追加しないこと。
- 禁止事項の優先順位: 捏造禁止 > オーバーエンジニアリング禁止 > 最小差分原則。