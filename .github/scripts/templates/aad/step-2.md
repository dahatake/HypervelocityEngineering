{root_ref}
## 目的
ドメイン分析結果とサービス一覧を根拠に、データモデルを設計する。

## 入力
- `docs/domain-analytics.md`
- `docs/service-list.md`
- `docs/app-list.md`（アプリケーション一覧）

## 出力
- `docs/data-model.md`
- `src/data/sample-data.json`

## Custom Agent
`Arch-DataModeling` を使用

## 依存
- Step.1.2（サービス一覧抽出）が `aad:done` であること

## アプリケーション粒度
📋 `docs/app-list.md` のアプリケーション一覧（APP-ID）を参照し、Entity Catalog の各エンティティに「利用APP」（N:N）を記載すること。

## 完了条件
- `docs/data-model.md` と `src/data/sample-data.json` が作成されている
- 完了時に自身に `aad:done` ラベルを付与すること{additional_section}
