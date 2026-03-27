{root_ref}
## 目的
ユースケース文書を根拠に、DDD観点でバッチドメイン分析（冪等性・トランザクション境界・最終的一貫性・チェックポイント/リスタート等）を行い、docs/batch/batch-domain-analytics.md を作成する。

## 入力
- `docs/usecase-list.md`

## 出力
- `docs/batch/batch-domain-analytics.md`

## Custom Agent
`Arch-Batch-DomainAnalytics` を使用

## 完了条件
- `docs/batch/batch-domain-analytics.md` が作成されている
- 完了時に自身に `abd:done` ラベルを付与すること{additional_section}