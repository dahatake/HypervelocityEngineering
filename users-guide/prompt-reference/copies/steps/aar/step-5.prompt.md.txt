{root_ref}

{app_arch_scope_section}
## 目的
Step.2 の設計書どおりに Knowledge Base / Knowledge Source を Azure CLI で作成し、Step.4 の RED テストを GREEN にする。

## 入力
- リソースグループ名: `{resource_group}`
- `docs/catalog/app-catalog.md`
- `docs/azure/agentic-retrieval/{serviceId}-design.md`（Step.2 出力）
- `src/test/integration/agentic-retrieval/`（Step.4 出力）

## 出力
- `src/infra/azure/create-azure-agentic-retrieval/prep.sh`
- `src/infra/azure/create-azure-agentic-retrieval/create.sh`
- `src/infra/azure/create-azure-agentic-retrieval/services/{serviceId}.sh`

## 実装の必須条件
- 設計書の AR-CAP-01（KB 名 / reasoning effort / outputMode）を**そのまま**反映する。値を勝手に変えない。
- AR-CAP-02 の Knowledge Source を過不足なく作成する。
- スクリプトは冪等（再実行しても壊れない）にする。
- 既存の API / データストアは**変更しない**。接続設定のみを追加する。

## AC 検証（必須）
- `AC4B-1`: 全リソースが `Succeeded`
- `AC4B-14`: 実 KB の reasoning effort が設計値と一致
- `AC4B-15`: 実 KB の Knowledge Source 集合が設計値と一致
- `AC4B-18`: 全 Knowledge Source を横断する smoke retrieve が成功

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログ（work-status 系成果物）または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。

{existing_artifact_policy}

## Custom Agent
`Dev-Microservice-Azure-AgenticRetrievalDeploy` を使用

## 依存
- Step.4（Agentic Retrieval テストコード）が `aar:done` であること

## 完了条件
- 出力スクリプトが作成され、実行が成功している
- Step.4 のテストが全件 PASS になっている
- AC4B-1 / AC4B-14 / AC4B-15 / AC4B-18 の検証証跡が記録されている
{completion_instruction}{app_id_section}{additional_section}
