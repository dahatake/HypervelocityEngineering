{root_ref}

{app_arch_scope_section}
## 目的
`docs/azure/azure-services-additional.md` を根拠に、追加Azureサービスを Azure CLI で冪等に作成する（APP-ID 指定時はスコープ内のサービスのみ）。

## 入力
- リソースグループ名: `{resource_group}`
- `docs/azure/azure-services-additional.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- （任意）subscription / tenant / 優先リージョン / 命名規則

## 出力
- `infra/azure/create-azure-additional-resources-prep.sh`
- `infra/azure/create-azure-additional-resources/create.sh`
- （複数サービスの場合）`infra/azure/create-azure-additional-resources/services/<service>.sh`
- `docs/catalog/service-catalog-matrix.md` 更新

## デプロイ TDD フロー（必須）
1. デプロイテスト仕様書の生成: `docs/test-specs/deploy-step2-additional-test-spec.md`
2. 検証スクリプトの生成: `infra/azure/verify-additional-resources.sh`（exit code: 0=全PASS, 非0=FAILあり）
3. 検証スクリプト実行 → 全 FAIL 確認（RED 状態）
4. デプロイスクリプトの作成・実行
5. 検証スクリプト実行 → 全 PASS まで修正（最大 3 回反復。超過時は `asdw-web:blocked` + FAIL 項目一覧を報告）

## Custom Agent
`Dev-Microservice-Azure-AddServiceDeploy` を使用

## 依存
- Step.2.2（追加 Azure サービス選定）が `asdw-web:done` であること

## 完了条件
- 出力ファイルが作成されている
- 検証スクリプトで全項目 PASS であること
{completion_instruction}{app_id_section}{additional_section}
