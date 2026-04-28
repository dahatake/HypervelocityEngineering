<!-- DEPRECATED: このテンプレートは templates/aagd/step-1.md に移動しました。 -->
{root_ref}
## 目的
ユースケース記述を入力として、AI Agent のアプリケーション定義・粒度設計・詳細設計を実施し、Agent 一覧を出力する（APP-ID 指定時はスコープ内のサービス/画面のみ）。

## 入力
- ユースケースID: {usecase_id}
- ユースケース記述: {usecase_path}
- ガイドライン: `users-guide/08-ai-agent.md`
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
- `docs/agent/agent-architecture.md`
- `docs/agent/agent-detail-<Agent-ID>-<Agent名>.md`（Agent ごと）
- `docs/ai-agent-catalog.md`

## Custom Agent
`Arch-AIAgentDesign` を使用

## 依存
- Step.2.5（Azure Compute Deploy）が `asdw:done` であること

## 完了条件
- `docs/ai-agent-catalog.md` が作成されている
{completion_instruction}{app_id_section}{additional_section}