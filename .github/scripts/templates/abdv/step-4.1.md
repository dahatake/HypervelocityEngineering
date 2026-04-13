{root_ref}
## 目的
デプロイ済みの Azure リソース構成を Azure Well-Architected Framework（WAF）5本柱で評価する。

## 入力
- デプロイ済みの Azure リソース（Azure Portal / CLI で確認）
- `docs/azure/azure-services-data.md`
- `docs/batch/batch-service-catalog.md`
- `docs/batch/batch-monitoring-design.md`（監視設計書: WAF「運用の優秀性」柱の根拠）
- `docs/azure/azure-services-compute.md`（存在する場合のみ参照）

## 出力
- WAF レビューレポート（`docs/azure/waf-review.md`）

## Custom Agent
`QA-AzureArchitectureReview` を使用

## 依存
- {dep}

## 完了条件
- `docs/azure/waf-review.md` が作成されている
- 完了時に自身に `abdv:done` ラベルを付与すること{rg_section}{job_section}{additional_section}