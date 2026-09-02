#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_PAT:?GITHUB_PAT is required}"
: "${REPO_URL:?REPO_URL is required}"

RUNNER_NAME="${RUNNER_NAME:-aca-runner-$(hostname)}"
RUNNER_LABELS="${RUNNER_LABELS:-self-hosted,linux,x64,aca}"
RUNNER_CONFIGURED=false
RUNNER_REMOVED=false

extract_owner_repo() {
  local raw url_path owner repo
  raw="$1"

  url_path="$raw"
  url_path="${url_path#https://github.com/}"
  url_path="${url_path#http://github.com/}"
  url_path="${url_path#github.com/}"
  url_path="${url_path%.git}"
  url_path="${url_path%/}"

  owner="${url_path%%/*}"
  repo="${url_path#*/}"

  if [[ -z "$owner" || -z "$repo" || "$repo" == "$owner" || "$repo" == */* ]]; then
    echo "Invalid REPO_URL format: $raw" >&2
    exit 1
  fi

  printf '%s %s\n' "$owner" "$repo"
}

read -r REPO_OWNER REPO_NAME < <(extract_owner_repo "$REPO_URL")

REG_TOKEN="$(curl -fsSL -X POST \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/actions/runners/registration-token" \
  | jq -r '.token')"

if [[ -z "$REG_TOKEN" || "$REG_TOKEN" == "null" ]]; then
  echo "Failed to get runner registration token." >&2
  exit 1
fi

cleanup() {
  if [[ "$RUNNER_REMOVED" == "true" ]]; then
    return 0
  fi
  RUNNER_REMOVED=true

  if [[ "$RUNNER_CONFIGURED" != "true" ]]; then
    echo "[entrypoint] runner is not configured. skip remove."
    return 0
  fi

  echo "[entrypoint] removing runner..."
  local remove_token
  remove_token="$(curl -fsSL -X POST \
    -H "Authorization: token ${GITHUB_PAT}" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/actions/runners/remove-token" \
    | jq -r '.token')"

  if [[ -n "$remove_token" && "$remove_token" != "null" ]]; then
    # config.sh remove は --unattended オプションを受け付けないため指定しない
    ./config.sh remove --token "$remove_token" || true
  else
    echo "[entrypoint] remove token の取得に失敗したため、Runner 削除をスキップします。" >&2
  fi
}

trap cleanup EXIT SIGTERM SIGINT

# --disableupdate は付けない:
# 付けると Runner が deprecated 化された際に自動更新されず、
# "Runner version is deprecated and cannot receive messages." エラーで全滅する。
# エフェメラル実行のため、起動時の自動更新コストは許容する。
./config.sh \
  --unattended \
  --url "$REPO_URL" \
  --token "$REG_TOKEN" \
  --name "$RUNNER_NAME" \
  --labels "$RUNNER_LABELS" \
  --ephemeral
RUNNER_CONFIGURED=true

./run.sh
