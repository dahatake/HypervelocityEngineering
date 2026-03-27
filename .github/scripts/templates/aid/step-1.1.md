{root_ref}
## 目的
ユースケース文書を根拠に、DDD観点＋IoT 3層境界（Device/Edge/Cloud）でドメイン分析を行い、docs/domain-analytics.md を作成する。

## 入力
- `docs/usecase-list.md`

## 出力
- `docs/domain-analytics.md`

## Custom Agent
`Arch-IoT-DomainAnalytics` を使用

## 依存
- なし（ルートノード）

## 完了条件
- `docs/domain-analytics.md` が作成されている
- 完了時に自身に `aid:done` ラベルを付与すること{additional_section}
