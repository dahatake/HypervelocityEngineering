{root_ref}
## 目的
サービス一覧、データモデル、画面一覧、ドメイン分析を統合してサービスカタログを作成する。

## 入力
- `docs/service-list.md`
- `docs/data-model.md`
- `docs/screen-list.md`
- `docs/domain-analytics.md`
- `docs/app-list.md`（アプリケーション一覧）

## 出力
- `docs/service-catalog.md`

## Custom Agent
`Arch-Microservice-ServiceCatalog` を使用

## 依存
- Step.4（画面一覧と遷移図）が `aad:done` であること

## アプリケーション粒度
📋 `docs/app-list.md` のアプリケーション一覧（APP-ID）を参照し、Table A（画面→API）に「所属APP」（1:1）、Table C（サービス責務）に「利用APP」（N:N）を記載すること。

## 完了条件
- `docs/service-catalog.md` が作成されている
- 完了時に自身に `aad:done` ラベルを付与すること{additional_section}
