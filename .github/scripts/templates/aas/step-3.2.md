{root_ref}
## 目的
ユースケース文書とドメイン分析結果を根拠に、サービス一覧を抽出し、docs/catalog/service-catalog.md を作成する。

## 入力
- `docs/catalog/use-case-catalog.md`
- `docs/catalog/domain-analytics.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧）

## 出力
- `docs/catalog/service-catalog.md`

## Custom Agent
`Arch-Microservice-ServiceIdentify` を使用

## 依存
- Step.3.1（ドメイン分析）が `aas:done` であること

## アプリケーション粒度
📋 `docs/catalog/app-catalog.md` のアプリケーション一覧（APP-ID）を参照し、各サービス候補に APP-ID との紐付け（N:N）を行うこと。

## 完了条件
- `docs/catalog/service-catalog.md` が作成されている
{completion_instruction}{additional_section}
