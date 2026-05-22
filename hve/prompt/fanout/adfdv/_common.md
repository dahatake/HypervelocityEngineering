# ADFDV Fan-out per-job 追加指示

このサブタスクは ADFDV Step 2.1 / 2.2 の fan-out 子であり、データフローアプリ `{{key}}` のみ を対象とする。

## 対象
- `test/dataflow/{{key}}.Tests/`（Step 2.1）
- `src/dataflow/{{key}}/`（Step 2.2）

## 必須参照
- `docs/dataflow/apps/{{key}}-spec.md`
- `docs/test-specs/{{key}}-test-spec.md`

## 並列実行ルール
- 他ジョブのテスト/コードに書き込まない。
