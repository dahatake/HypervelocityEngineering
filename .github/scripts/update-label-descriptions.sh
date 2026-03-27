#!/usr/bin/env bash
# 既存ラベルの description を更新するスクリプト
# 使い方: GITHUB_TOKEN=xxx REPO=owner/repo bash .github/scripts/update-label-descriptions.sh
set -euo pipefail

update_label() {
  local name="$1"
  local new_desc="$2"
  local encoded_name
  encoded_name=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$name")
  if curl -sf -X PATCH \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${REPO}/labels/${encoded_name}" \
    -d "$(python3 -c 'import json, sys; print(json.dumps({"description": sys.argv[1]}))' "$new_desc")"; then
    echo "Updated: ${name}"
  else
    echo "Failed or not found: ${name}"
    return 1
  fi
}

update_label "auto-batch-design" "run full batch design workflow"
update_label "auto-batch-dev" "run full batch dev workflow (Azure resource, coding, deploy, review)"
update_label "auto-iot-design" "run full IoT / physical AI design document generation workflow"
update_label "auto-app-selection" "run app selection workflow (usecase to app list and architecture recommendation)"
update_label "auto-app-design" "run app design workflow (microservice architecture design document generation)"
update_label "auto-app-dev-microservice" "run full microservice app development workflow on Azure"
