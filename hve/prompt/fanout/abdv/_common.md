# ABDV Fan-out per-job 追加指示

このサブタスクは ABDV Step 2.1 / 2.2 の fan-out 子であり、バッチジョブ `{{key}}` のみ を対象とする。

## 対象
- `test/batch/{{key}}.Tests/`（Step 2.1）
- `src/batch/{{key}}/`（Step 2.2）

## 必須参照
- `docs/batch/jobs/{{key}}-spec.md`
- `docs/test-specs/{{key}}-test-spec.md`

## 並列実行ルール
- 他ジョブのテスト/コードに書き込まない。
