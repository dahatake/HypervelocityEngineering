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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LABELS_FILE="${REPO_ROOT}/.github/labels.json"

if [ ! -f "$LABELS_FILE" ]; then
  echo "Error: labels.json not found at ${LABELS_FILE}"
  exit 1
fi

LABEL_COUNT=$(jq '. | length' "$LABELS_FILE")
echo "Updating descriptions for ${LABEL_COUNT} labels from ${LABELS_FILE} ..."

for i in $(seq 0 $((LABEL_COUNT - 1))); do
  NAME=$(jq -r ".[$i].name" "$LABELS_FILE")
  DESCRIPTION=$(jq -r ".[$i].description" "$LABELS_FILE")
  update_label "$NAME" "$DESCRIPTION"
  sleep 1
done
