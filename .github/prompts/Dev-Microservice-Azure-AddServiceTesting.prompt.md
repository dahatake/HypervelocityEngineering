> Step.2.3 で生成された追加 Azure サービスの integration test を実環境に対して実行し、TDD GREEN フェーズとして全 PASS させる。テストコードは原則変更しない（テスト保護ルール）。GREEN にならない原因が「接続設定 / IAM / リソース設定」の場合、`src/infra/azure/` 配下の最小修正で解決する。

> **WORK**: `work/run/<run-id>/Dev-Microservice-Azure-AddServiceTesting/Issue-<識別子>/`

## TDD テスト結果レポート（必須）

- 出力先: `tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md`
- `src/test/` はテストコード専用、`tests/` はテスト結果レポート専用とし、実行ログを `docs/` / `src/` に追記しない。
- 必須ラベル: `Schema-Version`, `Evidence-Status`, `TDD-Judgement`, `Secret-Redaction`, `Test-Files-Changed`。
- RED は Step 固有の期待結果を `Expected Outcome` に記録し、GREEN は `TDD-Judgement: PASS` とテスト保護証跡を必須とする。
- 固定スキーマは Skill `tdd-red-green-reality` の `tdd-test-report.md` テンプレートに従う。ラベルは必ず `- Label: value` 形式で書き、`Label: value` のプレーン行にしない。
- 見出し名は `## Command`, `## Expected Outcome`, `## Actual Result`, `## Evidence`, `## Failure Analysis`, `## Test Protection` に固定する。`## Result` / `## Observed Result` / `## Actual Outcome` / `## Changed Test Files` などの代替名は禁止。

```markdown
# TDD Test Report - <target-key> <phase>

<!-- validation-confirmed -->

- Schema-Version: 1
- Workflow: <workflow-id>
- Step: <step-id>
- Agent: <custom-agent-name>
- Target-Key: <target-key>
- Phase: <RED/GREEN>
- Test-Code-Path: <src/test/...>
- Timestamp-UTC: <ISO-8601 UTC timestamp>
- Evidence-Status: EXECUTED
- TDD-Judgement: <PASS/FAIL>
- Secret-Redaction: confirmed
- Test-Files-Changed: <yes/no/N/A>

## Command

## Expected Outcome

## Actual Result

## Evidence

## Failure Analysis

## Test Protection
```

TDD GREEN フェーズ専用 Agent（追加 Azure サービス向け）。
本 Agent は **追加 Azure サービスがマネージドサービスである**前提のため、`Dev-Microservice-Azure-ServiceCoding-AzureFunctions` のような実装コード生成は**行わない**。代わりに「設定補完（接続情報・IAM・リソース構成の差分修正）」と「テスト実行ループ」を担う。

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

> 共通行動規約 (`.github/copilot-instructions.md` §0 / Skill `agent-common-preamble`) の禁止事項を本 Agent でも明示する。

- **捏造禁止**: 接続文字列 / リソース名 / リージョン / SKU を根拠なく生成しない。不明は `TBD` または `不明（要確認）` と明記する。
- **無関係変更禁止**: スコープ外のファイル整形・一括リファクタを行わない（最小差分）。
- **検証マーカー欠落禁止**: 完了報告に `<!-- validation-confirmed -->` または `## 検証` を含める。
- **work/ 直接編集禁止**: §4.1 準拠。
- **`original-docs/` 書き込み禁止**。
- **ルート `README.md` 変更禁止**。
- **秘密情報禁止**: 接続文字列 / アカウントキー / SAS / トークンを成果物（コード / README / 作業ログ）に含めない。
- **テストコード変更禁止**（テスト保護ルール）: `src/test/integration/add-service/` のテストコード本体（`.cs` ファイル）は原則変更しない。許可される変更は以下のみ:
  - テストプロジェクトの環境変数読み込み用ヘルパー（テストロジック非依存）
  - `appsettings.Testing.json` 等の **テスト設定ファイル**（接続先のみ）

## Agent 固有の Skills 依存

- `microservice-design-guide` — 追加サービス利用契約の参照
- `work-artifacts-layout` — `work/` 配下 §4.1 準拠
- `harness-verification-loop` — Build / Lint / Test / Security / Diff
- `harness-error-recovery` — テスト失敗時の E-01〜E-05 リカバリ
- `harness-safety-guard` — リソース削除等の破壊的操作の検出と中断
- `tdd-red-green-reality` — 実テスト実行で GREEN を証明・恒真式で誤魔化しない・プラットフォーム別 verify コマンドの確定
- `karpathy-guidelines` — LLM 共通ミス防止

## 生成テストの実行環境

- 本 Step の `dotnet test` は、追加 Azure サービスが正しくデプロイ済み・構成済みであることを前提にした外部サービス検証である。
- ローカル端末 / CI / デプロイ先のいずれでも、同じ環境変数または `appsettings.Testing.json` 等のテスト設定ファイルで接続先・認証・Resource 名を注入する。
- 必須設定が未設定の場合は C1 接続設定不備または環境ブロッカーとして扱い、テストを弱めたり skip したりして PASS 扱いしない。
- 接続文字列・アカウントキー・SAS・Bearer token 等の秘密情報をコード、README、ログにハードコードしない。

## Azure 公式情報参照（Microsoft Learn MCP 必須）

- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログ（work-status 系成果物）または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。必要に応じて `az ... -h` / パッケージマネージャ / 公式 CLI help を補助確認として使う。

# 1) 目的（スコープ固定）

- 対象は **Step.2.3 で生成された integration テストプロジェクト全件**。
- 目的は「`dotnet test` を実行し、全テストを PASS（TDD GREEN）させる」こと。
- GREEN にならない場合の解決手段は以下に限定する（優先順位順）:
  1. **環境変数 / appsettings 設定の補完**（接続先・認証方式の指定）
  2. **`src/infra/azure/` 配下の bicep / azd 設定の最小修正**（IAM ロール追加 / コンテナ・インデックス・トピック等の追加リソース定義）+ 再デプロイ
  3. 上記で解決しない場合は `asdw-web:blocked` ラベル付与 + **原因別フィードバック先**:
     - C4（設定値不一致 / SKU ミスマッチ等 → 選定見直し必要）→ **Step.2.1 へフィードバック**
     - C2/C3（IAM 不足 / リソース未作成 → デプロイ範囲不足）→ **Step.2.2 へフィードバック**
     - C5（テスト本体不備 → ケース追加/修正必要）→ **Step.2.3 へフィードバック**
- "全アプリ対応""設計刷新""横断リファクタ"は範囲外。

# 2) 入力（優先順位順）

必須:

- `src/test/integration/add-service/`（Step.2.3 の成果物 — テストプロジェクト群）
- `docs/azure/azure-services-additional.md`（Step.2.1 出力 — 期待する SKU / レプリケーション / インデックス設定）
- `docs/catalog/app-catalog.md`（APP-ID スコープ判定根拠 — io-contract で required: true）

参照候補（存在すれば読む）:

- `src/infra/azure/`（Step.2.2 のデプロイ成果物 — bicep / azd / verify スクリプト）
- `docs/catalog/service-catalog-matrix.md`（追加サービス利用サービス）
- `docs/catalog/test-strategy.md`
- 各テストプロジェクトの `README.md`（Step.2.3 出力 — 接続環境変数一覧 / 想定 IAM ロール）

## APP-ID スコープ → Skill `app-scope-resolution` を参照

# 3) 出力（成果物）

必須:

- **テスト実行ログ**（完了報告 / `{WORK}/test-run.log`）— 全プロジェクトの `dotnet test` 出力と PASS / FAIL 集計
- `src/test/integration/add-service/`（io-contract 上は `mode: append`）— 設定ファイル（`appsettings.Testing.json` 等）の追加 / 更新のみ

任意（必要に応じて）:

- `src/infra/azure/` 配下の **最小差分パッチ**（IAM ロール追加 / リソース設定追加）— 変更が必要な場合のみ
- `src/infra/azure/` 配下のスクリプトによる **再デプロイ実行** — 上記設定変更を反映する場合

作業ログ（Skill work-artifacts-layout 既定）:

- `{WORK}` に従う。失敗テスト → 原因 → 対応の対応表を記載。

# 4) 依存確認（必須・最初に実行）

| 確認対象 | 停止条件 | 報告メッセージ |
|---|---|---|
| `src/test/integration/add-service/` | 存在しない・空 | 「依存 Step 2.3（追加サービステストコード生成）が未完了のため実行不可です」 |
| Step.2.2 完了状態 | デプロイ未完了が確認できる場合 | 「依存 Step 2.2（追加サービス Deploy）が未完了のため、リソース未作成テストが必ず FAIL します。先に Step.2.2 を完了させてください」 |
| Azure 接続 | 以下すべてが fail: (a) `az account show` コマンド、(b) env `AZURE_CLIENT_ID` / `AZURE_FEDERATED_TOKEN_FILE`（OIDC）、(c) `DefaultAzureCredential` の初期化 | 「Azure 認証経路がいずれも確立していません。`az login` / GitHub Actions OIDC / Managed Identity のいずれかをセットアップしてください」 |

# 5) 実行手順（この順で）

## 5.1) 接続情報の確認と環境変数投入

- 各テストプロジェクトの README に記載された環境変数一覧を取得する。
- Step.2.2 のデプロイ成果物（bicep output / `azd env get-values`）から接続エンドポイント・リソース名を取得する。**捏造禁止**。
- `azd env get-values` の全出力をログや成果物へ保存しない。README で必要とされた非秘密の名前・endpoint だけを選択し、secret / key / connection string / token は表示・記録しない。
- 環境変数を `.env.testing` または GitHub Actions secrets / variables に投入する（**秘密情報はログ・成果物に出力しない**）。

## 5.2) TDD GREEN ループ（最大 `tdd_max_retries` 回反復）

> `tdd_max_retries` は registry `WorkflowDef.params` で宣言され、Issue body または CLI 起動時パラメータとして渡される（既定 5）。

> **リトライ戦略（Skill `tdd-green-retry-strategy` 準拠）**: 各反復は前回と**異なるアプローチ**を選ぶ（下記 C1〜C5 の原因分類が対応先の切り替え軸になる）。同一の手当てを単純に繰り返さない。各失敗時は根本原因を実出力から特定し、次の対応を決める前に **Microsoft Learn MCP**（Azure / C# / Azure CLI / SDK / REST API）で正しい構文・設定・前提を確認する。Web 検索は MCP で解決できない場合のみ用いる。

1. **`dotnet test` 実行**: 全プロジェクトのテストを並列実行し、FAIL リストを取得する。
2. **失敗原因の分類**: 各 FAIL を以下のカテゴリに分類する:
   - **C1 接続設定不備**: エンドポイント / 認証情報の欠落 → 5.3 で対応
   - **C2 IAM 不足**: 401 / 403 / `RoleAssignmentNotFound` → 5.4 で対応
   - **C3 リソース未作成**: 404 / `ContainerNotFound` / `IndexNotFound` 等 → 5.4 で対応。
    - **Foundry Project 未作成（`az cognitiveservices account project show --name <account> --resource-group <RG> --project-name <project>` が NotFound / 非 `Succeeded`）は Project 作成＝ Step.2.2 の責務のため、本 Agent では自己対応せず即中断し、Step.2.2 へフィードバックして `asdw-web:blocked` を付与する。**親 account の存在や `created-resources.json` だけで GREEN にしない。
     - **Foundry のモデル未デプロイ（`az cognitiveservices account deployment list` が 0 件）は、モデルデプロイ＝ Step.2.2（Deploy）の責務のため 5.4 で自己対応せず、即中断して Step.2.2 へフィードバックし `asdw-web:blocked` ラベル付与**（本 Agent は Project / モデルを作成しない）。
   - **C4 設定値不一致**: SKU / レプリケーション / 整合性レベル等（**Foundry のモデル SKU / 容量を含む**）が `azure-services-additional.md` と不一致 → 設計見直し必要のため **即中断（リトライ枠を消費せず）して Step.2.1 へフィードバック**し `asdw-web:blocked` ラベル付与
   - **C5 テスト本体の不備**: テストコード自体に誤りが疑われる → **即中断（リトライ枠を消費せず）して Step.2.3 へフィードバック**し `asdw-web:blocked` ラベル付与
3. **対応の実施**（5.3 / 5.4）後、手順 1 へ戻る。各対応の採用アプローチ・根本原因・参照した Microsoft Learn の URL を作業ログに短く記録する。
4. **`tdd_max_retries` 回反復しても全 PASS にならない場合**: `asdw-web:blocked` ラベルを付与し、試した各アプローチ・未 PASS テスト一覧 + 原因分類 + フィードバック先 Step を **Issue コメント（GitHub Issue 起点モード）または `work/run/<run-id>/Issue-<識別子>/completion-report.md`（CLI セッション起点モード）で報告する。

## 5.3) 設定補完（C1 対応）

- 環境変数 / `appsettings.Testing.json` を更新する。
- **秘密情報はテストランナーの環境変数経由のみ**。コード / 設定ファイルにハードコードしない。
- 環境変数の命名 / 既定値は各テストプロジェクトの README に明記された規約に従う。

## 5.4) インフラ最小修正（C2 / C3 対応）

- `src/infra/azure/` 配下の bicep / azd 設定に **最小差分** で IAM ロール追加 / コンテナ・インデックス等のリソース追加を適用する。
- Foundry Project の作成とモデル deployment の作成・更新は Step.2.2 の専任責務であり、本 Agent の C2 / C3 最小修正に含めない。Project／モデル不在は §5.2 の分類どおり block して Step.2.2 へ戻す。
- **再デプロイは破壊的操作を避ける責務がある**。推奨手順:
  1. `az deployment group what-if --resource-group <RG> --template-file <bicep>` で実際の差分を確認
  2. 破壊的変更 (Delete / Replace) が無いことをログに記録
  3. `az deployment group create`（または `azd provision`）で適用。`azd up` は deploy + provision の両方を含むため本 Agent では**推奨しない**
  4. 適用後、Step.2.2 で使用された verify スクリプト（存在すれば）を実行して反映を検証
- 修正内容を作業ログに記録する（what-if 出力と変更前後の diff）。
- **C4 （設定値不一致）は本 Agent では修正しない** — §1 の「フィードバック先」に従い Step.2.1 へ差し戻す。

## 5.5) 全 PASS 確認

- `dotnet test` を最終実行し、全プロジェクトで PASS することを確認する。
- テスト実行ログ（コマンド出力含む）を `{WORK}/test-run.log` に保存する。

# 6) 禁止事項（このタスク固有）

- `src/test/integration/add-service/` のテストコード本体（`.cs` ファイル）を変更しない（テスト保護ルール）。
- `src/api/` 配下の自前実装コードを生成・変更しない（Step.3.3 の責務）。
- `docs/azure/azure-services-additional.md` を変更しない（読み取り専用 — 変更が必要なら Step.2.1 へフィードバック）。
- リソースの削除 / 再作成を行わない（既存リソース保護）。
- Foundry Project を作成・更新せず、新しいモデル deployment を作成・更新しない。
- **`azd up` の実行禁止**（provision + deploy を同時実行し deploy 側で意図しない変更を起こしうるため）。代わりに `az deployment group create` または `azd provision` を使う（§5.4 参照）。
- 接続文字列・アカウントキー・SAS をログ / 成果物に含めない。

# 7) 完了条件（DoD）

- 全 integration テストプロジェクトで `dotnet test` が PASS（TDD GREEN）。
- Foundry 採用時は、Project 子リソース実在テストとモデル deployment 実在テストが別々に存在し、両方が実行済みで PASS している。
- テスト実行ログ（`{WORK}/test-run.log`）に最終実行結果（PASS 件数 / 0 FAIL）が記録されている。
- インフラ修正を行った場合、`src/infra/azure/` の diff が最小差分で適用され、変更理由が作業ログに記録されている。
- `tdd_max_retries` 反復で解決できなかった場合、`asdw-web:blocked` ラベル + 詳細レポートが提供されている。
- 完了報告に検証マーカーを含める。

# 8) 最終品質レビュー（単回インライン・セルフチェック）

## 8.1 セルフチェック契約

以下のドメイン固有観点は、通常時に1回のインライン・セルフチェックとしてまとめて確認し、敵対的レビューの発動条件ではない。

## 8.2 ドメイン固有観点

- **テスト保護ルール遵守 & スコープ整合性**：テストコード本体が変更されていないか、`src/api/` 配下に変更が及んでいないか、`docs/azure/azure-services-additional.md` が読み取り専用扱いされているか、修正は `src/infra/` と設定ファイルに限定されているか
- **TDD GREEN 達成と原因記録の品質**：全テスト PASS のエビデンスが具体的か、FAIL → 原因 → 対応の対応表が具体的か、C5（テストロジック・assertion・SDK/API利用等のテスト本体不備）が誤って C1〜C4 で握り潰されていないか
- **セキュリティ & 運用品質**：秘密情報がログ・成果物に漏洩していないか、Managed Identity が優先採用されているか、インフラ修正の minimum diff 原則が守られているか、blocked ラベル付与時のフィードバック品質

## 8.3 反映方法

確認結果は独立したレビュー成果物にせず、問題があれば主成果物を修正し、完了報告の検証結果へ簡潔に含める。

### knowledge/ 参照（任意・存在する場合のみ）

- `knowledge/D17-品質保証-UAT-受入パッケージ.md` — 品質保証・UAT
- `knowledge/D20-セキュア設計-実装ガードレール.md` — セキュア設計・実装ガードレール
