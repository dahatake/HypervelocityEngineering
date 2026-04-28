{root_ref}
## 目的
ユースケース記述を入力として、AI Agent のアプリケーション定義書を作成する。

## 入力
- `docs/catalog/use-case-catalog.md`（ユースケース記述）
- `docs/catalog/service-catalog-matrix.md`
- `docs/catalog/domain-analytics.md`
- `docs/catalog/data-model.md`
- `docs/catalog/service-catalog.md`
- `docs/services/SVC-*.md`（関連サービスのみ）
- `docs/catalog/app-catalog.md`（アプリケーション一覧）
- `users-guide/08-ai-agent.md`（設計ガイドライン Step 1）

## 出力
- `docs/agent/agent-application-definition.md`

## Custom Agent
`Arch-AIAgentDesign` を使用

## 依存
- aad-web 完了後に実行すること（Step.2.3 が `aad-web:done` であること）

## アプリケーション粒度
📋 `docs/catalog/app-catalog.md` のアプリケーション一覧（APP-ID）を参照し、Agent の対象 APP-ID を明記すること。

## 完了条件
- `docs/agent/agent-application-definition.md` が作成されている
{completion_instruction}{app_id_section}{additional_section}
