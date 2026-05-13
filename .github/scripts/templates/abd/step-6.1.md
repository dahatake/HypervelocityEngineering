{root_ref}

{app_arch_scope_section}
## 目的
サービスカタログとジョブ設計に基づき、ジョブ毎の詳細仕様書を作成する。

## 入力
- `docs/batch/batch-service-catalog.md`
- `docs/batch/batch-job-catalog.md`
- `docs/batch/batch-data-model.md`

## 出力
- `docs/batch/jobs/{jobId}-{jobNameSlug}-spec.md`（ジョブごとに1ファイル）

{existing_artifact_policy}

## Custom Agent
`Arch-Batch-JobSpec` を使用

## 依存
- {dep}

## 完了条件
- 各ジョブの詳細仕様書が全て作成されている
{completion_instruction}{additional_section}