{root_ref}

{app_arch_scope_section}
## 目的
Azure CLIでデータ系サービスを最小構成で作成し、サンプルデータを変換・一括登録する（冪等・検証付き）。

## 入力
- リソースグループ名: `{resource_group}`
- `docs/azure/azure-services-data.md`
- `docs/catalog/service-catalog-matrix.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- `src/data/sample-data.json`

## 出力
- `infra/azure/create-azure-data-resources-prep.sh`
- `infra/azure/create-azure-data-resources.sh`
- `src/data/azure/data-registration-script.sh`
- `docs/azure/service-catalog.md` 更新

{existing_artifact_policy}

## デプロイ TDD フロー（必須）
1. デプロイテスト仕様書の生成: `docs/test-specs/deploy-step1-data-test-spec.md`
2. 検証スクリプトの生成: `infra/azure/verify-data-resources.sh`（exit code: 0=全PASS, 非0=FAILあり）
3. 検証スクリプト実行 → 全 FAIL 確認（RED 状態）
4. デプロイスクリプトの作成・実行
5. 検証スクリプト実行 → 全 PASS まで修正（最大 3 回反復。超過時は `asdw-web:blocked` + FAIL 項目一覧を報告）

## Custom Agent
`Dev-Microservice-Azure-DataDeploy` を使用

## 依存
- Step.1.1（Azure データストア選定）が `asdw-web:done` であること

## 完了条件
- 出力ファイルが作成されている
- 検証スクリプトで全項目 PASS であること
{completion_instruction}{app_id_section}{additional_section}
