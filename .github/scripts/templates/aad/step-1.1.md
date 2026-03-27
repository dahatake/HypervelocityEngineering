{root_ref}
## 目的
ユースケース文書を根拠に、DDD観点でドメイン分析を行い、docs/domain-analytics.md を作成する。

## 前提条件
- `docs/app-list.md` が存在すること（Auto App Selection Workflow の成果物）

## 入力
- `docs/usecase-list.md`
- `docs/app-list.md`（アプリケーション一覧）

## 出力
- `docs/domain-analytics.md`

## Custom Agent
`Arch-Microservice-DomainAnalytics` を使用

## 依存
- フェーズ2の最初のStepとして実行（前段の依存はフェーズ1の成果物のみ）

## 完了条件
- `docs/domain-analytics.md` が作成されている
- 完了時に自身に `aad:done` ラベルを付与すること{additional_section}
