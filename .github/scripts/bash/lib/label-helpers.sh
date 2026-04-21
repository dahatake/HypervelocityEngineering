#!/usr/bin/env bash
# label-helpers.sh — ラベル操作の共通関数
#
# 依存環境変数:
#   GH_TOKEN — GitHub API トークン
#   REPO     — owner/repo 形式

create_label() {
  local name="$1" color="$2" desc="${3:-}"
  local http_code
  http_code=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST \
    -H "Authorization: Bearer ${GH_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${REPO}/labels" \
    -d "{\"name\":\"${name}\",\"color\":\"${color}\",\"description\":\"${desc}\"}")
  case "${http_code}" in
    201) echo "ラベル作成: ${name}" ;;
    422) echo "ラベル既存（スキップ）: ${name}" ;;
    *)   echo "ラベル作成エラー: ${name} HTTP ${http_code}" ;;
  esac
  sleep 1
}
