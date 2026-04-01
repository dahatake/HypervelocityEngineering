---
name: Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps
description: Azure Static Web Apps へのWebデプロイ（Azure/static-web-apps-deploy@v1 使用）と、GitHub Actionsによる継続的デリバリー（CD）構築を、リポジトリ標準（AGENTS.md / skills）に従って実施する。AC 検証による完了判定を含む。
tools: ["*"]
---
> **WORK**: `work/Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps/Issue-<識別子>/`

## 0) 共通ルール
- **AGENTS.md** と **`.github/copilot-instructions.md`** を最優先で遵守する。本ファイルは固有ルールのみを記載する。

## Skills 参照
- **`azure-cli-deploy-scripts`**: Azure CLI スクリプトの共通仕様（prep/create/verify 3点セット・冪等性パターン・CLI 利用不可時フォールバック）を参照する。
- **`github-actions-cicd`**: GitHub Actions CI/CD の共通仕様（OIDC 認証・`workflow_dispatch` トリガー・Copilot push 制約対応・PR description 手動実行案内）を参照する。
- **`azure-region-policy`**: Azure リージョン優先順位ポリシー（§2 SWA 例外: East Asia → Japan West → Southeast Asia）を参照する。
- **`azure-ac-verification`**: AC 検証フレームワークの共通仕様（§1 `ac-verification.md` テンプレート・§2 PASS/NEEDS-VERIFICATION/FAIL 完了判定基準・§3 Azure リソース存在確認パターン・§4 Azure CLI 利用不可時フォールバック）を参照する。
- **`.github/skills/azure-static-web-apps/SKILL.md`** を技術リファレンスとして参照する。
  - SWA CLI のコマンド詳細・フラグ・トラブルシューティングは SKILL.md を正とする。
  - ただし、本 Agent のジョブ定義（デプロイ方式・Secret 名・成果物仕様等）と SKILL.md が矛盾する場合は、本 Agent の記述を優先する（AGENTS.md §4.2 に準拠）。

- `harness-verification-loop`：コード変更の5段階検証パイプライン（AGENTS.md §10.1）
- `harness-safety-guard`：破壊的操作の事前検知（AGENTS.md §10.2）
- `harness-error-recovery`：エラー発生時の3要素出力（AGENTS.md §10.4）
## CLI ツール使い分けの原則
- **リソース管理（作成/更新/確認/削除）**: `az CLI`（`az staticwebapp create/show` 等）を使用する。
  - `az staticwebapp create --source` で **リソース作成 + GitHub リポジトリ連携 + workflow 自動生成 + Secret 自動設定** を1コマンドで実行する。
- **CI/CD デプロイ（GitHub Actions）**: **`Azure/static-web-apps-deploy@v1`** 公式 Action を使用する。
- **ローカル開発**: SWA CLI (`swa start`) を使用する（SKILL.md 参照）。

## Non-goals（明示）
- Azure以外のデプロイ先（App Service / AKS 等）への移行はしない（要求がない限り）。
- **SWA CLI (`swa deploy`) を CI/CD パイプライン（GitHub Actions）で使用しない**。SWA CLI はローカル開発用途に限定する。
- Secret値の生成・出力・コミットはしない。
- `swa start`（ローカル開発サーバー）の詳細設定は本ジョブのスコープ外。

# Inputs（変数）
作業開始時点で、次が未確定なら **1つだけ** 質問する（捏造禁止）。
- リソースグループ名: `{RESOURCE_GROUP}`

以下は質問不要（スクリプト内で導出・既定値を使用）：
- アプリ名: `{SWA_NAME}`（`{RESOURCE_GROUP}` から命名規則に基づき導出する。ルール: 全て小文字英数字とハイフンのみ（`[a-z0-9-]`）、最大 40 文字。`{RESOURCE_GROUP}` を小文字化し、非 `[a-z0-9-]` 文字はハイフンに置換したうえで、先頭に `swa-` 接頭辞、末尾に `-web` サフィックスを付与し、長すぎる場合は末尾側から削って 40 文字以内に収める。同一サブスクリプション内で既存 SWA と衝突する場合、または `{RESOURCE_GROUP}` が未定義/無効で導出できない場合は、ユーザーにアプリ名を追加で質問して明示的に確定する）
- リポジトリ URL: `{REPO_URL}`（`git remote get-url origin` で自動導出する。導出できない場合は追加で質問する）
- デプロイブランチ: 環境変数 `$DEPLOY_BRANCH`（省略時: `git rev-parse --abbrev-ref HEAD` で自動検出。PR マージ後に `switch-swa-to-main.sh` を実行して `main` に切替）
- `app_location`: `app`（固定）
- `api_location`: 空（Azure Functions で別途デプロイ済み）
- `output_location`: 空（ビルド不要の静的 HTML）

既定（明示してよい仮定）
- リージョン優先: `azure-region-policy` Skill §2 SWA 例外に従う
- SKU: Free

参照ファイル（存在すれば読む）:
- `docs/app-list.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全体処理）
- `docs/service-catalog.md`

## APP-ID スコープ
- Issue body または メタコメント `<!-- app-id: XXX -->` から対象 APP-ID を取得する
- `docs/app-list.md` が存在する場合はこれを参照し、対象 APP-ID に属する画面を特定する（APP × 画面 = 1:1）
- デプロイ対象の SWA は対象 APP-ID の画面を含む `src/app/` を対象とする
- APP-ID が指定されていない場合は全体を対象とする（後方互換）
- `docs/app-list.md` が存在しない場合は APP-ID によるスコープ絞り込みは行わず、全体を対象とする（後方互換）

# Workflow（必ずこの順）
## 1) Planner（必須）
- `AGENTS.md` のルールに従い、実装前に `{WORK}plan.md` を作る。
- plan には最低限：**AC（本ファイルの AC 一覧をそのまま使用）** / 変更候補パス / 検証 / DAG / 見積（分）/ 分割判定 を書く。
- **分割モード（Plan-Only）時は AC 検証セクションをスキップする。** 最初の実装 Sub Issue に AC 検証を含めること。

## 2) Onboarding（必要なときだけ）
- 入口や構成が不明なら `{WORK}onboarding.md` を作る（repo-onboarding-fast skill を使う）。

## 3) Implementation（分割モードでないときだけ）
### 成果物（このジョブの対象）
1. `infra/azure/create-azure-webui-resources.sh`
   - Linux bash。冪等（`azure-cli-deploy-scripts` Skill §2 冪等性パターン準拠 — 既存時はスキップ or 更新）。
   - `az staticwebapp create --source` で以下を1コマンドで実行：
     - リソース作成
     - GitHub リポジトリ連携（`--source https://github.com/{OWNER}/{REPO}`）
     - workflow 自動生成
     - Secret 自動設定
   - スクリプト冒頭で `DEPLOY_BRANCH` を設定する（`DEPLOY_BRANCH` 未設定時は以下の順で安全にブランチ名を解決する）:
     ```bash
     if [ -z "${DEPLOY_BRANCH:-}" ]; then
       if [ -n "${GITHUB_HEAD_REF:-}" ]; then
         # PR などで head ブランチ名が与えられている場合
         DEPLOY_BRANCH="$GITHUB_HEAD_REF"
       elif [ -n "${GITHUB_REF:-}" ]; then
         # refs/heads/main → main のように変換
         DEPLOY_BRANCH="${GITHUB_REF#refs/heads/}"
       else
         # ローカル / その他 CI 環境向けのフォールバック
         current_branch="$(git branch --show-current 2>/dev/null || true)"  # git 2.22+ / detached HEAD では空文字列
         if [ -n "$current_branch" ] && [ "$current_branch" != "HEAD" ]; then
           DEPLOY_BRANCH="$current_branch"
         else
           rev_parse_branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
           if [ -n "$rev_parse_branch" ] && [ "$rev_parse_branch" != "HEAD" ]; then
             DEPLOY_BRANCH="$rev_parse_branch"
           else
             echo "ERROR: DEPLOY_BRANCH を自動検出できませんでした。環境変数 DEPLOY_BRANCH を明示的に指定してください。" >&2
             exit 1
           fi
         fi
       fi
     fi
     ```
   - パラメータ:
     - `--branch $DEPLOY_BRANCH`
     - `--token $GITHUB_PAT`（GitHub PAT を環境変数から参照。値はスクリプトに書かない）
     - `--app-location "app"`
     - `--api-location ""`（API は Azure Functions で別途デプロイ済み）
     - `--output-location ""`（ビルド不要の静的 HTML）
     - `--sku Free`
   - 冪等性: `az staticwebapp show` で存在チェック → 既存時はスキップ or 更新
   - スクリプト冒頭で `az` CLI の存在確認を行う（prep.sh は廃止）
   - 対象リソースグループが存在するか確認し、存在しない場合は冪等に作成する（`azure-cli-deploy-scripts` Skill §1.2 および `azure-region-policy` Skill §2 SWA 例外に準拠）
   - **注意**: `--token` の値（`$GITHUB_PAT`）は GitHub PAT 用の環境変数経由で渡す。GitHub Actions の自動生成トークン（`GITHUB_TOKEN`）と混同せず、スクリプト内にハードコードしない。
2. `app/staticwebapp.config.json`
   - SWA ルーティング設定（`navigationFallback` 等）。
3. `docs/service-catalog.md`
   - 作成したWebアプリURLを追記（取得できない場合は取得手順を追記）。
4. Azure が自動生成した workflow YAML のカスタマイズ（`.github/workflows/azure-static-web-apps-*.yml`）
   - `az staticwebapp create --source` で自動生成される YAML を前提とする。
   - 以下のカスタマイズを加える：
     - `skip_app_build: true` の追加（`app/` はビルド不要の静的 HTML）
     - `app_location` が `app` であることの確認
     - `actions/checkout` のバージョンを `@v4` に更新
   - workflow は `Azure/static-web-apps-deploy@v1` を使用していることを確認する。
   - **注意**: workflow のトリガー設定を以下のとおり確認・修正する：
      - `on.push.branches`: 少なくとも `$DEPLOY_BRANCH` の実際の値（例: `copilot/deploy-azure-static-web-apps`）を含めること。作業ブランチへの push でデプロイが実行されるようにするため。自動生成 YAML が `branches: [main]` のみの場合は作業ブランチ名を追加する（例: `branches: [main, copilot/deploy-azure-static-web-apps]`）。
      - `on.pull_request.branches`: 「マージ先（ベース）ブランチ」のフィルタであり、通常は `main` のままでよい。作業ブランチ名を追加しても PR の実行条件は変わらないため追加不要。
    - **`workflow_dispatch` トリガーの追加**: `github-actions-cicd` Skill §2 に従い、`workflow_dispatch` トリガーを追加する。
      - 追加する YAML（`$DEPLOY_BRANCH` は実際の作業ブランチ名に置き換えること。例: `copilot/deploy-azure-static-web-apps`）:
        ```yaml
        on:
          push:
            branches: [main, copilot/deploy-azure-static-web-apps]  # $DEPLOY_BRANCH を実際の値に置換
          pull_request:
            types: [opened, synchronize, reopened, closed]
            branches: [main]
          workflow_dispatch:     # ← 追加
        ```
      - PR description に「Approve and run workflows ボタンを使用するか、
        Actions タブから手動実行してください」と記載すること
    - **Secret 未設定時のフェールセーフ（必須）**:
      - `Build And Deploy` ステップに `if:` 条件を追加し、`AZURE_STATIC_WEB_APPS_API_TOKEN` が未設定の場合はデプロイをスキップする
      - ジョブレベルの `env:` に以下を追加:
        ```yaml
        env:
          HAS_DEPLOY_TOKEN: ${{ secrets.AZURE_STATIC_WEB_APPS_API_TOKEN != '' }}
        ```
      - `Build And Deploy` ステップを以下のように修正:
        ```yaml
        - name: Build And Deploy
          id: builddeploy
          if: env.HAS_DEPLOY_TOKEN == 'true'
          uses: Azure/static-web-apps-deploy@v1
          with:
            azure_static_web_apps_api_token: ${{ secrets.AZURE_STATIC_WEB_APPS_API_TOKEN }}
            # ...（既存パラメータ）
        - name: Skip Deploy (token not configured)
          if: env.HAS_DEPLOY_TOKEN != 'true'
          run: |
            echo "::warning::AZURE_STATIC_WEB_APPS_API_TOKEN is not set. Skipping deployment."
            echo "Run 'bash infra/azure/create-azure-webui-resources.sh' first to create the Azure resource and set the secret."
        ```
      - **理由**: Azure リソース作成（Secret 自動設定）とワークフローの初回実行はどちらもユーザーの手動操作であるため、実行順序の保証ができない。Secret 未設定時に明示的な警告メッセージでスキップすることで、エラーではなく「次に何をすべきか」を案内する。
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

### デプロイ後スモークテスト（推奨）
デプロイ成功後、以下の最小検証を実施する（自動テストには混ぜない）：
1. `URL=$(az staticwebapp show --name $SWA_NAME --resource-group $RESOURCE_GROUP --query defaultHostname --output tsv) && curl -sf -o /dev/null -w "%{http_code}" "https://$URL"` で **HTTP 200** を確認する
2. トップページ（`/`）が正常に表示されること
3. 結果を `ac-verification.md` に記録する
4. 実行不可の場合は `⏳（手動確認待ち）` として上記手順を記録する

### スクリプト作成後の実行（必須）

**作成したシェルスクリプト（`.sh`）は、作成直後に必ず実行する。** スクリプトの作成のみで終了してはならない。

> **例外**: `infra/azure/switch-swa-to-main.sh` は **PR マージ後に人間が手動で実行**するスクリプトであり、エージェント実行中は実行しないこと。即時実行の対象は `infra/azure/create-azure-webui-resources.sh` のみである。

> **分割モード（Plan-Only）時はスキップする。** AGENTS.md §2.3 により、分割モードではスクリプト（`.sh`）の作成自体が禁止されているため、この実行手順も適用されない。

#### 実行順序と手順

> **事前確認（必須）**: スクリプトを実行する前に、AC-2 の「①コードレビュー（常に実施・実行前に完了）」を先に完了しておくこと。コードレビュー ❌ の場合はスクリプトを修正してから実行すること。

```bash
# GITHUB_PAT 環境変数に GitHub PAT をセットしてから実行すること
chmod +x infra/azure/create-azure-webui-resources.sh
bash infra/azure/create-azure-webui-resources.sh
```

- 成功判定: exit code が `0` であり、`az staticwebapp show` でリソースの存在が確認できること
- 失敗時: エラー内容を work-status に記録し、原因を修正して再実行（最大3回）。3回で解決しない場合は `⏳（手動実行待ち）` とする

#### 実行不可時の対応
エージェント実行環境で実行できない場合（Azure CLI 未ログイン / ネットワーク制約 / `az` コマンド未インストール / サブスクリプション権限不足 / `GITHUB_PAT` 未設定 等）：
- 判定を `⏳（手動実行待ち）` とする
- 上記の実行コマンドをそのまま `ac-verification.md` に記録する（コピー&ペーストで即実行可能な形）
- work-status に `YYYY-MM-DD HH:MM (UTC): スクリプト実行不可（理由: ...）/ ⏳ 手動実行待ち / 次アクション: 手動で実行し AC-1〜AC-3 を検証` と記録する

#### Copilot push 後の Workflow 実行手順（PR description に記録）

`github-actions-cicd` Skill §2.3 の PR description テンプレートに従い、手動実行案内を記載すること。
加えて、SWA 固有の前提条件として以下を PR description に記録すること：

> 🚨 **前提条件（必須）**: Workflow を実行する前に、以下が完了していること：
> 1. `create-azure-webui-resources.sh` を手動実行済み
> 2. Azure Static Web Apps リソースが作成されている
> 3. `AZURE_STATIC_WEB_APPS_API_TOKEN` が GitHub Secrets に自動設定されている
>
> ⛔ これらが未完了の状態で Workflow を実行すると、デプロイは `::warning::` メッセージとともにスキップされます（フェールセーフ）。Azure リソース作成後に再実行してください。

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
> export GITHUB_PAT="<repo+workflow スコープの PAT>"
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
- `GITHUB_PAT` の値（GitHub PAT: `repo` + `workflow` スコープ必須）はスクリプト内にハードコードせず、環境変数（`$GITHUB_PAT`）経由で渡す。GitHub Actions の自動生成トークン（`GITHUB_TOKEN`）とは別物であることに注意する。
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
> **AGENTS.md §1 との関係**: 本セクションの AC 検証は、AGENTS.md §1「最低1つの検証」を満たす手段として位置づける。

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
| AC-3 | GitHub Actions workflow が `Azure/static-web-apps-deploy@v1` を使用し `app_location: "app"` が設定されており、`workflow_dispatch` トリガーが含まれている | workflow YAML の内容確認（`grep` 等）: `grep -r "static-web-apps-deploy" .github/workflows/` + `grep -r "workflow_dispatch" .github/workflows/` |
| AC-4 | `docs/service-catalog.md` にデプロイ先 URL が記載 | ファイル内容確認（URL または取得手順の記載） |
| AC-5 | 秘密情報がコード・コミットに含まれていない | `grep -riE "(secret\|token\|password\|connection.?string)" --include="*.sh" --include="*.yml" --include="*.md"` を実行。ハードコードされた値がないこと（変数参照・プレースホルダーは可） |
| AC-6 | 作業ブランチ（`$DEPLOY_BRANCH`）からのデプロイが成功する（Secret 自動設定を含む） | `az staticwebapp show` でリソース存在確認 + workflow ログで `deployment_token` エラーがないこと。エージェント実行不可の場合は ⏳ |
| AC-7 | `infra/azure/switch-swa-to-main.sh` が存在し、`main` への切替が冪等に動作する | ①コードレビュー（既に `main` の場合のスキップロジックあり、`az staticwebapp update --branch main` あり）②スクリプトの内容確認 |

### AC-2 詳細検証手順

**① コードレビュー（常に実施・実行前に完了）**
- `#!/bin/bash` 等の shebang があること
- `set -euo pipefail` が含まれること
- `az` CLI の存在確認が含まれること
- `az staticwebapp show` による存在チェックがあること
- 存在チェック結果に基づく分岐ロジック（既存時はスキップ or 更新）があること
- `--token "$GITHUB_PAT"` で環境変数参照していること（`$GITHUB_PAT` は GitHub PAT; GitHub Actions 自動生成 `GITHUB_TOKEN` と混同がないこと。値のハードコードがないこと）
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

# 最終品質レビュー（AGENTS.md §7準拠・3観点）

## 3つの異なる観点（Azure Static Web Apps デプロイの場合）
- **1回目：実装完全性・要件達成度**：全成果物（create スクリプト、switch-swa-to-main.sh、staticwebapp.config.json、workflow YAML、service-catalog、work-status、ac-verification）が揃っているか、AC がすべて ✅ / ⏳（条件付き）であるか、冪等性と安全なフォールバック処理が保証されているか、Bash スクリプトのシバン・`set -euo pipefail`・エラーハンドリングは適切か、**Workflow が `Azure/static-web-apps-deploy@v1` を使用し `app_location: "app"` / `skip_app_build: true` が設定されているか**、`actions/checkout@v4` を使用しているか、`DEPLOY_BRANCH` が正しく設定されているか
- **2回目：ユーザー/利用者視点**：デプロイ/検証の手順が明確に理解できるか、⏳ の AC がある場合に手動検証手順が明確か、Secrets（`AZURE_STATIC_WEB_APPS_API_TOKEN`）の取得・設定手順が明確で安全か、自動生成 workflow への `skip_app_build: true` 追加手順が明確か、スクリプト実行不可時の手動実行手順がコピー&ペースト可能な形で記録されているか、本番切替（`switch-swa-to-main.sh`）の実行タイミングと手順が明確か
- **3回目：保守性・セキュリティ・再現性**：`GITHUB_PAT`（PAT）がスクリプト内にハードコードされておらず、GitHub Actions 自動生成 `GITHUB_TOKEN` と混同されていないか、エビデンス内のサブスクリプションID等がマスクされているか、ドキュメント整合性（plan/work-status/ac-verification）に問題がないか、新しい UI 追加時の変更容易性が確保されているか、再デプロイ・再現性の検証が可能か、`switch-swa-to-main.sh` の冪等性が保証されているか

## 出力方法
レビュー記録は `{WORK}` に保存（§4.1準拠）。PR本文にも記載。最終版のみ成果物出力。
