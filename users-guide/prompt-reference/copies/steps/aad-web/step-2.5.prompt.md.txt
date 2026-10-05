{root_ref}

{app_arch_scope_section}
## 目的
AAD-Web 設計フェーズで、マイクロサービス定義書の「外部依存・統合」から追加で必要な Azure サービス（AI/認証/統合/運用等）を選定し、根拠（Microsoft Learn）付きで記録する（APP-ID 指定時はスコープ内のサービスのみ）。

## 補足: AI/LLM ・ 検索カテゴリの強制ルール
対象サービスの機能要件に `チャットボット` / `Prompt` / `AI Agent` / `RAG` 等が含まれる場合は、Prompt `Dev-Microservice-Azure-AddServiceDesign` の §3.1 強制ルールに従う（AI/LLM 第一候補 = Microsoft Foundry / 検索第一候補 = Azure AI Search）。Azure OpenAI Service の直接利用は禁止（Foundry resource 経由のモデル参照のみ許容）。

AI/LLM 該当時は、Foundry resource と **Foundry Project** を別リソースとして扱い、`Foundry Project名` / `Project location` / `Project作成方針` と、`モデル選択方式: model-router|fixed` を `docs/azure/azure-services-additional.md` に残す。本 Step は構成定義のみで Azure resource は作成しない。モデル指定がない一般用途は Model Router を先に評価し、不適合・利用不可時だけ live catalog の最新互換 fixed モデルを選ぶ。quota を取得できない場合は値を代用せず `TBD（Deploy時live確認必須: <理由>）` とする。

## 入力
- `docs/catalog/use-case-catalog.md`
- `docs/catalog/service-catalog.md`
- `docs/services/{serviceId}-{serviceNameSlug}-description.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- 既存採用済み（追加提案から除外、存在する場合のみ）:
  - `docs/azure/azure-services-compute.md`
  - `docs/azure/azure-services-data.md`

## 出力
- `docs/azure/azure-services-additional.md`

- Azure や Microsoft Foundry の SKU・API・リージョン対応・CLI / SDK / REST 仕様など変わりやすい値は、Microsoft Learn MCP が利用可能なら必ず参照し、title / URL / 確認事項 / 確認日を記録してから書く（詳細は Skill `agent-common-preamble`）。参照できない値は `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。

{existing_artifact_policy}

## Custom Agent
`Dev-Microservice-Azure-AddServiceDesign` を使用

## 依存
- Step.2.2（マイクロサービス定義書）が `aad-web:done` であること

## 完了条件
- `docs/azure/azure-services-additional.md` が作成されている
{completion_instruction}{app_id_section}{additional_section}
