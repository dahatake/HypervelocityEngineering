{root_ref}
## 目的
Step.1 のアプリケーション定義を入力として、AI Agent の粒度設計（Single/Multi 判断）とアーキテクチャ骨格を設計する。

## 入力
- `docs/agent/agent-application-definition.md`（Step.1 の成果物）
- `docs/catalog/service-catalog-matrix.md`
- `docs/catalog/domain-analytics.md`
- `docs/catalog/data-model.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧）
- `users-guide/08-ai-agent.md`（設計ガイドライン Step 2）

## 出力
- `docs/agent/agent-architecture.md`

## Custom Agent
`Arch-AIAgentDesign-Step2` を使用

## 依存
- Step.1（AI Agent アプリケーション定義）が `aag:done` であること

## 完了条件
- `docs/agent/agent-architecture.md` が作成されている
{completion_instruction}{app_id_section}{additional_section}
