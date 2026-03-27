{root_ref}
## 目的
ジョブ設計書・データモデル・ドメイン分析を統合してバッチジョブ版サービスカタログを作成する。

## 入力
- `docs/batch/batch-job-catalog.md`
- `docs/batch/batch-data-model.md`
- `docs/batch/batch-domain-analytics.md`

## 出力
- `docs/batch/batch-service-catalog.md`

## Custom Agent
`Arch-Batch-ServiceCatalog` を使用

## 依存
- Step.3（ジョブ設計書）が `abd:done` であること

## 完了条件
- `docs/batch/batch-service-catalog.md` が作成されている
- 完了時に自身に `abd:done` ラベルを付与すること{additional_section}