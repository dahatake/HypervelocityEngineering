{root_ref}
## 目的
ドメイン分析・データソース分析・バッチデータモデルを根拠に、バッチジョブ設計書（ジョブ一覧・依存DAG・スケジュール・リトライ戦略・冪等性保証）を作成する。

## 入力
- `docs/batch/batch-domain-analytics.md`
- `docs/batch/batch-data-source-analysis.md`
- `docs/batch/batch-data-model.md`

## 出力
- `docs/batch/batch-job-catalog.md`

## Custom Agent
`Arch-Batch-JobCatalog` を使用

## 依存
- Step.2（バッチデータモデル）が `abd:done` であること

## 完了条件
- `docs/batch/batch-job-catalog.md` が作成されている
- 完了時に自身に `abd:done` ラベルを付与すること{additional_section}