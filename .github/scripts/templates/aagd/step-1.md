{root_ref}
## 目的
ユースケース記述を入力として、AI Agent のアプリケーション定義書を作成する（Step 1）。

## 入力
- ユースケースID: {usecase_id}
- ユースケース記述: {usecase_path}
- ガイドライン: `users-guide/08-ai-agent.md`（Step 1 セクション参照）
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- 参照（存在すれば）:
  - `docs/catalog/service-catalog-matrix.md`
  - `docs/catalog/service-catalog.md`
  - `docs/catalog/data-model.md`
  - `docs/catalog/domain-analytics.md`
  - `docs/catalog/use-case-catalog.md`
  - `docs/services/SVC-*.md`
  - `docs/azure/azure-services-data.md`
  - `docs/azure/azure-services-additional.md`

## 成果物
- `docs/agent/agent-application-definition.md`

{existing_artifact_policy}

## Custom Agent
`Arch-AIAgentDesign-Step1` を使用

## 依存
- asdw-web の Azure Compute Deploy 完了後に実行すること（Step.2.5 が `asdw-web:done` であること）

## 完了条件
- `docs/agent/agent-application-definition.md` が作成されている
{completion_instruction}{app_id_section}{additional_section}
