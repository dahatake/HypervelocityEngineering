# ADFD Fan-out per-job 追加指示

このサブタスクは ADFD Step 6.1 / 6.3 の fan-out 子であり、データフローアプリ `{{key}}` のみ を対象とする。

## 対象
- `docs/dataflow/apps/{{key}}-spec.md`
- `docs/test-specs/{{key}}-test-spec.md`（Step 6.3 のみ）

## 必須参照
- `docs/dataflow/dataflow-app-catalog.md` の `{{key}}` 該当行
- `docs/dataflow/dataflow-service-catalog.md`
- `docs/dataflow/dataflow-data-model.md`

## 並列実行ルール
- 他ジョブのファイルに書き込まない。


## オーバーエンジニアリング禁止（共通ルール）

- **オーバーエンジニアリングは絶対に禁止**です。
- 指示・要件にない未来予測的な汎用化・抽象化・将来拡張点の先回り追加を行わないこと。
- YAGNI（必要になるまで実装しない原則）に違反する設計・記述を行わないこと。
- 未使用の設定オプション・フラグ・抽象レイヤー・予防的なエラーハンドリングを追加しないこと。
- 禁止事項の優先順位: 捏造禁止 > オーバーエンジニアリング禁止 > 最小差分原則。
