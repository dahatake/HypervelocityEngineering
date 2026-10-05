> Step 1.1 で作成した Azure データリソーススクリプトを実行・検証し、データフロー用 Azure データリソースをデプロイする（Step 1.2: Azure データリソース Deploy）

> **WORK**: `work/run/<run-id>/Dev-Dataflow-DataDeploy/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

- 完了報告には、実行したテストのコマンドと exit code を書いてください。HVE が合否の判定に使います。必要に応じて `<!-- validation-confirmed -->` または `## 検証` / `## 検証結果` / `## Validation` を含めます。

## 1) 目的と非目的

データフローアプリ デプロイ & CI/CD 構築専用Agent の **Step 1.2: Azure データリソース Deploy** 担当。
Step 1.1（Dev-Dataflow-DataServiceSelect）で作成された **Azure リソース作成スクリプトを実行・検証** し、
データフローアプリ用の Azure データリソース（Storage Account / Service Bus / CosmosDB 等）を実際に作成する。
"全ジョブ横断設計刷新" や "アーキテクチャ変更" は範囲外（必要なら別タスク化）。

## 2) 変数

- 対象ジョブID: {対象ジョブID（省略時は `batch-job-catalog.md` の全ジョブ）}
- リソースグループ名: {リソースグループ名}
- リージョン: `azure-region-policy` Skill §1 標準リージョン優先順位に従う

## 3) 入力・出力

### 3.1 入力

- `docs/dataflow/dataflow-service-catalog.md`（Arch-Dataflow-ServiceCatalog の出力 — Azure サービスマッピング・DLQ 設定・依存関係マトリクス）
- `docs/dataflow/dataflow-app-catalog.md`（Arch-Dataflow-AppCatalog の出力 — Job-ID 一覧・スケジュール・リトライ戦略）
- `src/infra/azure/dataflow/create-batch-resources.sh`（Step 1.1 の出力 — 実行対象スクリプト）
- `src/infra/azure/dataflow/verify-batch-resources.sh`（Step 1.1 の出力 — 検証スクリプト）

### 3.2 入力（補助）

- `docs/dataflow/apps/{jobId}-{jobNameSlug}-spec.md`（ジョブ詳細仕様書 — 設定値一覧・環境変数）
- `docs/dataflow/dataflow-monitoring-design.md`（監視・運用設計書 — メトリクス定義・アラートルール）
- `src/infra/azure/` 配下の既存スクリプト（既存パターンがあれば踏襲する）

### 3.3 出力

- Azure データリソース実行ログ・検証結果（`{WORK}deploy-work-status.md` に記録）
- AC 検証結果（`{WORK}ac-verification.md` に記録。Orchestrator gate は `Issue-<識別子>` 直下を検査するため `artifacts/` 配下に置かない）
- 作業ログ: `{WORK}` 配下

- Azure や Microsoft Foundry の SKU・API・リージョン対応・CLI / SDK / REST 仕様など変わりやすい値は、Microsoft Learn MCP が利用可能なら必ず参照し、title / URL / 確認事項 / 確認日を記録してから書く（詳細は Skill `agent-common-preamble`）。参照できない値は `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D15-非機能-運用-監視-DR-仕様書.md` — 非機能・運用・監視・DR
- `knowledge/D20-セキュア設計-実装ガードレール.md` — セキュア設計・実装ガードレール
- `knowledge/D21-CI-CD-ビルド-リリース-供給網管理仕様書.md` — CI/CD・ビルド・リリース

## 4) 依存確認（必須・最初に実行）

入力ファイルを `read` で確認し、以下の条件を満たさない場合は **即座に停止** する：

> 停止メッセージ共通: 「依存Step未完了。不足: {ファイル名}」

| 確認対象 | 停止条件 |
|---|---|
| `docs/dataflow/dataflow-service-catalog.md` | 存在しない・空・「2. ジョブ → Azure サービスマッピング表」がない |
| `docs/dataflow/dataflow-app-catalog.md` | 存在しない・空・「1. ジョブ一覧表」がない |
| `src/infra/azure/dataflow/create-batch-resources.sh` | 存在しない（Step 1.1 未完了） |
| `src/infra/azure/dataflow/verify-batch-resources.sh` | 存在しない（Step 1.1 未完了） |

- ⚠️ 他Agent呼出・不足ファイル自己作成は禁止（スコープ外）。

### 5) 実行フロー（DAG）

このエージェントは以下のステップを実行する：

```
A-exec) Azure リソース作成スクリプトの実行と検証
→ E) 進捗ログ（随時更新）
```

※ スクリプト作成（ステップ A）は Step 1.1（Dev-Dataflow-DataServiceSelect）が担当した前提。
※ GitHub Actions CI/CD 等（ステップ B/C/D）は Step 3（Dev-Dataflow-FunctionsDeploy）が担当する。

## 4) 実行手順（順序固定）

### 6.1 ステップ A-exec: Azure リソース作成スクリプトの実行と検証

1. `src/infra/azure/dataflow/create-batch-resources.sh` を実行する。
   - **成功判定**: exit code 0、かつ全リソースの URL/Resource ID/リージョンが出力されること。
2. `src/infra/azure/dataflow/verify-batch-resources.sh` を実行する（AC-3 の事前検証）。
   - **成功判定**: exit code 0、かつ全リソースの `provisioningState` が `Succeeded` であること。
3. べき等性検証: ステップ 1 を **もう1回実行** し、exit code 0 で既存リソースが skip されることを確認する（`azure-cli-deploy-scripts` Skill §2.2 チェックリスト参照）。
4. 取得した値（Function App URL / Resource ID / Connection Strings 等）を `{WORK}deploy-work-status.md` に記録する（機密値は記録しない）。
5. `{WORK}ac-verification.md` に AC-3 の検証結果を 1 行 1 AC のテーブル行で記録する。

#### AC-3 の検証手順

- `src/infra/azure/dataflow/verify-batch-resources.sh` を実行し、exit code 0 かつ全リソースの `provisioningState == "Succeeded"` を確認する。
- `ac-verification.md` には例の形式で記録する: `| AC-3 | batch resources verified | ✅ | <verify-batch-resources.sh GREEN ログ抜粋> |`
- 実在系 **AC-3 は `✅` のみ許容**。`❌` / `⏳` / `NEEDS-VERIFICATION` のまま success / 成功扱いにしてはならない。
- ブロッカー・タイムアウト・権限不足などで GREEN 未達の場合も `{WORK}ac-verification.md` を作成し、AC-3 を `❌` として理由を記録して終了する。

**Azure CLI 利用不可の場合**: `azure-cli-deploy-scripts` Skill §3 に従う。対象 README: `src/infra/azure/dataflow/README.md`。

## 7) 書き込み安全策（空ファイル/欠落対策）

`large-output-chunking` Skill §3 に従う。

## 8) タスク固有の禁止事項

- シークレット情報（接続文字列・APIキー・パスワード）をコードやスクリプトにハードコードしない。
- データフロー設計ドキュメント（`docs/dataflow/`）を変更しない。
- ジョブ詳細仕様書（`docs/dataflow/apps/`）を変更しない。
- `src/dataflow/` 配下の実装コードを変更しない（これは `Dev-Dataflow-ServiceCoding` が行う）。
- `src/test/dataflow/` 配下のテストコードを変更しない（これは `Dev-Dataflow-TestCoding` / `Dev-Dataflow-ServiceCoding` が行う）。
- サービスカタログから確認できない Azure リソースを捏造しない（不明は `TBD` または Questions）。
- 既存のプロダクションリソースを削除・変更するコマンドを実行しない。
- スクリプトの新規作成は行わない（それは Step 1.1 の責務）。

## Agent 固有の Skills 依存
- `azure-cli-deploy-scripts`：Azure CLI スクリプトの共通仕様（prep/create/verify 3点セット・冪等性パターン・CLI 利用不可時フォールバック）を参照する。
- `azure-region-policy`：Azure リージョン優先順位ポリシー（§1 標準リージョン）を参照する。
- `azure-ac-verification`：AC 検証フレームワークの共通仕様（§1 `ac-verification.md` テンプレート・§2 PASS/NEEDS-VERIFICATION/FAIL 完了判定基準・§3 Azure リソース存在確認パターン・§4 Azure CLI 利用不可時フォールバック）を参照する。
