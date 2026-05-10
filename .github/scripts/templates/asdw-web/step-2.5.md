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
- リージョン: `Japan East`（優先。利用不可なら `Japan West`、それも不可なら `Southeast Asia`）

## 出力
- `infra/azure/create-azure-api-resources-prep.sh`
- `.github/workflows/` にCI/CD（OIDC + azure/login 優先）
- `docs/catalog/service-catalog-matrix.md` 更新
- `test/{サービスID}-{サービス名}/` にスモークテスト + 手動UI

## デプロイ TDD フロー（必須）
1. デプロイテスト仕様書の生成: `docs/test-specs/deploy-step2-compute-test-spec.md`
2. 検証スクリプトの生成: `infra/azure/verify-api-resources.sh`（exit code: 0=全PASS, 非0=FAILあり）
3. 検証スクリプト実行 → 全 FAIL 確認（RED 状態）
4. デプロイスクリプトの作成・実行
5. 検証スクリプト実行 → 全 PASS まで修正（最大 3 回反復。超過時は `asdw-web:blocked` + FAIL 項目一覧を報告）

## 注意
Copilot が push しても workflow は自動実行されないことがある。PR 側でユーザーが実行承認できるよう説明を残す。

## Custom Agent
`Dev-Microservice-Azure-ComputeDeploy-AzureFunctions` を使用

## 依存
- Step.2.4（サービスコード実装）が `asdw-web:done` であること

{remote_mcp_server_section}

## 完了条件
- デプロイスクリプトと CI/CD ワークフローが作成されている
- 検証スクリプトで全項目 PASS であること
{completion_instruction}{app_id_section}{additional_section}
