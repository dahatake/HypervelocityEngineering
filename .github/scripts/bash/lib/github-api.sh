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

# ---------------------------------------------------------------------------
# api_call_with_http_status METHOD URL [DATA] [MAX_RETRY] [NO_RETRY_CODES]
#
# api_call と同じヘッダ/リトライ方針で呼び出し、HTTP status を変数に保持する。
#
# Args:
#   METHOD          — HTTP メソッド（GET / POST / PATCH / DELETE）
#   URL             — https://api.github.com/... の完全 URL
#   DATA            — 省略可。JSON リクエストボディ（文字列）
#   MAX_RETRY       — 省略可。最大試行回数（既定: 5）
#   NO_RETRY_CODES  — 省略可。即時終了するHTTPコード（空白区切り。例: "404 401"）
#
# Globals:
#   API_CALL_LAST_HTTP_STATUS — 直近レスポンスのHTTP status（または curl_exit_N）
#
# Returns:
#   成功時(2xx): レスポンス body を stdout に出力し exit 0
#   失敗時: 可能であればレスポンス body を stdout に出力し exit 1
# ---------------------------------------------------------------------------
api_call_with_http_status() {
  local method="$1"; shift
  local url="$1"; shift
  local data="${1:-}"
  local max_retry="${2:-5}"
  local no_retry_codes="${3:-}"
  local wait=1
  local response http_code body
  local curl_exit=0
  local no_retry_match=""

  API_CALL_LAST_HTTP_STATUS="unknown"

  for i in $(seq 1 "${max_retry}"); do
    if [[ -n "${data}" ]]; then
      response=$(curl -sS -w "\n%{http_code}" \
        -X "${method}" \
        -H "Authorization: Bearer ${GH_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        -H "Content-Type: application/json" \
        "${url}" \
        -d "${data}" 2>&1) || curl_exit=$?
    else
      response=$(curl -sS -w "\n%{http_code}" \
        -X "${method}" \
        -H "Authorization: Bearer ${GH_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "${url}" 2>&1) || curl_exit=$?
    fi

    if (( curl_exit == 0 )); then
      http_code=$(echo "${response}" | tail -1)
      body=$(echo "${response}" | head -n -1)
      API_CALL_LAST_HTTP_STATUS="${http_code}"
      echo "${body}"
      if [[ "${http_code}" =~ ^2 ]]; then
        return 0
      fi

      no_retry_match=$(echo " ${no_retry_codes} " | grep -F " ${http_code} " || true)
      if [[ -n "${no_retry_match}" ]]; then
        return 1
      fi

      if (( i < max_retry )); then
        echo "API エラー: HTTP ${http_code}、${wait}秒後にリトライ (${i}/${max_retry})" >&2
        sleep "${wait}"
        wait=$((wait * 2))
      fi
    else
      API_CALL_LAST_HTTP_STATUS="curl_exit_${curl_exit}"
      if (( i < max_retry )); then
        echo "API 呼び出し失敗: ${method} ${url} (${API_CALL_LAST_HTTP_STATUS})、${wait}秒後にリトライ (${i}/${max_retry})" >&2
        sleep "${wait}"
        wait=$((wait * 2))
      fi
    fi

    curl_exit=0
  done

  echo "API 呼び出し失敗: ${method} ${url} (status=${API_CALL_LAST_HTTP_STATUS})" >&2
  return 1
}
