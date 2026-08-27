{root_ref}

{app_arch_scope_section}
## 目的
Step.2.5 の Azure 実装設計を入力に、Azure AI Search の Index / Knowledge Source / Knowledge Base を **冪等にデプロイ**し、設計値と実リソース設定の一致を実在で検証する（APP-ID 指定時はスコープ内のサービスのみ）。

## 責務境界
- Foundry resource / Foundry Project / モデル deployment は **Step.2.2 が作成する**。本 Step では作成しない。
- 本 Step は Knowledge Source と Knowledge Base、および必要な接続・RBAC 割当を担当する。

## 入力
- リソースグループ名: `{resource_group}`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- `docs/azure/agentic-retrieval/{serviceId}-design.md`（Step.2.5 出力）

## 出力
- `src/infra/azure/create-azure-agentic-retrieval/prep.sh`
- `src/infra/azure/create-azure-agentic-retrieval/create.sh`
- `src/infra/azure/create-azure-agentic-retrieval/services/{serviceId}.sh`

## 実在検証（reality gate）
以下は `ac-verification.md` で `✅` のみ許容する。`❌` / `⏳` のまま完了した場合は Step を fail に降格させる。

| AC | 内容 |
| --- | --- |
| AC4B-1 | 作成すべき全リソースが存在し `provisioningState: Succeeded` |
| AC4B-14 | Knowledge Base の `retrievalReasoningEffort` が AR-CAP-01 の設計値と一致 |
| AC4B-15 | Knowledge Source の件数・名前・`alwaysQuery` が AR-CAP-02 の行と一致 |
| AC4B-18 | 非破壊 smoke retrieve で AR-CAP-02 の全 Knowledge Source が検索対象になったことを確認 |

`ac-verification.md` は 1 行 1 AC のテーブル行で記録する。応答本文・raw URL・query 本文は証跡へ保存せず、provider / 件数 / status / 取得日時だけを残す。

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログ（work-status 系成果物）または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。

{existing_artifact_policy}

## Custom Agent
`Dev-Microservice-Azure-AgenticRetrievalDeploy` を使用

## 依存
- Step.2.2（追加 Azure サービス Deploy）が `asdw-web:done` であること
- Step.2.5（Agentic Retrieval Azure 実装設計）が `asdw-web:done` であること

## 完了条件
- 実在系 AC（AC4B-1 / AC4B-14 / AC4B-15 / AC4B-18）がすべて `✅`
- `docs/azure/agentic-retrieval/{serviceId}-design.md` が 1 件も存在しない場合は、その事実を作業ログへ記録して成果物なしで完了する
{completion_instruction}{app_id_section}{additional_section}
