{root_ref}

{app_arch_scope_section}
## 目的
Azure Static Web Apps へのWebデプロイと、GitHub Actionsによる継続的デリバリー（CD）構築を実施する。

## 入力
- リソースグループ名: `{resource_group}`
- デプロイブランチ: `{branch}`（HVE Orchestrator が Step.4.3 用に作成・push する一時ブランチ）
- `app_location`: `src/app/`
- `api_location`: 空（API は Azure Static Web Apps Linked Backend で接続）
- 既存 workflow: `.github/workflows/azure-static-web-apps-app009.yml`（default branch に存在するリポジトリ管理 workflow。Step.4.3 では新規作成しない）
- リージョン優先: East Asia → Japan West → Southeast Asia
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

## 出力
- `src/infra/azure/create-azure-webui-resources-prep.sh`
- `src/infra/azure/create-azure-webui-resources.sh`
- `docs/catalog/service-catalog-matrix.md` 更新

SWA デプロイワークフローを新規作成しない。既存 `.github/workflows/azure-static-web-apps-app009.yml` を pre-flight で確認し、`gh workflow run ... --ref {branch}` に使用する。

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログ（work-status 系成果物）または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。必要に応じて `az ... -h` / パッケージマネージャ / 公式 CLI help を補助確認として使う。

{existing_artifact_policy}

## デプロイ TDD フロー（必須）
1. デプロイテスト仕様書の生成: `docs/test-specs/deploy-step3-swa-test-spec.md`
2. 検証スクリプトの生成: `src/infra/azure/verify-webui-resources.sh`（exit code: 0=全PASS, 非0=FAILあり）
3. 検証スクリプト実行 → 全 FAIL 確認（RED 状態）
4. 既存 SWA workflow が default branch で認識可能であることを確認（未認識なら deploy へ進まず blocked）
5. デプロイスクリプトの作成・実行
6. 検証スクリプト実行 → 全 PASS まで修正（最大 3 回反復。超過時は `asdw-web:blocked` + FAIL 項目一覧を報告）

## Custom Agent
`Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps` を使用

## 依存
- Step.4.2（UI 実装）が `asdw-web:done` であること
- Step.3.5（Deploy 後 再テスト）が `asdw-web:done` であること

## Branch / PR 境界
HVE GUI/CLI の ASDW-WEB Step 単位 CI/CD では、ブランチ作成・PR 作成・merge は Orchestrator の責務。Agent は提供された `{branch}` を `gh workflow run ... --ref {branch}` に使用し、新規 branch 作成や `gh pr create` は行わない。

## 完了条件
- デプロイスクリプトが作成され、既存 SWA workflow が default branch で認識可能であること
- 検証スクリプトで全項目 PASS であること
{completion_instruction}{app_id_section}{additional_section}
