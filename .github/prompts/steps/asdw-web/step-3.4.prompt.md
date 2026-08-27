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

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログ（work-status 系成果物）または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。必要に応じて `az ... -h` / パッケージマネージャ / 公式 CLI help を補助確認として使う。

{existing_artifact_policy}

## デプロイ TDD フロー（必須）
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
