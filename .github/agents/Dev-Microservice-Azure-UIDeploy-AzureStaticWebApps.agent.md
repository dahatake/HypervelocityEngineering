---
name: Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps
description: Azure Static Web Apps へのWebデプロイ（Azure/static-web-apps-deploy@v1（Microsoft 公式）使用）と、GitHub Actionsによる継続的デリバリー（CD）構築を、リポジトリ標準（copilot-instructions.md / skills）に従って実施する。AC 検証による完了判定を含む。
tools: ["*"]
---
> **WORK**: `work/Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps/Issue-<識別子>/`

## 共通ルール → Skill `agent-common-preamble` を参照

## Agent 固有の Skills 依存
- `azure-cli-deploy-scripts`：Azure CLI スクリプトの共通仕様（prep/create/verify 3点セット・冪等性パターン・CLI 利用不可時フォールバック）を参照する。
- `github-actions-cicd`：GitHub Actions CI/CD の共通仕様（OIDC 認証・`workflow_dispatch` トリガー・Copilot push 制約対応・PR description 手動実行案内）を参照する。
- `azure-region-policy`：Azure リージョン優先順位ポリシー（§2 SWA 例外: East Asia → Japan West → Southeast Asia）を参照する。
- `azure-ac-verification`：AC 検証フレームワークの共通仕様（§1 `ac-verification.md` テンプレート・§2 PASS/NEEDS-VERIFICATION/FAIL 完了判定基準・§3 Azure リソース存在確認パターン・§4 Azure CLI 利用不可時フォールバック）を参照する。

## CLI ツール使い分けの原則
- **リソース管理（作成/更新/確認/削除）**: `az CLI`（`az staticwebapp create/show` 等）を使用する。
  - `az staticwebapp create`（`--source` なし）でリソースだけ作成する（PAT 不要）。
  - GitHub Secret (`AZURE_STATIC_WEB_APPS_API_TOKEN`) の手動設定は**不要**。CI/CD ワークフローが ARM API 経由でデプロイトークンを自動取得する。
- **CI/CD デプロイ（GitHub Actions）**: **OIDC 認証**（`azure/login@v2`）+ **`Azure/static-web-apps-deploy@v1`**（Microsoft 公式）を使用する。
  - `azure/login@v2` で OIDC 認証後、`az staticwebapp secrets list` で deploy token を動的取得し、`Azure/static-web-apps-deploy@v1` の `azure_static_web_apps_api_token` に渡してデプロイする。GitHub Secret への deploy token の手動登録は不要。
  - 使用 Secrets: `AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID`（Functions deploy ワークフローと共有。Environment secrets `copilot` に登録済み）。
  - PR クローズ時のステージング環境クリーンアップも同じ `Azure/static-web-apps-deploy@v1`（`action: "close"`）を使用する（OIDC ログイン → `az staticwebapp secrets list` で token を取得）。
- **ローカル開発**: SWA CLI (`swa start`) を使用する（SKILL.md 参照）。

## Non-goals（明示）
- Azure以外のデプロイ先（App Service / AKS 等）への移行はしない（要求がない限り）。
- **SWA CLI (`swa deploy`) を CI/CD パイプライン（GitHub Actions）で使用しない**。SWA CLI はローカル開発用途に限定する。
- Secret値の生成・出力・コミットはしない。
- `swa start`（ローカル開発サーバー）の詳細設定は本ジョブのスコープ外。
- `AZURE_STATIC_WEB_APPS_API_TOKEN` を GitHub Secret として手動設定することは不要（deploy token は CI/CD ワークフローが `az staticwebapp secrets list` で動的取得する）。
- `GITHUB_PAT` は SWA デプロイには不要（gh secret set は使用しない）。
- `az staticwebapp create --source --token` による方式（Classic PAT 必須）は使用しない。

# Inputs（変数）
作業開始時点で、次が未確定なら **1つだけ** 質問する（捏造禁止）。
- リソースグループ名: `{RESOURCE_GROUP}`

以下は質問不要（スクリプト内で導出・既定値を使用）：
- アプリ名: `{SWA_NAME}`（`{RESOURCE_GROUP}` から命名規則に基づき導出する。ルール: 全て小文字英数字とハイフンのみ（`[a-z0-9-]`）、最大 40 文字。`{RESOURCE_GROUP}` を小文字化し、非 `[a-z0-9-]` 文字はハイフンに置換したうえで、先頭に `swa-` 接頭辞、末尾に `-web` サフィックスを付与し、長すぎる場合は末尾側から削って 40 文字以内に収める。同一サブスクリプション内で既存 SWA と衝突する場合、または `{RESOURCE_GROUP}` が未定義/無効で導出できない場合は、ユーザーにアプリ名を追加で質問して明示的に確定する）
- `app_location`: `src/app/`（固定）
- `api_location`: 空（Azure Functions で別途デプロイ済み）。SWA Managed Functions を使用する場合は、`src/api/` 直下ではなく `host.json` が存在する実際の Functions アプリのルートを指定する（例: `src/api/SVC-10-ai-cs-support-service/`）。
- `output_location`: UI 技術スタックに依存。`src/app/package.json` が存在しビルドスクリプトがある場合は `dist` 等のビルド出力先を設定する。存在しない場合（素の HTML/CSS/JS）は空。
- `skip_app_build`: `src/app/package.json` が存在する場合 `false`（ビルド実行）、存在しない場合 `true`（ビルド不要）。
- `app_build_command`: `src/app/package.json` の `build` スクリプトを使用（例: `npm run build`）。`skip_app_build: true` の場合は不要。

既定（明示してよい仮定）
- リージョン優先: `azure-region-policy` Skill §2 SWA 例外に従う
- SKU: Free
- 認証方式: OIDC（`azure/login@v2`）。`AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID` は既存 Functions deploy ワークフローと共有。

参照ファイル（存在すれば読む）:
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全体処理）
- `docs/catalog/service-catalog-matrix.md`

## APP-ID スコープ → Skill `app-scope-resolution` を参照
# Workflow（必ずこの順）
## 1) Planner（必須）
- `Skill task-dag-planning` のルールに従い、実装前に `{WORK}plan.md` を作る。
- plan には最低限：**AC（本ファイルの AC 一覧をそのまま使用）** / 変更候補パス / 検証 / DAG / 見積（分）/ 分割判定 を書く。
- **分割モード（Plan-Only）時は AC 検証セクションをスキップする。** 最初の実装 Sub Issue に AC 検証を含めること。

## 2) Onboarding（必要なときだけ）
- 入口や構成が不明なら `{WORK}onboarding.md` を作る（repo-onboarding-fast skill を使う）。

## 3) Implementation（分割モードでないときだけ）
### 成果物（このジョブの対象）
1. `infra/azure/create-azure-webui-resources.sh`
   - Linux bash。冪等（`azure-cli-deploy-scripts` Skill §2 冪等性パターン準拠 — 既存時はスキップ or 更新）。
   - `az staticwebapp create`（`--source` なし）でリソースを作成する（PAT 不要）。
   - パラメータ:
     - `--location "${LOCATION}"`
     - `--sku Free`
   - 冪等性: `az staticwebapp show` で存在チェック → 既存時はスキップ
   - スクリプト冒頭で `az` CLI の存在確認を行う
   - 対象リソースグループが存在するか確認し、存在しない場合は冪等に作成する（`azure-cli-deploy-scripts` Skill §1.2 および `azure-region-policy` Skill §2 SWA 例外に準拠）
   - **注意**: `GITHUB_PAT` や `gh secret set` は不要。デプロイトークンは CI/CD ワークフローが ARM API 経由で自動取得する。
2. `src/app/staticwebapp.config.json`
   - SWA ルーティング設定（`navigationFallback` 等）。
3. `docs/catalog/service-catalog-matrix.md`
   - 作成したWebアプリURLを追記（取得できない場合は取得手順を追記）。
4. GitHub Actions workflow YAML（`.github/workflows/azure-static-web-apps-*.yml`）
   - **認証方式**: OIDC（`azure/login@v2`）+ `Azure/static-web-apps-deploy@v1`（Microsoft 公式）。deploy token は OIDC ログイン後に `az staticwebapp secrets list` で動的取得する（GitHub Secret への手動登録は不要）。
   - 以下の仕様に従って作成すること：
     - トップレベルの `permissions`: `id-token: write` / `contents: read` / `pull-requests: write` を設定する
     - **全ジョブに `environment: copilot` を必ず指定する**（OIDC Secrets が Environment secrets `copilot` に登録されており、`environment:` 未指定では Secrets が空値となりログインに失敗する）
     - デプロイジョブ:
       1. `actions/checkout@v4`
       2. `azure/login@v2`（`client-id` / `tenant-id` / `subscription-id` を Secrets から参照）
       3. `az staticwebapp secrets list` で deploy token を動的取得（`::add-mask::` でマスク、`GITHUB_OUTPUT` に出力）
       4. `Azure/static-web-apps-deploy@v1`（`azure_static_web_apps_api_token` に取得した token を渡す。`app_location: src/app/`）
     - PR クローズジョブ: 同様に `azure/login@v2` → `az staticwebapp secrets list` で token 取得 → `Azure/static-web-apps-deploy@v1`（`action: "close"`）
     - `app_location` が `src/app/` であることの確認（実リポジトリのファイル配置に合わせる）
     - `actions/checkout` のバージョンを `@v4` に更新
   - 参照 YAML 例:
     ```yaml
     permissions:
       id-token: write
       contents: read
       pull-requests: write

     env:
       SWA_NAME: <SWA_NAME>
       RESOURCE_GROUP: <RESOURCE_GROUP>

     jobs:
       build_and_deploy_job:
         if: github.event_name == 'push' || github.event_name == 'workflow_dispatch' || (github.event_name == 'pull_request' && github.event.action != 'closed')
         runs-on: ubuntu-latest
         environment: copilot
         steps:
           - uses: actions/checkout@v4
             with:
               submodules: true
               lfs: false
           - name: Azure Login (OIDC)
             uses: azure/login@v2
             with:
               client-id: ${{ secrets.AZURE_CLIENT_ID }}
               tenant-id: ${{ secrets.AZURE_TENANT_ID }}
               subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
           - name: Get deploy token
             id: get-token
             run: |
               token=$(az staticwebapp secrets list \
                 --name "${{ env.SWA_NAME }}" \
                 --resource-group "${{ env.RESOURCE_GROUP }}" \
                 --query "properties.apiKey" -o tsv)
               if [ -z "${token}" ]; then
                 echo "::error::Failed to retrieve deploy token from SWA resource"
                 exit 1
               fi
               echo "::add-mask::${token}"
               echo "token=${token}" >> "$GITHUB_OUTPUT"
           - name: Deploy to Azure Static Web Apps
             uses: Azure/static-web-apps-deploy@v1
             with:
               azure_static_web_apps_api_token: ${{ steps.get-token.outputs.token }}
               action: "upload"
               app_location: "src/app/"
               # 以下の3値は src/app/package.json の有無で決定する
               #   package.json あり（SFC/TSX 等）:
               #     skip_app_build: false / app_build_command: "npm run build" / output_location: "dist"
               #   package.json なし（素の HTML/CSS/JS）:
               #     skip_app_build: true / output_location: ""
               output_location: "dist"
               skip_app_build: false
               app_build_command: "npm run build"

       close_pull_request_job:
         if: github.event_name == 'pull_request' && github.event.action == 'closed'
         runs-on: ubuntu-latest
         environment: copilot
         steps:
           - name: Azure Login (OIDC)
             uses: azure/login@v2
             with:
               client-id: ${{ secrets.AZURE_CLIENT_ID }}
               tenant-id: ${{ secrets.AZURE_TENANT_ID }}
               subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
           - name: Get deploy token
             id: get-token
             run: |
               token=$(az staticwebapp secrets list \
                 --name "${{ env.SWA_NAME }}" \
                 --resource-group "${{ env.RESOURCE_GROUP }}" \
                 --query "properties.apiKey" -o tsv)
               if [ -z "${token}" ]; then
                 echo "::error::Failed to retrieve deploy token from SWA resource"
                 exit 1
               fi
               echo "::add-mask::${token}"
               echo "token=${token}" >> "$GITHUB_OUTPUT"
           - name: Close Pull Request
             uses: Azure/static-web-apps-deploy@v1
             with:
               azure_static_web_apps_api_token: ${{ steps.get-token.outputs.token }}
               action: "close"
     ```
   - **注意**: workflow のトリガー設定を以下のとおり確認・修正する：
      - `on.push.branches`: 少なくとも `main` を含めること。
      - Copilot が一時的に追加した作業ブランチ名（例: `copilot/...`）は、デプロイ成功確認後にトリガーから **削除** すること（AC チェック対象）。
      - `on.pull_request.branches`: 通常は `main` のままでよい。
   - **`workflow_dispatch` トリガーの追加**: `github-actions-cicd` Skill §2 に従い、`workflow_dispatch` トリガーを追加する。PR description に「Actions タブから手動実行してください」と記載すること。
5. `infra/azure/switch-swa-to-main.sh`（本番切替スクリプト）
   - Linux bash。PR マージ後に実行し、SWA の追跡ブランチを `main` に切り替える。
   - 冪等性: 現在のブランチが既に `main` の場合はスキップして正常終了する。
   - 実装要件:
     - スクリプト先頭に shebang と安全設定を追加する: `#!/usr/bin/env bash` と `set -euo pipefail` を必須とする。
     - `SWA_NAME` および `RESOURCE_GROUP` は環境変数から参照し（ハードコード禁止）、未設定または空の場合はエラーメッセージを出力して `exit 1` で即時終了する（例: `: "${SWA_NAME:?SWA_NAME is required}"` / `: "${RESOURCE_GROUP:?RESOURCE_GROUP is required}"`）。
     - `az staticwebapp show --name $SWA_NAME --resource-group $RESOURCE_GROUP --query repositoryBranch --output tsv` で現在の追跡ブランチを取得し、既に `main` なら `echo "Already on main, skipping"` でスキップ
     - `az staticwebapp update --name $SWA_NAME --resource-group $RESOURCE_GROUP --branch main` を実行
   - スクリプト冒頭に実行手順コメントを記載: `# PR マージ後に実行: bash infra/azure/switch-swa-to-main.sh`
   - `SWA_NAME`・`RESOURCE_GROUP` は環境変数から参照（ハードコード禁止）
6. `{WORK}screen-azure-deploy-work-status.md`
   - 進捗ログを追記（後述フォーマット）。
7. `{WORK}ac-verification.md`
   - AC 検証結果を記録（後述フォーマット）。
8. **API 接続経路の構成**（UI が API を呼ぶ場合 — `docs/catalog/service-catalog-matrix.md` を参照して判定）
   - `docs/catalog/service-catalog-matrix.md` に UI → API の依存がある場合、以下のいずれかを構成する：
     - **方式A: SWA Linked Backend**（推奨、Standard SKU 必須）: `az staticwebapp backends link` でバックエンド（Azure Functions）を連携。`staticwebapp.config.json` にプロキシルート不要。
     - **方式B: APIM 経由**: `API_BASE_URL` に APIM URL を設定。UICoding Agent が環境変数を参照するコードを生成済み。SWA アプリ設定 (`az staticwebapp appsettings set`) で値を注入。
     - **方式C: `staticwebapp.config.json` プロキシ**: `routes` に `/api/*` → バックエンド URL のルーティングを追加。SWA Free SKU で利用可能。
   - 選択した方式を `docs/catalog/service-catalog-matrix.md` と `{WORK}ac-verification.md` に記録する。
   - `staticwebapp.config.json` の `navigationFallback.exclude` に API パス（`/api/*` 等）を追加して除外する。

### デプロイ後スモークテスト（推奨）
デプロイ成功後、以下の最小検証を実施する（自動テストには混ぜない）：
1. `URL=$(az staticwebapp show --name $SWA_NAME --resource-group $RESOURCE_GROUP --query defaultHostname --output tsv) && curl -sf -o /dev/null -w "%{http_code}" "https://$URL"` で **HTTP 200** を確認する
2. トップページ（`/`）が正常に表示されること
3. 結果を `ac-verification.md` に記録する
4. 実行不可の場合は `⏳（手動確認待ち）` として上記手順を記録する

### スクリプト作成後の実行（必須）

**作成したシェルスクリプト（`.sh`）は、作成直後に必ず実行する。** スクリプトの作成のみで終了してはならない。

> **例外**: `infra/azure/switch-swa-to-main.sh` は **PR マージ後に人間が手動で実行**するスクリプトであり、エージェント実行中は実行しないこと。即時実行の対象は `infra/azure/create-azure-webui-resources.sh` のみである。

> **分割モード（Plan-Only）時はスキップする。** Skill task-dag-planning により、分割モードではスクリプト（`.sh`）の作成自体が禁止されているため、この実行手順も適用されない。

#### 実行順序と手順

> **事前確認（必須）**: スクリプトを実行する前に、AC-2 の「①コードレビュー（常に実施・実行前に完了）」を先に完了しておくこと。コードレビュー ❌ の場合はスクリプトを修正してから実行すること。

```bash
# GITHUB_PAT は不要。Azure リソース作成のみ実行する。
chmod +x infra/azure/create-azure-webui-resources.sh
bash infra/azure/create-azure-webui-resources.sh
```

- 成功判定: exit code が `0` であり、`az staticwebapp show` でリソースの存在が確認できること
- 失敗時: エラー内容を work-status に記録し、原因を修正して再実行（最大3回）。3回で解決しない場合は `⏳（手動実行待ち）` とする

#### 実行不可時の対応
エージェント実行環境で実行できない場合（Azure CLI 未ログイン / ネットワーク制約 / `az` コマンド未インストール / サブスクリプション権限不足 等）：
- 判定を `⏳（手動実行待ち）` とする
- 上記の実行コマンドをそのまま `ac-verification.md` に記録する（コピー&ペーストで即実行可能な形）
- work-status に `YYYY-MM-DD HH:MM (UTC): スクリプト実行不可（理由: ...）/ ⏳ 手動実行待ち / 次アクション: 手動で実行し AC-1〜AC-3 を検証` と記録する

#### Copilot push 後の Workflow 実行手順（PR description に記録）

`github-actions-cicd` Skill §2.3 の PR description テンプレートに従い、手動実行案内を記載すること。
加えて、SWA 固有の前提条件として以下を PR description に記録すること：

> 🚨 **前提条件（必須）**: Workflow を実行する前に、以下が完了していること：
> 1. `create-azure-webui-resources.sh` を実行済み（Azure リソース作成）
> 2. Azure Static Web Apps リソースが存在すること（`az staticwebapp show` で確認）
>
> ⛔ これらが未完了の状態で Workflow を実行すると、OIDC 方式では **デプロイはスキップされず失敗します**。Azure Static Web Apps リソースの事前作成（`create-azure-webui-resources.sh`）が必須の前提条件です。

#### 実行結果の記録
- 実行結果は work-status（進捗ログフォーマットに従う）と `ac-verification.md` の両方に記録する
- **セキュリティ注意**: 実行結果にサブスクリプションID・テナントID等が含まれる場合は `***` でマスクしてから記録する

#### PR description の手動操作案内（必須フォーマット）

手動操作が必要な場合、以下のフォーマットで **依存関係を明示して** PR description に記載すること：

> ## 🚨 マージ前に必要な手動操作（順序厳守）
>
> 以下の手順は **必ずこの順序で** 実行してください。
> ステップ N+1 はステップ N が完了していないと失敗します。
>
> ### ステップ 1: Azure リソース作成（⛔ 未実行だとステップ 2 が失敗します）
> ```bash
> # GITHUB_PAT は不要。Azure リソース作成のみ実行する。
> bash infra/azure/create-azure-webui-resources.sh
> ```
> **完了確認**: `az staticwebapp show --name {SWA_NAME} --resource-group {RESOURCE_GROUP}` でリソースが表示されること
>
> ### ステップ 2: ワークフロー実行（⚠️ ステップ 1 完了後に実行）
> PR の「Approve and run workflows」 または Actions タブ → 手動実行
>
> ### ステップ 3: マージ後: 本番ブランチ切替
> ```bash
> SWA_NAME="{SWA_NAME}" RESOURCE_GROUP="{RESOURCE_GROUP}" \
>   bash infra/azure/switch-swa-to-main.sh
> ```

- **順序制約の明記**: ステップ間の依存関係を `⛔ 未実行だとステップ N が失敗します` の形式で明示する
- **完了確認の追記**: 各ステップに完了を確認するコマンドまたは手順を記載する

### 本番切替ステップ（PR マージ後に実施）

`create-azure-webui-resources.sh` による作業ブランチからの初回デプロイが成功（AC-1・AC-6 が ✅ または ⏳）したら、本番切替手順を `ac-verification.md` と `docs/` に記録する：

1. **切替スクリプトの説明**: `switch-swa-to-main.sh` は PR マージ後（`main` ブランチに作業内容が取り込まれた後）に実行する。
2. **実行コマンド（記録用）**:
   ```bash
   # PR マージ後に実行すること
   # SWA_NAME と RESOURCE_GROUP は create-azure-webui-resources.sh 実行時に設定した値、または ac-verification.md の AC-1 エビデンスから確認する
   SWA_NAME="<az staticwebapp show で確認した name>" RESOURCE_GROUP="<リソースグループ名>" bash infra/azure/switch-swa-to-main.sh
   ```
3. **切替後の確認**: `az staticwebapp show` で追跡ブランチが `main` になっていることを確認する。

> **注意**: このステップはエージェント実行中ではなく、PR マージ後に人間が手動で実行する。`ac-verification.md` に上記コマンドをそのまま記録し `⏳（マージ後実施）` とすること。

### セキュリティ/運用（最小）
- 資格情報/トークン/個人情報を、コード・コミット・ログに含めない。
- Secrets の手動設定が必要なら、README か work-status に「手順のみ」短く記録（値は書かない）。
- **エビデンス記録時の注意**: `az` コマンド出力にサブスクリプションID・テナントID等が含まれる場合は `***` でマスクしてから記録する。

### 進捗ログ（追記フォーマット）
- `YYYY-MM-DD HH:MM (UTC): 実施内容 / 結果 / 次アクション`

### 大きい出力・空ファイル対策
- 大量生成・長文は `large-output-chunking` skill に従い分割する。
- 書き込み後にファイルの先頭数行/サイズを確認し、空なら分割して追記し直す。

# 受け入れ条件（AC）の検証と完了判定（必須）

> **実行タイミング**: Implementation 完了後に実施する。すべての AC が合格（✅ または ⏳）にならない限り、最終品質レビューには進まない。
>
> **分割モード時**: 本セクションはスキップする。最初の実装 Sub Issue の AC に本 AC 一覧を含めること。
>
> **§1 との関係**: 本セクションの AC 検証は、§1「最低1つの検証」を満たす手段として位置づける。

## 🔴 AC-1: Azure リソース存在確認（最重要）

**スクリプト実行後に Microsoft Azure に作成すべきリソースが作成されていること。**

これが本ジョブの最も重要な受け入れ条件である。他の AC がすべて ✅ でも、AC-1 が ❌ なら作業は未完了とする。

### 検証手順
```bash
az staticwebapp show \
  --name "{SWA_NAME}" \
  --resource-group "{RESOURCE_GROUP}" \
  --query "{name:name, resourceGroup:resourceGroup, region:location, sku:sku.name, defaultHostname:defaultHostname}" \
  --output table
```
リソースが存在し、`defaultHostname` が取得できることを確認する。

### 判定基準
- ✅: コマンドが正常に結果を返し、`defaultHostname` が取得できる
- ❌: コマンドが「リソース不存在」を示すエラーを返す
- ⏳: エージェント実行環境で Azure CLI が利用できない場合 → 検証コマンドを `ac-verification.md` に記録し、PR description に `⚠️ AC-1: 手動検証が必要` と明記する

## AC 一覧（AC-2 以降）

| # | 受け入れ条件 | 検証方法 |
|---|---|---|
| AC-2 | `infra/azure/create-azure-webui-resources.sh` が冪等に動作する | ①コードレビュー（`az staticwebapp show` による存在チェック分岐あり）②実行テスト（exit code 0）。不可なら ⏳ |
| AC-3 | GitHub Actions workflow が OIDC (`azure/login@v2`) + `Azure/static-web-apps-deploy@v1`（Microsoft 公式）を使用し、全ジョブに `environment: copilot` が指定されていること、deploy token を `az staticwebapp secrets list` で動的取得していること、`app_location: src/app/` が設定されており、`workflow_dispatch` トリガーと `id-token: write` 権限が含まれていること | ワークフロー YAML のコードレビュー |
| AC-4 | `docs/catalog/service-catalog-matrix.md` にデプロイ先 URL が記載 | ファイル内容確認（URL または取得手順の記載） |
| AC-5 | 秘密情報がコード・コミットに含まれていない | `grep -riE "(secret\|token\|password\|connection.?string)" --include="*.sh" --include="*.yml" --include="*.md"` を実行。ハードコードされた値がないこと（変数参照・プレースホルダーは可） |
| AC-6 | デプロイが成功する（OIDC 認証で自動実行） | `az staticwebapp show` でリソース存在確認 + workflow 実行ログで `Azure/static-web-apps-deploy` が成功していること。エージェント実行不可の場合は ⏳ |
| AC-7 | `infra/azure/switch-swa-to-main.sh` が存在し、`main` への切替が冪等に動作する | ①コードレビュー（既に `main` の場合のスキップロジックあり、`az staticwebapp update --branch main` あり）②スクリプトの内容確認 |

### AC-2 詳細検証手順

**① コードレビュー（常に実施・実行前に完了）**
- `#!/bin/bash` 等の shebang があること
- `set -euo pipefail` が含まれること
- `az` CLI の存在確認が含まれること
- `az staticwebapp show` による存在チェックがあること
- 存在チェック結果に基づく分岐ロジック（既存時はスキップ or 更新）があること
- `--source` フラグを**使用していない**こと（OIDC 方式の確認）
- `GITHUB_PAT` や `gh secret set` の呼び出しがないこと（不要）
- 確認結果を `ac-verification.md` の AC-2 行に記録する

**② 実行テスト（コードレビュー ✅ 後に実施・可能なら実施）**
```bash
chmod +x infra/azure/create-azure-webui-resources.sh
bash infra/azure/create-azure-webui-resources.sh
```
- 成功判定: exit code 0 かつ `az staticwebapp show` でリソース存在確認

## 共通検証ルール

`azure-ac-verification` Skill §4 に従う。エージェント環境で Azure CLI が利用可能なら実行して ✅ / ❌ を判定し、利用不可なら `⏳（手動実行待ち）` とする。

### AC 検証結果の記録先
`{WORK}ac-verification.md` に `azure-ac-verification` Skill §1 のテンプレートに従って記録する。

### 完了判定

`azure-ac-verification` Skill §2 の統一ステータス名（PASS / NEEDS-VERIFICATION / FAIL）に従う。

# 最終品質レビュー（Skill adversarial-review 準拠・3観点）

## 3つの異なる観点（Azure Static Web Apps デプロイの場合）
- **1回目：実装完全性・要件達成度**：全成果物（create スクリプト、switch-swa-to-main.sh、staticwebapp.config.json、workflow YAML、service-catalog、work-status、ac-verification）が揃っているか、AC がすべて ✅ / ⏳（条件付き）であるか、冪等性と安全なフォールバック処理が保証されているか、Bash スクリプトのシバン・`set -euo pipefail`・エラーハンドリングは適切か、**Workflow が `Azure/static-web-apps-deploy@v1` を使用し、全ジョブに `environment: copilot` が指定され、deploy token を `az staticwebapp secrets list` で動的取得し、`app_location: "src/app/"` が設定されているか**、`actions/checkout@v4` を使用しているか、`DEPLOY_BRANCH` が正しく設定されているか
- **2回目：ユーザー/利用者視点**：デプロイ/検証の手順が明確に理解できるか、⏳ の AC がある場合に手動検証手順が明確か、`AZURE_STATIC_WEB_APPS_API_TOKEN` や `GITHUB_PAT` の設定が不要であることが明記されているか、スクリプト実行不可時の手動実行手順がコピー&ペースト可能な形で記録されているか、本番切替（`switch-swa-to-main.sh`）の実行タイミングと手順が明確か
- **3回目：保守性・セキュリティ・再現性**：OIDC 用の Secrets (`AZURE_CLIENT_ID` 等) がスクリプト内にハードコードされておらず、環境変数・Secrets 参照のみであるか、エビデンス内のサブスクリプションID等がマスクされているか、ドキュメント整合性（plan/work-status/ac-verification）に問題がないか、新しい UI 追加時の変更容易性が確保されているか（別リポジトリでも再利用可能か）、再デプロイ・再現性の検証が可能か、`switch-swa-to-main.sh` の冪等性が保証されているか

## 出力方法
レビュー記録は `{WORK}` に保存（Skill work-artifacts-layout §4.1）。PR本文にも記載。最終版のみ成果物出力。

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D15-非機能-運用-監視-DR-仕様書.md` — 非機能・運用・監視・DR
- `knowledge/D20-セキュア設計-実装ガードレール.md` — セキュア設計・実装ガードレール
- `knowledge/D21-CI-CD-ビルド-リリース-供給網管理仕様書.md` — CI/CD・ビルド・リリース
