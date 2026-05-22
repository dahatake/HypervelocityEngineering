#!/usr/bin/env bash
set -euo pipefail
umask 077
set +x

# Usage: ./deploy.sh
# 前提条件:
# - Azure CLI がインストール済み
# - az login 済み
# - 対象サブスクリプションが az account set で選択済み

# ---------------------------------------------------------------------------
# ヘルパー関数
# ---------------------------------------------------------------------------

require_command() {
  local cmd_name="$1"
  if ! command -v "$cmd_name" >/dev/null 2>&1; then
    echo "[ERROR] required command not found: $cmd_name" >&2
    exit 1
  fi
}

require_az_login() {
  if ! az account show -o none 2>/dev/null; then
    echo "[ERROR] not logged in to Azure. Run 'az login' first." >&2
    exit 1
  fi
}

az_tsv() {
  az "$@" -o tsv | tr -d '\r'
}

require_env() {
  local var_name="$1"
  if [[ -z "${!var_name:-}" ]]; then
    echo "[ERROR] required environment variable is not set: $var_name" >&2
    exit 1
  fi
}

parse_repo_url() {
  local url="$1"
  local repo_path
  repo_path="${url#https://github.com/}"
  repo_path="${repo_path#http://github.com/}"
  repo_path="${repo_path#github.com/}"
  repo_path="${repo_path%.git}"
  repo_path="${repo_path%/}"
  OWNER="${repo_path%%/*}"
  REPO="${repo_path#*/}"
  if [[ -z "$OWNER" || -z "$REPO" || "$REPO" == "$OWNER" || "$REPO" == */* ]]; then
    echo "ERROR: REPO_URL の形式が不正です: $url" >&2
    exit 1
  fi
}

wait_for_principal_id() {
  local job_name="$1"
  local resource_group="$2"
  local max_seconds="$3"
  local interval_seconds="$4"
  local principal_id=""
  local attempt=1
  local max_attempts
  max_attempts=$(( max_seconds / interval_seconds ))
  while [[ $attempt -le $max_attempts ]]; do
    principal_id="$(az_tsv containerapp job show --name "$job_name" --resource-group "$resource_group" --query identity.principalId)"
    if [[ -n "$principal_id" ]]; then
      echo "$principal_id"
      return 0
    fi
    sleep "$interval_seconds"
    attempt=$(( attempt + 1 ))
  done
  echo "[WARN] Job の managed identity principalId を ${max_seconds}秒以内に取得できませんでした。" >&2
}

ensure_role_assignment() {
  local assignee_object_id="$1"
  local scope="$2"
  local role_id="$3"
  local err
  err="$(az role assignment create \
    --assignee-object-id "$assignee_object_id" \
    --assignee-principal-type ServicePrincipal \
    --scope "$scope" \
    --role "$role_id" \
    2>&1)" || {
    if echo "$err" | grep -q "RoleAssignmentExists"; then
      : # 既存割当は無視
    else
      echo "$err" >&2
      return 1
    fi
  }
}

resolve_current_principal_for_rbac() {
  local account_type
  local account_name
  local principal_id=""
  local principal_type=""

  account_type="$(az_tsv account show --query user.type)"
  account_name="$(az_tsv account show --query user.name)"

  if [[ -z "$account_type" || -z "$account_name" ]]; then
    echo "[ERROR] 現在の Azure ログイン主体を特定できませんでした。'az account show' の user.type / user.name を確認してください。" >&2
    return 1
  fi

  case "$account_type" in
    user)
      principal_id="$(az_tsv ad signed-in-user show --query id)"
      principal_type="User"
      ;;
    servicePrincipal)
      principal_id="$(az_tsv ad sp show --id "$account_name" --query id)"
      principal_type="ServicePrincipal"
      ;;
    *)
      echo "[ERROR] 未対応の Azure ログイン主体です: type=$account_type name=$account_name" >&2
      return 1
      ;;
  esac

  if [[ -z "$principal_id" ]]; then
    echo "[ERROR] RBAC 付与対象の object id を取得できませんでした: type=$account_type name=$account_name" >&2
    return 1
  fi

  printf '%s\t%s\n' "$principal_id" "$principal_type"
}

ensure_role_assignment_for_current_principal() {
  local scope="$1"
  local role_name="$2"
  local principal
  local principal_id
  local principal_type
  local err

  principal="$(resolve_current_principal_for_rbac)" || return 1
  principal_id="${principal%%$'\t'*}"
  principal_type="${principal#*$'\t'}"

  err="$(az role assignment create \
    --assignee-object-id "$principal_id" \
    --assignee-principal-type "$principal_type" \
    --scope "$scope" \
    --role "$role_name" \
    2>&1)" || {
    if echo "$err" | grep -q "RoleAssignmentExists"; then
      : # 既存割当は無視
    else
      echo "$err" >&2
      return 1
    fi
  }
}

set_keyvault_secret_with_retry() {
  local vault_name="$1"
  local secret_name="$2"
  local secret_value="$3"
  local max_attempts="$4"
  local interval_seconds="$5"
  local attempt=1
  local output

  while [[ $attempt -le $max_attempts ]]; do
    output="$(az_tsv keyvault secret set \
      --vault-name "$vault_name" \
      --name "$secret_name" \
      --value "$secret_value" \
      --query id 2>&1)" && {
      printf '%s' "$output"
      return 0
    }

    if echo "$output" | grep -q "ForbiddenByRbac\|setSecret/action\|Caller is not authorized"; then
      echo "[WARN] Key Vault RBAC 反映待ちのため secret set を再試行します (${attempt}/${max_attempts})" >&2
      sleep "$interval_seconds"
      attempt=$(( attempt + 1 ))
      continue
    fi

    echo "$output" >&2
    return 1
  done

  echo "[ERROR] Key Vault secret set failed after ${max_attempts} attempts. RBAC role propagation may be delayed." >&2
  return 1
}

# .env 形式の値エスケープ（" と \ をバックスラッシュエスケープ）
kv_escape() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '%s' "$value"
}

# 一時ファイル経由の原子的書き込み（umask 077 が先頭で設定済み）
atomic_write() {
  local target_path="$1"
  local content="$2"
  local tmp_path
  tmp_path="$(mktemp "${target_path}.XXXXXX")"
  printf '%s' "$content" > "$tmp_path"
  chmod 600 "$tmp_path"
  mv -f "$tmp_path" "$target_path"
}

# GitHub Actions Outputs にキー=値を書き込む（$GITHUB_OUTPUT が設定されているときのみ）
# 機微項目には is_secret=true を渡し、ログに ::add-mask:: を出力する
emit_github_output() {
  local key="$1"
  local value="$2"
  local is_secret="${3:-false}"
  if [[ -z "${GITHUB_OUTPUT:-}" ]]; then
    return 0
  fi
  if [[ ! -w "$GITHUB_OUTPUT" ]]; then
    echo "[WARN] emit_github_output: GITHUB_OUTPUT ('${GITHUB_OUTPUT}') is not writable; skipping '${key}'." >&2
    return 0
  fi
  if [[ "$is_secret" == "true" && -n "$value" ]]; then
    # GitHub Actions のログ上で値をマスクする
    echo "::add-mask::${value}"
  fi
  # 値に改行が含まれないことを前提とする（本スクリプトの出力対象は ID / URI / 名前のみ）
  # 万一改行が混入した場合は出力を安全にスキップする
  if [[ "$value" == *$'\n'* ]]; then
    echo "[WARN] emit_github_output: skipping '${key}' because value contains a newline." >&2
    return 0
  fi
  printf '%s=%s\n' "$key" "$value" >> "$GITHUB_OUTPUT"
}

# ---------------------------------------------------------------------------
# Step 0: 事前検証
# ---------------------------------------------------------------------------

require_command az
require_command jq
require_az_login

# サブスクリプション情報（Phase 2 で追加）
SUBSCRIPTION_ID="$(az_tsv account show --query id)"
TENANT_ID="$(az_tsv account show --query tenantId)"

# ---------------------------------------------------------------------------

# 環境変数で指定する必須・オプション変数（デフォルト値をここで設定）
# 必須: GITHUB_PAT, REPO_URL
# オプション: RESOURCE_GROUP, LOCATION, ACR_NAME, CONTAINERAPPS_ENV, KV_NAME

RESOURCE_GROUP="${RESOURCE_GROUP:-github-runner-rg}"
LOCATION="${LOCATION:-japaneast}"
ACR_NAME="${ACR_NAME:-githubrunnersacr$(date +%s | tail -c 7)}"
CONTAINERAPPS_ENV="${CONTAINERAPPS_ENV:-github-runner-aca-env}"
KV_NAME="${KV_NAME:-github-runner-kv-$(date +%s | tail -c 7)}"
REPO_URL="${REPO_URL:-}"
RUNNER_LABELS="${RUNNER_LABELS:-self-hosted,linux,x64,aca}"
JOB_NAME="${JOB_NAME:-gha-runner-job}"
IMAGE_NAME="${IMAGE_NAME:-gha-runner:latest}"
ACR_PULL_ROLE_ID="7f951dda-4ed3-4680-a7ca-43fe172d538d"
KV_SECRETS_OFFICER_ROLE_NAME="Key Vault Secrets Officer"

# 必須変数チェック
for required in GITHUB_PAT REPO_URL RESOURCE_GROUP LOCATION ACR_NAME CONTAINERAPPS_ENV KV_NAME; do
  value="${!required}"
  if [[ -z "$value" ]]; then
    echo "ERROR: 必須環境変数 '${required}' が未設定です。export ${required}='value' で設定後、再度実行してください。" >&2
    exit 1
  fi
done

# GitHub PAT が見かけ上のプレースホルダではないか確認
if [[ "$GITHUB_PAT" == "<YOUR_"* ]]; then
  echo "ERROR: GITHUB_PAT が設定されていません。GitHub Personal Access Token を export GITHUB_PAT='...' で指定してください。" >&2
  exit 1
fi

if [[ "$REPO_URL" == "<YOUR_"* ]]; then
  echo "ERROR: REPO_URL が設定されていません。export REPO_URL='https://github.com/owner/repo' で指定してください。" >&2
  exit 1
fi

echo "Step 1: リソースグループを作成します"
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION"
RESOURCE_GROUP_ID="$(az_tsv group show --name "$RESOURCE_GROUP" --query id)"

echo "Step 2: Azure Container Registry を作成します"
if az acr show --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" >/dev/null 2>&1; then
  az acr update \
    --resource-group "$RESOURCE_GROUP" \
    --name "$ACR_NAME" \
    --admin-enabled false
else
  az acr create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$ACR_NAME" \
    --sku Basic \
    --admin-enabled false
fi
ACR_ID="$(az_tsv acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query id)"
ACR_SERVER="$(az_tsv acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query loginServer)"

echo "Step 3: Azure Container Apps Environment を作成します"
az containerapp env create \
  --name "$CONTAINERAPPS_ENV" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION"
CONTAINERAPPS_ENV_ID="$(az_tsv containerapp env show --name "$CONTAINERAPPS_ENV" --resource-group "$RESOURCE_GROUP" --query id)"
# defaultDomain プロパティが存在しない az/拡張バージョンの可能性に備え、取得失敗時は空文字列にフォールバックする
CONTAINERAPPS_ENV_DEFAULT_DOMAIN="$(az_tsv containerapp env show --name "$CONTAINERAPPS_ENV" --resource-group "$RESOURCE_GROUP" --query properties.defaultDomain 2>/dev/null || echo '')"

echo "Step 4: Key Vault を作成し GitHub PAT を格納します"
az keyvault create \
  --name "$KV_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION"
KV_ID="$(az_tsv keyvault show --name "$KV_NAME" --query id)"
KV_URI="$(az_tsv keyvault show --name "$KV_NAME" --query properties.vaultUri)"

ensure_role_assignment_for_current_principal "$KV_ID" "$KV_SECRETS_OFFICER_ROLE_NAME"
GITHUB_PAT_SECRET_ID="$(set_keyvault_secret_with_retry "$KV_NAME" "github-pat" "$GITHUB_PAT" 12 10)"
unset GITHUB_PAT
GITHUB_PAT_SECRET_URI_NO_VERSION="${KV_URI%/}/secrets/github-pat"

echo "Step 5: Runner イメージをビルドして ACR にプッシュします"
az acr build \
  --registry "$ACR_NAME" \
  --image "$IMAGE_NAME" \
  --file tools/runner/Dockerfile \
  .
IMAGE_FULL="${ACR_SERVER}/${IMAGE_NAME}"
# az acr repository show の digest プロパティはバージョンによって取得できない場合があるため、空文字列フォールバック
IMAGE_DIGEST="$(az_tsv acr repository show --name "$ACR_NAME" --image "$IMAGE_NAME" --query digest 2>/dev/null || echo '')"

echo "Step 5.5: ACR pull 用 User-Assigned Managed Identity を作成し、RBAC ロール割り当てを事前完了します"
# Job 作成時にイメージ pull が試みられるため、先に identity と RBAC を用意する
JOB_IDENTITY_NAME="${JOB_NAME}-identity"
if az identity show --name "$JOB_IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
  echo "既存の User-Assigned Identity を再利用します: $JOB_IDENTITY_NAME"
else
  echo "User-Assigned Identity を作成します: $JOB_IDENTITY_NAME"
  az identity create \
    --name "$JOB_IDENTITY_NAME" \
    --resource-group "$RESOURCE_GROUP"
fi
JOB_IDENTITY_ID="$(az_tsv identity show --name "$JOB_IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" --query id)"
JOB_IDENTITY_PRINCIPAL_ID="$(az_tsv identity show --name "$JOB_IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" --query principalId)"
echo "RBAC ロール割り当てを完了させます（最大 12 回リトライ、10秒間隔）..."
ensure_role_assignment "$JOB_IDENTITY_PRINCIPAL_ID" "$ACR_ID" "$ACR_PULL_ROLE_ID"

echo "Step 6: Container Apps Job（KEDA github-runner scaler）を作成します"
# 機密情報のため、ログ出力（set -x など）を有効化しないでください。
GITHUB_PAT_VALUE="$(az_tsv keyvault secret show --vault-name "$KV_NAME" --name github-pat --query value)"

echo "[INFO] parsing REPO_URL"
parse_repo_url "$REPO_URL"
REPO_OWNER="$OWNER"
REPO_NAME="$REPO"

if az containerapp job show --name "$JOB_NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
  echo "既存 Job を削除して再作成します"
  az containerapp job delete \
    --name "$JOB_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --yes
fi

# RUNNER_LABELS から KEDA reserved labels (self-hosted, linux, x64) を除いた追加ラベルを算出
# KEDA github-runner scaler は reservedLabels = [self-hosted, linux, x64] を自動付与するため、
# それ以外のカスタムラベル（例: aca）のみを labels= に渡す必要がある
RUNNER_EXTRA_LABELS="$(echo "$RUNNER_LABELS" \
  | tr ',' '\n' \
  | awk 'NF && tolower($0) != "self-hosted" && tolower($0) != "linux" && tolower($0) != "x64"' \
  | paste -sd ',' -)"
echo "[INFO] KEDA scaler 用追加ラベル: '${RUNNER_EXTRA_LABELS}' (元: '${RUNNER_LABELS}')"

SCALE_METADATA=(
  "githubAPIURL=https://api.github.com"
  "owner=${REPO_OWNER}"
  "repos=${REPO_NAME}"
  "runnerScope=repo"
  "targetWorkflowQueueLength=1"
)
if [[ -n "$RUNNER_EXTRA_LABELS" ]]; then
  SCALE_METADATA+=("labels=${RUNNER_EXTRA_LABELS}")
fi

az containerapp job create \
  --name "$JOB_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$CONTAINERAPPS_ENV" \
  --trigger-type Event \
  --min-executions 0 \
  --max-executions 5 \
  --polling-interval 30 \
  --replica-timeout 3600 \
  --replica-retry-limit 0 \
  --replica-completion-count 1 \
  --parallelism 1 \
  --image "${IMAGE_FULL}" \
  --cpu 2.0 \
  --memory 4Gi \
  --mi-user-assigned "$JOB_IDENTITY_ID" \
  --registry-server "$ACR_SERVER" \
  --registry-identity "$JOB_IDENTITY_ID" \
  --secrets "github-pat=${GITHUB_PAT_VALUE}" \
  --env-vars \
    "GITHUB_PAT=secretref:github-pat" \
    "REPO_URL=${REPO_URL}" \
    "RUNNER_LABELS=${RUNNER_LABELS}" \
  --scale-rule-name github-runner \
  --scale-rule-type github-runner \
  --scale-rule-metadata "${SCALE_METADATA[@]}" \
  --scale-rule-auth "personalAccessToken=github-pat"

JOB_ID="$(az_tsv containerapp job show --name "$JOB_NAME" --resource-group "$RESOURCE_GROUP" --query id)"
JOB_LOCATION="$(az_tsv containerapp job show --name "$JOB_NAME" --resource-group "$RESOURCE_GROUP" --query location)"
JOB_PROVISIONING_STATE="$(az_tsv containerapp job show --name "$JOB_NAME" --resource-group "$RESOURCE_GROUP" --query properties.provisioningState)"

# User-Assigned Identity の principal id を使用（Job の system identity ではなく）
JOB_PRINCIPAL_ID="$JOB_IDENTITY_PRINCIPAL_ID"

unset GITHUB_PAT_VALUE

# ---------------------------------------------------------------------------
# Phase 3: 成果物出力
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- .env ファイル生成 ---
env_content="# Generated by tools/runner/deploy.sh — do not edit manually.
SUBSCRIPTION_ID=\"$(kv_escape "$SUBSCRIPTION_ID")\"
TENANT_ID=\"$(kv_escape "$TENANT_ID")\"
RESOURCE_GROUP=\"$(kv_escape "$RESOURCE_GROUP")\"
RESOURCE_GROUP_ID=\"$(kv_escape "$RESOURCE_GROUP_ID")\"
LOCATION=\"$(kv_escape "$LOCATION")\"
ACR_NAME=\"$(kv_escape "$ACR_NAME")\"
ACR_ID=\"$(kv_escape "$ACR_ID")\"
ACR_SERVER=\"$(kv_escape "$ACR_SERVER")\"
CONTAINERAPPS_ENV=\"$(kv_escape "$CONTAINERAPPS_ENV")\"
CONTAINERAPPS_ENV_ID=\"$(kv_escape "$CONTAINERAPPS_ENV_ID")\"
CONTAINERAPPS_ENV_DEFAULT_DOMAIN=\"$(kv_escape "$CONTAINERAPPS_ENV_DEFAULT_DOMAIN")\"
KV_NAME=\"$(kv_escape "$KV_NAME")\"
KV_ID=\"$(kv_escape "$KV_ID")\"
KV_URI=\"$(kv_escape "$KV_URI")\"
GITHUB_PAT_SECRET_ID=\"$(kv_escape "$GITHUB_PAT_SECRET_ID")\"
GITHUB_PAT_SECRET_URI_NO_VERSION=\"$(kv_escape "$GITHUB_PAT_SECRET_URI_NO_VERSION")\"
IMAGE_NAME=\"$(kv_escape "$IMAGE_NAME")\"
IMAGE_FULL=\"$(kv_escape "$IMAGE_FULL")\"
IMAGE_DIGEST=\"$(kv_escape "$IMAGE_DIGEST")\"
JOB_NAME=\"$(kv_escape "$JOB_NAME")\"
JOB_IDENTITY_NAME=\"$(kv_escape "$JOB_IDENTITY_NAME")\"
JOB_IDENTITY_ID=\"$(kv_escape "$JOB_IDENTITY_ID")\"
JOB_IDENTITY_PRINCIPAL_ID=\"$(kv_escape "$JOB_IDENTITY_PRINCIPAL_ID")\"
JOB_ID=\"$(kv_escape "$JOB_ID")\"
JOB_LOCATION=\"$(kv_escape "$JOB_LOCATION")\"
JOB_PROVISIONING_STATE=\"$(kv_escape "$JOB_PROVISIONING_STATE")\"
JOB_PRINCIPAL_ID=\"$(kv_escape "$JOB_PRINCIPAL_ID")\""
atomic_write "${SCRIPT_DIR}/.runner-deploy.env" "$env_content"

# --- JSON ファイル生成 ---
json_content="$(jq -n \
  --arg subscription_id           "$SUBSCRIPTION_ID" \
  --arg tenant_id                 "$TENANT_ID" \
  --arg rg_name                   "$RESOURCE_GROUP" \
  --arg rg_id                     "$RESOURCE_GROUP_ID" \
  --arg location                  "$LOCATION" \
  --arg acr_name                  "$ACR_NAME" \
  --arg acr_id                    "$ACR_ID" \
  --arg acr_server                "$ACR_SERVER" \
  --arg env_name                  "$CONTAINERAPPS_ENV" \
  --arg env_id                    "$CONTAINERAPPS_ENV_ID" \
  --arg env_domain                "$CONTAINERAPPS_ENV_DEFAULT_DOMAIN" \
  --arg kv_name                   "$KV_NAME" \
  --arg kv_id                     "$KV_ID" \
  --arg kv_uri                    "$KV_URI" \
  --arg pat_secret_id             "$GITHUB_PAT_SECRET_ID" \
  --arg pat_secret_uri            "$GITHUB_PAT_SECRET_URI_NO_VERSION" \
  --arg image_name                "$IMAGE_NAME" \
  --arg image_full                "$IMAGE_FULL" \
  --arg image_digest              "$IMAGE_DIGEST" \
  --arg job_name                  "$JOB_NAME" \
  --arg job_identity_name         "$JOB_IDENTITY_NAME" \
  --arg job_identity_id           "$JOB_IDENTITY_ID" \
  --arg job_identity_principal_id "$JOB_IDENTITY_PRINCIPAL_ID" \
  --arg job_id                    "$JOB_ID" \
  --arg job_location              "$JOB_LOCATION" \
  --arg job_state                 "$JOB_PROVISIONING_STATE" \
  --arg job_principal_id          "$JOB_PRINCIPAL_ID" \
  '{
    subscription:     { id: $subscription_id, tenant_id: $tenant_id },
    resource_group:   { name: $rg_name, id: $rg_id, location: $location },
    acr:              { name: $acr_name, id: $acr_id, login_server: $acr_server },
    containerapps_env:{ name: $env_name, id: $env_id, default_domain: $env_domain },
    key_vault:        { name: $kv_name, id: $kv_id, uri: $kv_uri,
                        github_pat_secret_id: $pat_secret_id,
                        github_pat_secret_uri: $pat_secret_uri },
    image:            { name: $image_name, full: $image_full, digest: $image_digest },
    job:              { name: $job_name, id: $job_id, location: $job_location,
                        provisioning_state: $job_state, principal_id: $job_principal_id },
    job_identity:     { name: $job_identity_name, id: $job_identity_id,
                        principal_id: $job_identity_principal_id },
    mode:             { use_kv_reference: false, auto_name: false }
  }')"
atomic_write "${SCRIPT_DIR}/.runner-deploy.json" "$json_content"

# --- GitHub Actions Outputs 出力 ---
emit_github_output "SUBSCRIPTION_ID"                  "$SUBSCRIPTION_ID"
emit_github_output "TENANT_ID"                        "$TENANT_ID"
emit_github_output "RESOURCE_GROUP"                   "$RESOURCE_GROUP"
emit_github_output "RESOURCE_GROUP_ID"                "$RESOURCE_GROUP_ID"
emit_github_output "LOCATION"                         "$LOCATION"
emit_github_output "ACR_NAME"                         "$ACR_NAME"
emit_github_output "ACR_ID"                           "$ACR_ID"
emit_github_output "ACR_SERVER"                       "$ACR_SERVER"
emit_github_output "CONTAINERAPPS_ENV"                "$CONTAINERAPPS_ENV"
emit_github_output "CONTAINERAPPS_ENV_ID"             "$CONTAINERAPPS_ENV_ID"
emit_github_output "CONTAINERAPPS_ENV_DEFAULT_DOMAIN" "$CONTAINERAPPS_ENV_DEFAULT_DOMAIN"
emit_github_output "KV_NAME"                          "$KV_NAME"
emit_github_output "KV_ID"                            "$KV_ID"
emit_github_output "KV_URI"                           "$KV_URI"
emit_github_output "GITHUB_PAT_SECRET_ID"             "$GITHUB_PAT_SECRET_ID"             "true"
emit_github_output "GITHUB_PAT_SECRET_URI_NO_VERSION" "$GITHUB_PAT_SECRET_URI_NO_VERSION" "true"
emit_github_output "IMAGE_NAME"                       "$IMAGE_NAME"
emit_github_output "IMAGE_FULL"                       "$IMAGE_FULL"
emit_github_output "IMAGE_DIGEST"                     "$IMAGE_DIGEST"
emit_github_output "JOB_NAME"                         "$JOB_NAME"
emit_github_output "JOB_IDENTITY_NAME"                "$JOB_IDENTITY_NAME"
emit_github_output "JOB_IDENTITY_ID"                  "$JOB_IDENTITY_ID"
emit_github_output "JOB_IDENTITY_PRINCIPAL_ID"        "$JOB_IDENTITY_PRINCIPAL_ID"
emit_github_output "JOB_ID"                           "$JOB_ID"
emit_github_output "JOB_LOCATION"                     "$JOB_LOCATION"
emit_github_output "JOB_PROVISIONING_STATE"           "$JOB_PROVISIONING_STATE"
emit_github_output "JOB_PRINCIPAL_ID"                 "$JOB_PRINCIPAL_ID"

# --- 完了ログ ---
echo "[INFO] Phase 3: deploy outputs written:"
echo "  ${SCRIPT_DIR}/.runner-deploy.env"
echo "  ${SCRIPT_DIR}/.runner-deploy.json"
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "  GITHUB_OUTPUT entries written (sensitive values masked)"
fi

echo "デプロイが完了しました。"
