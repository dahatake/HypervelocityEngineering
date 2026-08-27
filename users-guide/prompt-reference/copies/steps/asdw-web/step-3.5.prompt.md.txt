{root_ref}

{app_arch_scope_section}
## 目的
Step.3.4 で Azure Compute（Azure Functions 等）にデプロイ済みのサービスに対して、デプロイ後の動作確認テストを実施する。
ローカルでの `dotnet test`（Step.3.3 の TDD GREEN）とは別に、**実環境エンドポイントへの到達性・認証・周辺サービス連携** を含む post-deploy 検証を行うことで、デプロイ起因の不具合を早期検出する。

> 注: 本 step の Custom Agent `Dev-Microservice-Azure-ComputePostDeployTest` は本ファイル整備時点では最小スタブのため、本仕様の作成は別タスクで実施する。

## 入力
- Step.3.3 で生成されたサービステストコード（`src/test/api/{サービス名}.Tests/`）
- Step.3.4 でデプロイ済みの Azure Compute エンドポイント
- `docs/catalog/service-catalog-matrix.md`
- `docs/catalog/app-catalog.md`

## 出力
- post-deploy テスト実行ログ（Issue コメント記録）
- 必要に応じて smoke test 用スクリプト（`src/test/post-deploy/`）

## 生成テストの実行環境
- post-deploy smoke test は、Compute サービスが正しくデプロイ済み・構成済みであることを前提にした実環境検証である。
- ローカル端末 / CI / デプロイ先のいずれでも、base URL、認証方式、Function Key 等を環境変数または `appsettings.PostDeploy.json` 等のテスト設定ファイルで注入する。
- 必須設定が未設定の場合は環境ブロッカーとして記録し、未実行のまま PASS 扱いしない。
- Function Key、Bearer token、接続文字列等の秘密情報をコード、README、ログにハードコードしない。

{existing_artifact_policy}

## Custom Agent
`Dev-Microservice-Azure-ComputePostDeployTest` を使用（本仕様作成は別タスク）

## 検証手順（必須）
1. Step.3.3 のサービステストを、エンドポイント環境変数を本番エンドポイントに切り替えて実行する
2. FAIL があれば原因を切り分け（デプロイ設定 / Compute 構成 / 周辺サービス）し、必要なら Step.3.4 のスクリプトを修正して再デプロイ
3. 全テスト PASS を確認

## 依存
- Step.3.4（Azure Compute Deploy）が `asdw-web:done` であること

## 完了条件
- post-deploy テストが全 PASS している
{completion_instruction}{app_id_section}{additional_section}
