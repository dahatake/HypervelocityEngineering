{root_ref}
## 目的
ドメイン分析の境界を根拠に、AI Agent が Tool として呼び出す候補となるサービス（API 提供単位）の一覧を抽出する。

## 入力
- `docs/catalog/use-case-catalog.md`（必須）
- `docs/catalog/domain-analytics.md`（必須）
- `docs/catalog/app-catalog.md`（必須）

## 出力
- `docs/catalog/service-catalog.md`

{existing_artifact_policy}

## Custom Agent
`Arch-Microservice-ServiceIdentify` を使用

## 依存
- Step.2（ドメイン分析）が `ada:done` であること

## 完了条件
- `docs/catalog/service-catalog.md` が作成されている
{completion_instruction}{additional_section}
