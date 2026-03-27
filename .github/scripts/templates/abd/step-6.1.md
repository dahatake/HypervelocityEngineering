{root_ref}
## 目的
サービスカタログとジョブ設計に基づき、ジョブ毎の詳細仕様書を作成する。

## 入力
- `docs/batch/batch-service-catalog.md`
- `docs/batch/batch-job-catalog.md`
- `docs/batch/batch-data-model.md`

## 出力
- `docs/batch/jobs/{jobId}-{jobNameSlug}-spec.md`（ジョブごとに1ファイル）

## Custom Agent
`Arch-Batch-JobSpec` を使用

## 依存
- {dep}

## 完了条件
- 各ジョブの詳細仕様書が全て作成されている
- 完了時に自身に `abd:done` ラベルを付与すること{additional_section}