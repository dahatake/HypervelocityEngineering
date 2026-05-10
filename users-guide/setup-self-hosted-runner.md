# Self-hosted Runner セットアップ手順書（Azure Container Apps）

← [README](../README.md) | ← [getting-started.md](./getting-started.md)

この手順書は、`tools/runner/README.md` と `tools/runner/SETUP.md` を統合した単一ドキュメントです。  
以下の順番で実行すれば、GitHub Actions Self-hosted Runner を Azure Container Apps Jobs にデプロイして検証できます。

> **HVE Cloud Agent Orchestrator における位置づけ（省略可能）**: この手順は**オプション**です。GitHub-hosted runner（`ubuntu-latest` 等）を使う場合はスキップして [getting-started.md の Step.5（ラベル設定）](./getting-started.md#step5-ラベル設定) に進んでください。Self-hosted runner が必要なのは、組織のセキュリティ要件・閉域ネットワーク・固定 IP・専用ツール利用などの理由で自前の実行環境でワークフローを動かしたい場合です。設定タイミングは **認証・認可設定（Step.4）の後、Setup Labels 実行（Step.5）の前** が推奨です。なお、Self-hosted runner 側に設定した runner label（デフォルト: `self-hosted,linux,x64,aca`）は、Issue Template や workflow の `runs-on:` に指定する label と**一致している必要があります**。ラベルが不一致の場合、ジョブが `Waiting for a runner...` のまま進まなくなります。
>
> **⚠️ 認証トークンに関する注意**: この手順で必要なトークンは、getting-started.md Step.4 の `COPILOT_PAT`（Copilot 自動アサイン用 Fine-grained PAT）とは**別物**です。Self-hosted runner のデプロイには **GitHub Personal Access Token (classic)** が必要です（スコープ: `repo` + `admin:repo_hook`）。詳細は [Step 2: GitHub PAT を発行](#step-2-github-pat-を発行) を参照してください。
>
> **対象読者**: Azure Container Apps で Self-hosted Runner を構築・運用するリポジトリ管理者  
> **前提**: Azure サブスクリプション権限、GitHub リポジトリアクセス権、`tools/runner/` を実行できるローカル環境があること  
> **次のステップ**: セットアップ後は [getting-started.md の Step.5（ラベル設定）](./getting-started.md#step5-ラベル設定) へ戻り、Setup Labels を実行してください。運用時の詳細は [troubleshooting.md の Self-hosted runner（オプション）](./troubleshooting.md#7-self-hosted-runnerオプション) と `tools/runner/` 配下ドキュメントを参照してください。

## 目次
- [1. 概要](#1-概要)
- [2. 構成ファイル](#2-構成ファイル)
- [3. 前提条件](#3-前提条件)
- [4. 事前インストール](#4-事前インストール)
- [5. セットアップ手順（実行順）](#5-セットアップ手順実行順)
- [6. 動作確認](#6-動作確認)
- [7. ワークフロー移行](#7-ワークフロー移行)
- [8. トラブルシューティング](#8-トラブルシューティング)
- [9. セキュリティ運用](#9-セキュリティ運用)
- [10. 運用・保守](#10-運用保守)
- [11. 制約事項・注意点](#11-制約事項注意点)
- [12. 参考リンク](#12-参考リンク)

## 1. 概要

本構成は、GitHub Actions の Self-hosted Runner を Azure Container Apps Jobs 上でエフェメラル実行します。KEDA の `github-runner` スケーラーがキューを監視し、必要時のみ Runner を起動します。

```text
GitHub Actions Job Queue
        |
        v
KEDA github-runner scaler (Container Apps Job)
        |
        v
Azure Container Apps Job (Event Trigger)
        |
        v
Runner Container
  - GitHub Actions Runner (ephemeral)
  - Python 3.12 / pip / pytest
  - Azure CLI / jq / shellcheck / git / curl
        |
        v
1 ジョブ完了後に終了（不要時は 0 実行）
```

- GitHub-hosted Runner: GitHub 管理の実行基盤
- Self-hosted (ACA Job): 利用者管理の実行基盤（必要ツールを事前同梱可能）
- `--min-executions 0` によりアイドル時ゼロスケール可能

## 2. 構成ファイル

| ファイル | 説明 |
|---------|------|
| `tools/runner/deploy.sh` | Azure リソース作成と Runner デプロイを行うメインスクリプト |
| `tools/runner/Dockerfile` | Runner 実行環境を定義 |
| `tools/runner/entrypoint.sh` | コンテナ起動時の初期化処理 |
| `users-guide/setup-self-hosted-runner.md` | 本手順書（統合版） |

## 3. 前提条件

### 3.1 Azure
- Azure サブスクリプションが有効
- リソース作成権限（Contributor 以上推奨）
- Key Vault にシークレットを書き込める RBAC 権限（例: `Key Vault Secrets Officer` 以上）
- 対象リージョン（例: `japaneast`）

### 3.2 GitHub
- 対象リポジトリが存在
- Personal Access Token (classic) を発行可能
- PAT スコープ: `repo` と `admin:repo_hook`

### 3.3 ローカル
- `bash` 4.0+
- Azure CLI v2.50+
- `jq` 1.6+
- Docker（ローカルでイメージ検証する場合のみ）

## 4. 事前インストール

### 4.1 Azure CLI

Windows (Chocolatey / Scoop)
```powershell
choco install azure-cli
# または
scoop install azure-cli
```

macOS
```bash
brew install azure-cli
```

Linux (Ubuntu/Debian)
```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

確認
```bash
az --version
```

### 4.2 jq

Windows
```powershell
choco install jq
```

macOS
```bash
brew install jq
```

Linux (Ubuntu/Debian)
```bash
sudo apt-get update && sudo apt-get install -y jq
```

確認
```bash
jq --version
```

## 5. セットアップ手順（実行順）

### Step 1: Azure にログイン

```bash
az login
az account show --output table
```

サブスクリプションを切り替える場合:
```bash
az account set --subscription <subscription-id-or-name>
```

### Step 2: GitHub PAT を発行

1. GitHub: `Settings` > `Developer settings` > `Personal access tokens` > `Tokens (classic)`
2. `Generate new token (classic)` を選択
3. `repo` + `admin:repo_hook` を付与
4. トークンをコピー（有効期限は短め推奨）

### Step 3: 必須環境変数を設定

```bash
export GITHUB_PAT="github_pat_xxxxxxxxxxxxxxxxxxxx"
export REPO_URL="https://github.com/<owner>/<repo>"
```

### Step 4: 任意環境変数を設定（必要時）

```bash
export RESOURCE_GROUP="your-resource-group-name"
export LOCATION="japaneast"
export ACR_NAME="yourregistryname"
export CONTAINERAPPS_ENV="your-aca-env"
export KV_NAME="your-keyvault-name"
export RUNNER_LABELS="self-hosted,linux,x64,aca"
export JOB_NAME="gha-runner-job"
export IMAGE_NAME="gha-runner:latest"
```

### Step 5: デプロイ実行

```bash
cd <このリポジトリのルート>
./tools/runner/deploy.sh
```

実行例（インライン指定）:
```bash
export GITHUB_PAT="github_pat_xxxxx..." && \
export REPO_URL="https://github.com/dahatake/RoyalytyService2ndGen" && \
export RESOURCE_GROUP="my-runner-rg" && \
export LOCATION="eastus" && \
./tools/runner/deploy.sh
```

> `deploy.sh` を再実行すると既存の Container Apps Job は削除・再作成されます。実行中ジョブがないタイミングで実行してください。

## 6. 動作確認

`Self-hosted Runner が動作している` と判断するには、少なくとも 1 回は実際にジョブを実行して成功させる必要があります。  
リソースの存在確認のみ（6.1）では「デプロイ済み」の確認に留まり、「実行可能」の確認にはなりません。  
したがって、一度もテスト実行をしていない状態では `Self-hosted Runner が動作している` とは言えません。

### 6.1 Azure リソース確認

```bash
az group list --output table
az containerapp env list --resource-group $RESOURCE_GROUP --output table
az containerapp job list --resource-group $RESOURCE_GROUP --output table
az keyvault list --output table
```

確認ポイント:
- Resource Group が作成されている
- ACR に `gha-runner:latest` が存在し、Admin user が無効
- Container Apps Environment が作成済み
- Key Vault に `github-pat` シークレットが存在
- Container Apps Job（既定: `gha-runner-job`）が存在

### 6.2 テスト実行の準備

事前に次を確認します。

1. GitHub の対象リポジトリに [`.github/workflows/self-hosted-runner-smoke-test.yml`](../.github/workflows/self-hosted-runner-smoke-test.yml) が存在する
2. GitHub の `Settings` > `Actions` > `Runners` に対象 Runner が表示される
3. Runner labels が `self-hosted`, `linux`, `x64`, `aca` を含む
4. Azure 側で Container Apps Job が作成済みである

GitHub Actions 画面から実行する詳細手順:

1. GitHub で対象リポジトリを開く
2. `Actions` タブを開く
3. 左側のワークフロー一覧から `self-hosted-runner-smoke-test` を選択する
4. 右上の `Run workflow` を押す
5. 実行対象ブランチが `main` であることを確認して `Run workflow` を実行する
6. ジョブ `smoke` が `Queued` になったことを確認する
7. 数十秒から数分以内に `In progress` へ遷移することを確認する
8. ジョブ詳細ログを開き、`Runner info` と `Toolchain check` が成功していることを確認する

ログで最低限確認する項目:

- `runs-on: [self-hosted, linux, x64, aca]` の Runner が選ばれている
- `python3 --version` が成功している
- `az version | head -n 1` が成功している
- `jq --version` が成功している

### 6.3 テストワークフロー実行（必須）

実行手順:
1. GitHub の対象リポジトリで `Actions` タブを開く
2. `self-hosted-runner-smoke-test` を選択
3. `Run workflow` を実行
4. ジョブが `Queued` → `In progress` → `Success` になることを確認
5. ログで `runs-on: [self-hosted, linux, x64, aca]` の Runner が選択され、`python3` / `az` / `jq` のバージョン出力が成功していることを確認

CLI で確認する場合（任意）:
```bash
az containerapp job execution list \
  --name $JOB_NAME \
  --resource-group $RESOURCE_GROUP \
  --output table
```

確認ポイント:
- ワークフローが Self-hosted Runner で正常完了する
- ジョブ実行時に Container Apps Job の実行履歴が増える
- 完了後、不要な常時実行インスタンスが残らない（ゼロスケール）

### 6.4 GitHub 側確認
1. GitHub > Settings > Actions > Runners を開く
2. Self-hosted Runner の状態を確認
3. テストワークフローを実行
4. ジョブ実行時のスケールアウト、完了後のスケールインを確認

## 7. ワークフロー移行

`runs-on` を段階的に切り替えます。

変更前:
```yaml
runs-on: ubuntu-latest
```

変更後:
```yaml
runs-on: [self-hosted, linux, x64, aca]
```

- まず 1 本のワークフロー（例: `.github/workflows/test-hve-python.yml`）で検証
- 問題なければ対象を順次移行
- Python 3.12 をイメージ同梱しているため `actions/setup-python` は必須ではありません

## 8. トラブルシューティング

### ジョブが「Waiting for a runner to pick up this job...」のまま進まない

- 原因の最有力候補: KEDA `github-runner` scaler の `labels` メタデータに、`self-hosted/linux/x64` 以外のカスタムラベル（例: `aca`）が含まれていない
- 確認:
```bash
az containerapp job execution list --name $JOB_NAME --resource-group $RESOURCE_GROUP --output table
# → 0 件なら KEDA がスケールしていない（本問題に該当する可能性が高い）

az containerapp job show --name $JOB_NAME --resource-group $RESOURCE_GROUP \
  --query "properties.configuration.eventTriggerConfig.scale.rules[*].metadata"
# → 返却 JSON に "labels": "aca" 等が含まれていなければ本問題に該当
```
- 対処: `tools/runner/deploy.sh` を最新化して再実行
- 補足: KEDA の `reservedLabels` は `self-hosted, linux, x64` の 3 つで自動付与されるため、`labels=` には**それ以外**を指定する。本リポジトリでは `RUNNER_LABELS` 環境変数から自動算出される（`RUNNER_LABELS` を変更するだけで KEDA scaler 側にも自動反映される）

### `Runner version vX.Y.Z is deprecated and cannot receive messages.` エラーで全 execution が即終了する

#### 症状
- `az containerapp job execution list` で executions は次々に Succeeded として記録されている
- にもかかわらず GitHub Actions のジョブは `Waiting for a runner to pick up this job...` のまま進まない
- 各 execution の実行時間が極端に短い（30 秒〜1 分程度）

#### 原因
Dockerfile の `ARG RUNNER_VERSION` で固定したバージョンが GitHub によって deprecate され、メッセージ（ジョブ割当）の受信が拒否されている。`entrypoint.sh` が `--disableupdate` を指定していると自動更新で救済されない。

Runner は登録には成功するため `√ Runner successfully added` までログに出るが、`Listening for Jobs` 開始直後に（以下、実ログ原文ママ）
```
An error occured: Runner version vX.Y.Z is deprecated and cannot receive messages.
Runner listener exit with terminated error, stop the service, no retry needed.
```
が出て即座に exit する。コンテナは exit 0 で終わるため ACA 側は Succeeded と表示し、KEDA は次の execution を起動する無限ループに入る。

#### 確認方法

Log Analytics から直接ログを確認する（`az containerapp job logs show` は preview のため不安定）:

```bash
WORKSPACE_ID=$(az containerapp env show \
  -n $CONTAINERAPPS_ENV -g $RESOURCE_GROUP \
  --query properties.appLogsConfiguration.logAnalyticsConfiguration.customerId -o tsv)

az monitor log-analytics query \
  --workspace "$WORKSPACE_ID" \
  --analytics-query "ContainerAppConsoleLogs_CL
    | where ContainerGroupName_s startswith '${JOB_NAME}-'
    | where TimeGenerated > ago(30m)
    | where Log_s contains 'deprecated' or Log_s contains 'Listening for Jobs'
    | project TimeGenerated, ContainerGroupName_s, Log_s
    | order by TimeGenerated desc" \
  -o table
```

`deprecated and cannot receive messages` を含む行があれば本問題に該当。

#### 対処
1. https://github.com/actions/runner/releases で最新安定版を確認
2. `tools/runner/Dockerfile` の `ARG RUNNER_VERSION=` を最新版に更新
3. `tools/runner/entrypoint.sh` の `./config.sh` 呼び出しから `--disableupdate` を削除（自動更新で deprecated を回避できるようにする）
4. `./tools/runner/deploy.sh` を再実行（イメージ再ビルド + Job 再作成）

> 目安として 3 か月に 1 回は `RUNNER_VERSION` を最新化することを推奨します。

### `[ERROR] required command not found: jq`
- 原因: `jq` 未インストール
- 対処:
```bash
sudo apt-get install -y jq
jq --version
```

### `[ERROR] not logged in to Azure`
- 原因: Azure CLI 未ログイン
- 対処:
```bash
az login
az account show
```

### `ERROR: GITHUB_PAT が未設定です`
- 原因: `GITHUB_PAT` 未設定
- 対処:
```bash
export GITHUB_PAT="github_pat_xxxxxxxxxxxx"
./tools/runner/deploy.sh
```

### `ResourceNotFound: ... does not exist`
- 原因: リソースグループ不存在、またはサブスクリプション/権限不一致
- 対処:
```bash
az group list --output table
az account show
```

### `Deployment failed with status Conflict`
- 原因: 同名リソースが既存
- 対処:
```bash
az acr show --name $ACR_NAME --resource-group $RESOURCE_GROUP
export ACR_NAME="youracr$(date +%s)"
./tools/runner/deploy.sh
```

### `ForbiddenByRbac` / `setSecret/action`（Step 4 で停止）
- 原因: Key Vault が RBAC モードで作成され、実行主体にシークレット書き込み権限が不足
- 対処:
```bash
CURRENT_USER_OBJECT_ID=$(az ad signed-in-user show --query id -o tsv | tr -d '\r')
az role assignment create \
  --assignee-object-id "$CURRENT_USER_OBJECT_ID" \
  --assignee-principal-type User \
  --scope "$(az keyvault show --name $KV_NAME --query id -o tsv | tr -d '\r')" \
  --role "Key Vault Secrets Officer"
```

> RBAC 割り当て直後は反映に数十秒かかる場合があります。少し待ってから再実行してください。

### Runner が登録されない
- PAT スコープ（`repo` / `admin:repo_hook`）を確認
- `REPO_URL` 形式（`https://github.com/{owner}/{repo}`）を確認
- Container Apps Job から GitHub API への疎通を確認

### ジョブがタイムアウトする
- `tools/runner/deploy.sh` の `--replica-timeout` を調整

### イメージビルドが失敗する
- ACR 名の命名制約・重複を確認
- ACR へのアクセス権限を確認

## 9. セキュリティ運用

### 9.1 PAT の取り扱い
1. PAT をスクリプトに埋め込まない（環境変数で渡す）
2. 有効期限は短め（例: 30〜90日）
3. 不要になった PAT は GitHub 上で削除
4. 必要に応じて履歴と環境変数をクリア

```bash
history -c
export GITHUB_PAT=""
```

### 9.2 Azure 側アクセス制御
- Managed Identity + RBAC で最小権限化
- Key Vault へのアクセス権を必要最小限に設定

例:
```bash
az role assignment create \
  --assignee <your-user-id> \
  --role "Contributor" \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP"

az keyvault set-policy \
  --name $KV_NAME \
  --resource-group $RESOURCE_GROUP \
  --secret-permissions get list \
  --object-id <your-object-id>
```

## 10. 運用・保守

### 10.1 PAT ローテーション
1. 新しい PAT を発行
2. Key Vault の `github-pat` を更新
3. `./tools/runner/deploy.sh` を再実行

### 10.2 Runner イメージ更新

> **重要**: GitHub は古い Runner バージョンを定期的に deprecate し、メッセージ受信を停止します。
> deprecate されると Runner は登録に成功するもののジョブを 1 件も拾えなくなります（§8 トラブルシューティング参照）。
> **目安として 3 か月に 1 回は最新化を実施してください。**

1. https://github.com/actions/runner/releases で最新安定版バージョンを確認
2. `tools/runner/Dockerfile` の `ARG RUNNER_VERSION` を更新
3. `./tools/runner/deploy.sh` を再実行
4. 新規ジョブで新イメージ利用を確認（Log Analytics で `Current runner version: 'X.Y.Z'` を確認）

### 10.3 スケーリング調整
- `--max-executions`
- `--polling-interval`
- `targetWorkflowQueueLength`

### 10.4 削除

Container Apps Job のみ削除:
```bash
az containerapp job delete \
  --name $JOB_NAME \
  --resource-group $RESOURCE_GROUP \
  --yes
```

関連リソース一括削除:
```bash
az group delete --name $RESOURCE_GROUP --yes
```

## 11. 制約事項・注意点

- Docker-in-Docker 非対応
- Docker ビルドが必要なワークフローは GitHub-hosted Runner か VM ベース Self-hosted Runner へ切り分け検討
- パブリックリポジトリでの利用は非推奨
- Azure OIDC Federated Credential の Subject 調整が必要な場合がある

## 12. 参考リンク

- [Azure CLI 公式ドキュメント](https://learn.microsoft.com/cli/azure/)
- [Azure Container Apps](https://learn.microsoft.com/azure/container-apps/)
- [Azure Cosmos DB Emulator](https://learn.microsoft.com/azure/cosmos-db/emulator)
- [GitHub Actions Self-Hosted Runners](https://docs.github.com/en/actions/hosting-your-own-runners)
- [KEDA GitHub Runner Scaler](https://keda.sh/docs/scalers/github-runner/)
- [GitHub Actions Runner Releases](https://github.com/actions/runner/releases)
