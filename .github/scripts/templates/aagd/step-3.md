{root_ref}
## 目的
AI Agent を Azure AI Foundry Agent Service へデプロイし、GitHub Actions で CI/CD を構築する（APP-ID 指定時はスコープ内の Agent のみ）。

## 入力
- リソースグループ名: `{resource_group}`
- `src/agent/{agentId}-{agentName}/`
- `docs/ai-agent-catalog.md`
- `docs/azure/azure-services-additional.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

## 出力
- `infra/azure/create-azure-agent-resources-prep.sh`
- `infra/azure/create-azure-agent-resources.sh`
- `infra/azure/verify-agent-resources.sh`
- `.github/workflows/deploy-agent-{agentId}-{agentName}.yml`
- `docs/test-specs/deploy-step2-agent-test-spec.md`
- `docs/azure/service-catalog.md`（Agent エンドポイント追記）

## デプロイ TDD フロー（必須）
1. デプロイテスト仕様書の生成: `docs/test-specs/deploy-step2-agent-test-spec.md`
2. 検証スクリプトの生成: `infra/azure/verify-agent-resources.sh`（exit code: 0=全PASS, 非0=FAILあり）
3. 検証スクリプト実行 → 全 FAIL 確認（RED 状態）
4. デプロイスクリプトの作成・実行
5. 検証スクリプト実行 → 全 PASS まで修正（最大 3 回反復。超過時は `aagd:blocked` + FAIL 項目一覧を報告）

## Custom Agent
`Dev-Microservice-Azure-AgentDeploy` を使用

## 依存
- Step.2.3（AI Agent 実装）が `aagd:done` であること

## 完了条件
- デプロイスクリプトと CI/CD ワークフローが作成されている
- 検証スクリプトで全項目 PASS であること
{completion_instruction}{app_id_section}{additional_section}
