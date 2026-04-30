<!-- DEPRECATED: このテンプレートは templates/aag/step-3.md に移動しました。 -->
{root_ref}
## 目的
Step.8.2 の Agent Catalog の各 Agent について詳細設計書を作成し、Agent 一覧を更新する。

## 入力
- `docs/agent/agent-architecture.md`（Step.8.2 の成果物）
- `docs/agent/agent-application-definition.md`（Step.8.1 の成果物）
- `docs/catalog/service-catalog-matrix.md`
- `docs/services/SVC-*.md`（関連サービスのみ）
- `docs/catalog/app-catalog.md`（アプリケーション一覧）
- `users-guide/08-ai-agent.md`（設計ガイドライン Step 3）

## 出力
- `docs/agent/agent-detail-<Agent-ID>-<Agent名>.md`（Agent ごとに1ファイル）
- `docs/ai-agent-catalog.md`（Agent 一覧）

## Custom Agent
`Arch-AIAgentDesign-Step3` を使用

## 依存
- Step.8.2（AI Agent 粒度設計）が `aad:done` であること

## 完了条件
- `docs/agent/` 配下に Agent ごとの詳細設計書が作成されている
- `docs/ai-agent-catalog.md` が作成/更新されている
{completion_instruction}{app_id_section}{additional_section}
