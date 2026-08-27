{root_ref}
## 目的
ユースケースとアプリケーション一覧から、境界づけられたコンテキストとユビキタス言語を整理する。

## 入力
- `docs/catalog/use-case-catalog.md`（必須）
- `docs/catalog/app-catalog.md`（必須）

## 出力
- `docs/catalog/domain-analytics.md`

{existing_artifact_policy}

## Custom Agent
`Arch-Microservice-DomainAnalytics` を使用

## 依存
- Step.1（アプリケーションリストの作成）が `ada:done` であること

## 完了条件
- `docs/catalog/domain-analytics.md` が作成されている
{completion_instruction}{additional_section}
