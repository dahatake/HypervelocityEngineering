#!/usr/bin/env bash
# safe_gh_api: gh api のラッパー。失敗時に stdout を捨てて安全にフォールバック。
# Usage: result=$(safe_gh_api "/repos/OWNER/REPO/issues/123" '{}')
#   $1: GitHub API endpoint
#   $2: fallback value (default: '{}')
# Return:
#   常に 0 を返し、API 失敗時は stderr に warning を出して fallback を stdout に返す。
#   そのため呼び出し側は戻り値ではなく返却内容で分岐すること。
# Example:
#   result=$(safe_gh_api "/repos/${REPO}/issues/${ISSUE_NUM}" '{}')
#   if [ "${result}" = "{}" ]; then
#     echo "fallback が返却されたため API 取得失敗を扱う"
#   fi
safe_gh_api() {
  local endpoint="$1"
  local fallback="${2:-'{}'}"
  local result
  if ! result=$(gh api "$endpoint" 2>/dev/null); then
    echo "::warning::API call failed: ${endpoint}" >&2
    printf '%s' "$fallback"
    return 0
  fi
  printf '%s' "$result"
}
