{root_ref}

{app_arch_scope_section}
## 目的
サービス定義書の「外部依存・統合」から、追加で必要な Azure サービス（AI/認証/統合/運用等）を選定し、根拠（Microsoft Learn）付きで記録する（APP-ID 指定時はスコープ内のサービスのみ）。

既存の `docs/azure/azure-services-additional.md` がある場合は読み、本 Workflow で確定した Azure のデータ層・コンピュート（`docs/azure/azure-services-compute.md` / `docs/azure/azure-services-data.md`）を反映して変わる点の差分だけを追記する。既存の記述を削除・再生成しない。AAD-WEB Step.2.5 が同じ Agent で同じ成果物を作っており、選定をやり直すと同じ内容を 2 回書くことになるためである。既存の成果物が無い場合は新規に作成する。

## 補足: AI/LLM ・ 検索カテゴリの強制ルール
対象サービスの機能要件に `チャットボット` / `Prompt` / `AI Agent` / `RAG` 等が含まれる場合は、Prompt `Dev-Microservice-Azure-AddServiceDesign` の§3.1 強制ルールに従う（AI/LLM 第一候補 = Microsoft Foundry / 検索第一候補 = Azure AI Search）。

AI/LLM 該当時は、Foundry resource と **Foundry Project** を別リソースとして扱い、`Foundry Project名` / `Project location` / `Project作成方針` と、`モデル選択方式: model-router|fixed` を `docs/azure/azure-services-additional.md` に残す。本 Step は構成定義のみで Azure resource は作成しない。モデル指定がない一般用途は Model Router を先に評価し、不適合・利用不可時だけ live catalog の最新互換 fixed モデルを選ぶ。quota を取得できない場合は値を代用せず `TBD（Deploy時live確認必須: <理由>）` とする。

## 入力
- リソースグループ名: `{resource_group}`
- `docs/catalog/use-case-catalog.md`
- `docs/catalog/service-catalog.md`
- `docs/services/{サービスID}-{サービス名}-description.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- 既存採用済み（追加提案から除外）:
  - `docs/azure/azure-services-compute.md`
  - `docs/azure/azure-services-data.md`

## 出力
- `docs/azure/azure-services-additional.md`

- Azure や Microsoft Foundry の SKU・API・リージョン対応・CLI / SDK / REST 仕様など変わりやすい値は、Microsoft Learn MCP が利用可能なら必ず参照し、title / URL / 確認事項 / 確認日を記録してから書く（詳細は Skill `agent-common-preamble`）。参照できない値は `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。

{existing_artifact_policy}

## Custom Agent
`Dev-Microservice-Azure-AddServiceDesign` を使用

## 依存
- Step.1.1（Azure データストア選定）が `asdw-web:done` であること

## 完了条件
- `docs/azure/azure-services-additional.md` が作成されている
{completion_instruction}{app_id_section}{additional_section}
