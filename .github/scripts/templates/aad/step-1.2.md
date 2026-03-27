{root_ref}
## 目的
ユースケース文書とドメイン分析結果を根拠に、サービス一覧を抽出し、docs/service-list.md を作成する。

## 入力
- `docs/usecase-list.md`
- `docs/domain-analytics.md`
- `docs/app-list.md`（アプリケーション一覧）

## 出力
- `docs/service-list.md`

## Custom Agent
`Arch-Microservice-ServiceIdentify` を使用

## 依存
- Step.1.1（ドメイン分析）が `aad:done` であること

## アプリケーション粒度
📋 `docs/app-list.md` のアプリケーション一覧（APP-ID）を参照し、各サービス候補に APP-ID との紐付け（N:N）を行うこと。

## 完了条件
- `docs/service-list.md` が作成されている
- 完了時に自身に `aad:done` ラベルを付与すること{additional_section}
