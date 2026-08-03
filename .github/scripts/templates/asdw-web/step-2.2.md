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
- `src/infra/azure/create-azure-additional-resources-prep.sh`
- `src/infra/azure/create-azure-additional-resources/create.sh`
- （複数サービスの場合）`src/infra/azure/create-azure-additional-resources/services/<service>.sh`
- `docs/catalog/service-catalog-matrix.md` 更新
- `work/run/<run-id>/Dev-Microservice-Azure-AddServiceDeploy/Issue-<識別子>/ac-verification.md`（AC検証記録 — Orchestrator gate 検査対象）

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログ（work-status 系成果物）または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。必要に応じて `az ... -h` / パッケージマネージャ / 公式 CLI help を補助確認として使う。

{existing_artifact_policy}

## デプロイ TDD フロー（必須）
1. デプロイテスト仕様書の生成: `docs/test-specs/deploy-step2-additional-test-spec.md`
2. 検証スクリプトの生成: `src/infra/azure/create-azure-additional-resources/verify-additional-resources.sh`（exit code: 0=全PASS, 非0=FAILあり）
3. 検証スクリプト実行 → 全 FAIL 確認（RED 状態）
4. デプロイスクリプトの作成・実行
5. 検証スクリプト実行 → 全 PASS まで修正（最大 3 回反復。超過時は `asdw-web:blocked` + FAIL 項目一覧を報告）

> AI/LLM（Microsoft Foundry）採用時は、アカウント作成に加え **`--allow-project-management` 明示**、Foundry Project 子リソースの冪等作成、live catalog / quota に基づくモデル選定、モデルデプロイが必須。Project は `az cognitiveservices account project show` → 未存在時のみ `az cognitiveservices account project create` → `az cognitiveservices account project show` の順で確認し、account / Project / 設計の location 不一致は置換せず block する。Model Router は live catalog の `name=model-router` entry が返す format / version / SKU を使い、Balanced をモデル名として扱わない。検証スクリプトは Project `Succeeded`（AC-14）とデプロイ済みモデル 1 件以上（AC-13）を別々に確認すること（AI/LLM 非該当もAC-13/14のN/A行を残す）。親 account や `created-resources.json` だけを Project 実在の証拠にしない。

> サービス作成（`services/<service>.sh` の実行）は `create.sh` 内でバックグラウンドジョブにより**並列実行**すること。「ネットワーク境界」カテゴリ（Private Endpoint 等）は他サービスのリソースIDに依存するため、Wave A（ネットワーク境界以外を並列実行）→ Wave B（ネットワーク境界を実行）の2段階で実行する（詳細は Prompt §3.3.1「サービス作成の並列実行方針」）。

## Custom Agent
`Dev-Microservice-Azure-AddServiceDeploy` を使用

## 依存
- Step.2.1（追加 Azure サービス選定）が `asdw-web:done` であること
- Step.1.3（Azure データサービス Deploy）が `asdw-web:done` であること（local generation checkpoint 後の live フェーズ）

## 完了条件
- 出力ファイルが作成されている
- 検証スクリプトで全項目 PASS であること
{completion_instruction}{app_id_section}{additional_section}
