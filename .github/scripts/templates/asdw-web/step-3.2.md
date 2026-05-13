{root_ref}

{app_arch_scope_section}
## 目的
Azure Static Web Apps へのWebデプロイと、GitHub Actionsによる継続的デリバリー（CD）構築を実施する。

## 入力
- リソースグループ名: `{resource_group}`
- デプロイブランチ: `main`
- `app_location`: `src/app/`
- `api_location`: `src/app/lib/api/`
- リージョン優先: East Asia → Japan West → Southeast Asia
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

## 出力
- `infra/azure/create-azure-webui-resources-prep.sh`
- `infra/azure/create-azure-webui-resources.sh`
- `.github/workflows/` に SWA デプロイワークフロー（Secret `AZURE_STATIC_WEB_APPS_API_TOKEN` 参照）
- `docs/catalog/service-catalog-matrix.md` 更新

{existing_artifact_policy}

## デプロイ TDD フロー（必須）
1. デプロイテスト仕様書の生成: `docs/test-specs/deploy-step3-swa-test-spec.md`
2. 検証スクリプトの生成: `infra/azure/verify-webui-resources.sh`（exit code: 0=全PASS, 非0=FAILあり）
3. 検証スクリプト実行 → 全 FAIL 確認（RED 状態）
4. デプロイスクリプトの作成・実行
5. 検証スクリプト実行 → 全 PASS まで修正（最大 3 回反復。超過時は `asdw-web:blocked` + FAIL 項目一覧を報告）

## Custom Agent
`Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps` を使用

## 依存
- Step.3.1（UI 実装）が `asdw-web:done` であること

## 完了条件
- デプロイスクリプトと SWA ワークフローが作成されている
- 検証スクリプトで全項目 PASS であること
{completion_instruction}{app_id_section}{additional_section}
