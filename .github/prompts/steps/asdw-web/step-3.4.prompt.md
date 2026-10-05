{root_ref}

{app_arch_scope_section}
## 目的
サービスリストの対象サービスを、Azure Functions用に作成/更新→デプロイ、GitHub Actions で CI/CD 構築、API スモークテスト（+手動UI）追加まで行う（APP-ID 指定時はスコープ内のサービスのみ）。

## 入力
- リソースグループ名: `{resource_group}`
- `docs/catalog/service-catalog.md`
- `docs/catalog/service-catalog-matrix.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- `src/api/{サービスID}-{サービス名}/`
- デプロイブランチ: `{branch}`（HVE Orchestrator が Step.3.4 用に作成・push する一時ブランチ）
- リージョン: `Japan East`（優先。利用不可なら `Japan West`、それも不可なら `Southeast Asia`）

## 出力
- `src/infra/azure/create-azure-api-resources-prep.sh`
- `.github/workflows/` にCI/CD（OIDC + azure/login 優先）
- `docs/catalog/service-catalog-matrix.md` 更新
- `src/test/{サービスID}-{サービス名}/` にスモークテスト + 手動UI

- Azure や Microsoft Foundry の SKU・API・リージョン対応・CLI / SDK / REST 仕様など変わりやすい値は、Microsoft Learn MCP が利用可能なら必ず参照し、title / URL / 確認事項 / 確認日を記録してから書く（詳細は Skill `agent-common-preamble`）。参照できない値は `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。

{existing_artifact_policy}

## デプロイ TDD フロー
1. デプロイテスト仕様書の生成: `docs/test-specs/deploy-step2-compute-test-spec.md`
2. 検証スクリプトの生成: `src/infra/azure/verify-api-resources.sh`（exit code: 0=全PASS, 非0=FAILあり）
3. 検証スクリプト実行 → 全 FAIL 確認（RED 状態）
4. デプロイスクリプトの作成・実行
5. 検証スクリプト実行 → 全 PASS まで修正（最大 3 回反復。超過時は `asdw-web:blocked` + FAIL 項目一覧を報告）

## 注意
Copilot が push しても workflow は自動実行されないことがある。PR 側でユーザーが実行承認できるよう説明を残す。
HVE GUI/CLI の ASDW-WEB Step 単位 CI/CD では、ブランチ作成・PR 作成・merge は Orchestrator の責務。Agent は提供された `{branch}` を `gh workflow run ... --ref {branch}` に使用し、新規 branch 作成や `gh pr create` は行わない。

## Custom Agent
`Dev-Microservice-Azure-ComputeDeploy-AzureFunctions` を使用

## 依存
- Step.3.3（サービスコード実装）が `asdw-web:done` であること
- Step.2.4（追加サービスのテスト実施）が `asdw-web:done` であること

{remote_mcp_server_section}

## 完了条件
- デプロイスクリプトと CI/CD ワークフローが作成されている
- 検証スクリプトで全項目 PASS であること
{completion_instruction}{app_id_section}{additional_section}
