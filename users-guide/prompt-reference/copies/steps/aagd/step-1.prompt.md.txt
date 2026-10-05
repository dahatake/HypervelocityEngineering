{root_ref}
## 目的
ユースケース記述を入力として、AI Agent のアプリケーション定義書を作成する（Step 1）。

既存の `docs/agent/agent-application-definition.md` がある場合は読み、Azure の設計（`docs/azure/azure-services-data.md` / `docs/azure/azure-services-additional.md`）と対象ユースケースを反映して変わる点の差分だけを追記する。既存の記述を削除・再生成しない。AAG Step.1 が同じ Agent で同じ成果物を作っており、定義をやり直すと同じ内容を 2 回書くことになるためである。既存の成果物が無い場合は新規に作成する。

## 入力
- ユースケースID: {usecase_id}
- ユースケース記述: {usecase_path}
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
