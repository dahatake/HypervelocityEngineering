{root_ref}

{app_arch_scope_section}
## 目的
データフローアプリ設計書・サービスカタログを根拠に、必要な Azure データ系リソースを特定し、リソース作成スクリプトと検証スクリプトを準備する。

## 入力
- `docs/dataflow/dataflow-domain-analytics.md`
- `docs/dataflow/dataflow-data-source-analysis.md`
- `docs/dataflow/dataflow-data-model.md`
- `docs/dataflow/dataflow-app-catalog.md`
- `docs/dataflow/dataflow-service-catalog.md`
- `docs/dataflow/dataflow-test-strategy.md`（テスト戦略書: データストア選定の参考）

## 出力
- `src/infra/azure/dataflow/create-batch-resources.sh`（Azure CLI リソース作成スクリプト）
- `src/infra/azure/dataflow/verify-batch-resources.sh`（Azure CLI リソース検証スクリプト）

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログ（work-status 系成果物）または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。必要に応じて `az ... -h` / パッケージマネージャ / 公式 CLI help を補助確認として使う。

{existing_artifact_policy}

## Custom Agent
`Dev-Dataflow-DataServiceSelect` を使用

## 依存
- 依存なし（最初の Step）

## 完了条件
- `src/infra/azure/dataflow/create-batch-resources.sh` が作成されている
- `src/infra/azure/dataflow/verify-batch-resources.sh` が作成されている
{completion_instruction}{rg_section}{job_section}{additional_section}