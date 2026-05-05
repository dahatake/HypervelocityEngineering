#!/usr/bin/env bash
# github-api.sh — GitHub REST API の curl ベースユーティリティ関数
#
# gh CLI ではなく curl + GH_TOKEN を直接使用するワークフロー向け共通ライブラリ。
# （gh CLI ベースの実装は gh-api.sh を参照）
#
# 前提環境変数:
#   GH_TOKEN — GitHub API 認証トークン（必須）
#
# 使い方:
#   source "${GITHUB_WORKSPACE}/.github/scripts/bash/lib/github-api.sh"

# NOTE: No `set -euo pipefail` — this file is sourced as a library and must
# not alter the caller's shell options.

# Guard against double-sourcing
if [[ -n "${_GITHUB_API_SH_LOADED:-}" ]]; then
  return 0 2>/dev/null || true
fi
readonly _GITHUB_API_SH_LOADED=1

# ---------------------------------------------------------------------------
# api_call METHOD URL [DATA]
#
# リトライ付き GitHub REST API 呼び出し（curl ベース）。
#
# Args:
#   METHOD — HTTP メソッド（GET / POST / PATCH / DELETE）
#   URL    — https://api.github.com/... の完全 URL
#   DATA   — 省略可。JSON リクエストボディ（文字列）
#
# Returns:
#   成功時: JSON レスポンスを stdout に出力し exit 0
#   失敗時: エラーメッセージを stderr に出力し exit 1
# ---------------------------------------------------------------------------
api_call() {
  local method="$1"; shift
  local url="$1"; shift
  local data="${1:-}"
  local max_retry=5
  local wait=1
  local http_code response body

  for i in $(seq 1 "${max_retry}"); do
    if [[ -n "${data}" ]]; then
      response=$(curl -s -w "\n%{http_code}" \
        -X "${method}" \
        -H "Authorization: Bearer ${GH_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        -H "Content-Type: application/json" \
        "${url}" \
        -d "${data}")
    else
      response=$(curl -s -w "\n%{http_code}" \
        -X "${method}" \
        -H "Authorization: Bearer ${GH_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "${url}")
    fi
    http_code=$(echo "${response}" | tail -1)
    body=$(echo "${response}" | head -n -1)
    if [[ "${http_code}" =~ ^2 ]]; then
      echo "${body}"
      return 0
    fi
    echo "API エラー: HTTP ${http_code}、${wait}秒後にリトライ (${i}/${max_retry})" >&2
    sleep "${wait}"
    wait=$((wait * 2))
  done
  echo "API 呼び出し失敗: ${method} ${url}" >&2
  return 1
}
