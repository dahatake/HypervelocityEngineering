# ABD Fan-out per-job 追加指示

このサブタスクは ABD Step 6.1 / 6.3 の fan-out 子であり、バッチジョブ `{{key}}` のみ を対象とする。

## 対象
- `docs/batch/jobs/{{key}}-spec.md`
- `docs/test-specs/{{key}}-test-spec.md`（Step 6.3 のみ）

## 必須参照
- `docs/batch/batch-job-catalog.md` の `{{key}}` 該当行
- `docs/batch/batch-service-catalog.md`
- `docs/batch/batch-data-model.md`

## 並列実行ルール
- 他ジョブのファイルに書き込まない。
