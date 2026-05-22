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
