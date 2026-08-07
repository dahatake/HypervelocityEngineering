{root_ref}
## 目的
AI Agent を Azure AI Foundry Agent Service へデプロイし、GitHub Actions で CI/CD を構築する（APP-ID 指定時はスコープ内の Agent のみ）。

## 入力
- リソースグループ名: `{resource_group}`
- `src/agent/{key}/`
- `docs/ai-agent-catalog.md`
- `docs/agent/agent-detail-{key}.md`
- `docs/azure/azure-services-additional.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

## 出力
- `src/infra/azure/create-azure-agent-resources-prep.sh`
- `src/infra/azure/create-azure-agent-resources.sh`
- `src/infra/azure/verify-agent-resources.sh`
- `.github/workflows/deploy-agent-{key}.yml`
- `docs/test-specs/deploy-step2-agent-test-spec.md`
- `docs/azure/azure-service-catalog.md`（Agent エンドポイント追記）

## 入出力契約

- `.github/io-contracts/Dev-Microservice-Azure-AgentDeploy--aagd--3.yaml`

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードに加え、Section 7.0 / 7.3のsearch / MCP providerの接続・認証・権限・availabilityを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項 / 確認日** を `{WORK}` の作業ログ（work-status 系成果物）または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。必要に応じて `az ... -h` / パッケージマネージャ / 公式 CLI help を補助確認として使う。

{existing_artifact_policy}

## Foundry Project 責務境界

- Foundry Project は ASDW-WEB Step.2.2 が作成する。本 Step は **Foundry Project を作成しない**。
- Azure AI Search の Knowledge Base / Knowledge Source は ASDW-WEB Step.2.6（`Dev-Microservice-Azure-AgenticRetrievalDeploy`）が作成する。本 Step は **Knowledge Base / Knowledge Source を作成せず**、設計で選択された場合に存在と接続を確認するのみとする。未作成の場合は自己対応せず blocked として Step.2.6 へフィードバックする。
- Agent 登録前に `az cognitiveservices account project show --name <account> --resource-group <rg> --project-name <project>` で Project 子リソースと `Succeeded` を確認する。
- Project が無い場合は、account / Project 名を示して ASDW-WEB Step.2.2 (AddServiceDeploy) の先行実行を案内し、`aagd:blocked` で停止する。
- Project endpoint を取得できない場合、**親 account endpoint を Project endpoint の代用にしない**。値を推測・合成せず停止する。

## デプロイ TDD フロー（必須）
1. デプロイテスト仕様書の生成: `docs/test-specs/deploy-step2-agent-test-spec.md`
2. 検証スクリプトの生成: `src/infra/azure/verify-agent-resources.sh`（exit code: 0=全PASS, 非0=FAILあり）
3. Agent詳細設計Section 7.0 / 7.3から選択providerを確定し、Custom Agent Promptの`A-cap-plan`でavailability、permission、data boundary、fallbackとdeploy前inventoryを審査する
4. 初回deploy時だけ検証スクリプト実行 → リソース未作成によるFAIL確認（RED状態）。冪等redeploy時は既存GREENをbaselineとしてREDをスキップし、理由を`ac-verification.md`へ記録する
5. デプロイスクリプトの作成・実行（選択providerだけを接続し、N/A providerを作成しない）
6. 検証スクリプト実行 → 全 PASS まで修正（最大 3 回反復。超過時は `aagd:blocked` + FAIL 項目一覧を報告）
7. Custom Agent Promptの`A-cap-verify`を実行し、選択providerの接続/smoke、N/A providerのinventory差分ゼロ、証跡redactionを固定`Provider Pre-flight`表へ記録する

## Custom Agent
`Dev-Microservice-Azure-AgentDeploy` を使用

## 依存
- Step.2.3（AI Agent 実装）が `aagd:done` であること

## 完了条件
- デプロイスクリプトと CI/CD ワークフローが作成されている
- 検証スクリプトで全項目 PASS であること
- `ac-verification.md`の`Provider Pre-flight`固定表がHVE Deploy gateをPASSすること
{completion_instruction}{app_id_section}{additional_section}
