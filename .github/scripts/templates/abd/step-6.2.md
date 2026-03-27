{root_ref}
## 目的
サービスカタログとジョブ設計に基づき、監視・運用設計書を作成する。

## 入力
- `docs/batch/batch-service-catalog.md`
- `docs/batch/batch-job-catalog.md`

## 出力
- `docs/batch/batch-monitoring-design.md`

## Custom Agent
`Arch-Batch-MonitoringDesign` を使用

## 依存
- {dep}

## 完了条件
- `docs/batch/batch-monitoring-design.md` が作成されている
- 完了時に自身に `abd:done` ラベルを付与すること{additional_section}