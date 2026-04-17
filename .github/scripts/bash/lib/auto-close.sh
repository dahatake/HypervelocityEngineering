#!/usr/bin/env bash
# auto-close.sh — Issue 自動クローズユーティリティ

# NOTE: This file is sourced as a library. Do not set shell options here.

# Guard against double-sourcing
if [[ -n "${_AUTO_CLOSE_SH_LOADED:-}" ]]; then
  return 0 2>/dev/null || true
fi
readonly _AUTO_CLOSE_SH_LOADED=1

_AUTO_CLOSE_MARKER='<!-- auto-close-done -->'

_auto_close_resolve_repo() {
  local repo="${1:-}"
  if [[ -n "${repo}" ]]; then
    echo "${repo}"
    return 0
  fi
  if [[ -n "${REPO:-}" ]]; then
    echo "${REPO}"
    return 0
  fi
  if [[ -n "${GITHUB_REPOSITORY:-}" ]]; then
    echo "${GITHUB_REPOSITORY}"
    return 0
  fi
  echo "ERROR: Repository not specified (owner/repo)." >&2
  return 1
}

# _is_auto_merge_enabled ISSUE_JSON
# 判定条件: auto-approve-ready ラベル OR <!-- auto-merge: true -->
_is_auto_merge_enabled() {
  local issue_json="${1:-}"
  if [[ -z "${issue_json}" ]]; then
    echo "false"
    return 1
  fi

  local result
  result=$(printf '%s' "${issue_json}" | python3 -c '
import json, re, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("false")
    sys.exit(0)
labels = [l.get("name", "") for l in d.get("labels", []) if isinstance(l, dict)]
if "auto-approve-ready" in labels:
    print("true")
    sys.exit(0)
body = d.get("body") or ""
print("true" if re.search(r"<!--\s*auto-merge:\s*true\s*-->", body) else "false")
') || result="false"

  echo "${result}"
  [[ "${result}" == "true" ]]
}

# _has_auto_close_marker ISSUE_NUM [REPO]
_has_auto_close_marker() {
  local issue_num="${1:?_has_auto_close_marker: ISSUE_NUM required}"
  local repo
  repo=$(_auto_close_resolve_repo "${2:-}") || return 1

  local page=1 per_page=100
  while true; do
    local comments_json
    comments_json=$(gh api "/repos/${repo}/issues/${issue_num}/comments?per_page=${per_page}&page=${page}" 2>/dev/null) || {
      echo "false"
      return 1
    }

    local has_marker
    has_marker=$(printf '%s' "${comments_json}" | python3 -c '
import json, sys
marker = "<!-- auto-close-done -->"
try:
    comments = json.load(sys.stdin)
    if not isinstance(comments, list):
        comments = []
except Exception:
    comments = []
print("true" if any(marker in (c.get("body") or "") for c in comments if isinstance(c, dict)) else "false")
') || has_marker="false"

    if [[ "${has_marker}" == "true" ]]; then
      echo "true"
      return 0
    fi

    local count
    count=$(printf '%s' "${comments_json}" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(len(data) if isinstance(data, list) else 0)
except Exception:
    print(0)
') || count=0

    if (( count < per_page )); then
      break
    fi
    page=$((page + 1))
  done

  echo "false"
  return 1
}

# _all_sub_issues_closed ISSUE_NUM [REPO]
_all_sub_issues_closed() {
  local issue_num="${1:?_all_sub_issues_closed: ISSUE_NUM required}"
  local repo
  repo=$(_auto_close_resolve_repo "${2:-}") || return 1

  local page=1 per_page=100
  while true; do
    local subs_json
    subs_json=$(gh api "/repos/${repo}/issues/${issue_num}/sub_issues?per_page=${per_page}&page=${page}" 2>/dev/null) || {
      echo "false"
      return 1
    }

    local page_all_closed
    page_all_closed=$(printf '%s' "${subs_json}" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    if not isinstance(data, list):
        data = []
except Exception:
    data = []
print("true" if all((i.get("state") == "closed") for i in data if isinstance(i, dict)) else "false")
') || page_all_closed="false"

    if [[ "${page_all_closed}" != "true" ]]; then
      echo "false"
      return 1
    fi

    local count
    count=$(printf '%s' "${subs_json}" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(len(data) if isinstance(data, list) else 0)
except Exception:
    print(0)
') || count=0

    if (( count < per_page )); then
      break
    fi
    page=$((page + 1))
  done

  echo "true"
  return 0
}

# auto_close_issue ISSUE_NUM REASON_MSG [REPO]
auto_close_issue() {
  local issue_num="${1:?auto_close_issue: ISSUE_NUM required}"
  local reason_msg="${2:-Sub-issues are completed}"
  local repo
  repo=$(_auto_close_resolve_repo "${3:-}") || return 1

  local issue_json
  issue_json=$(gh api "/repos/${repo}/issues/${issue_num}" 2>/dev/null) || {
    echo "WARNING: Issue #${issue_num} の取得に失敗したため自動クローズをスキップします。" >&2
    return 1
  }

  local state
  state=$(printf '%s' "${issue_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state',''))" 2>/dev/null || echo "")
  if [[ "${state}" != "open" ]]; then
    echo "Issue #${issue_num} は open ではありません（state=${state:-unknown}）。スキップ。"
    return 0
  fi

  local auto_merge_enabled
  auto_merge_enabled=$(_is_auto_merge_enabled "${issue_json}" || true)
  if [[ "${auto_merge_enabled}" != "true" ]]; then
    echo "Issue #${issue_num} は auto-merge 無効のため自動クローズをスキップします。"
    return 0
  fi

  local has_marker
  if ! has_marker=$(_has_auto_close_marker "${issue_num}" "${repo}"); then
    echo "WARNING: Issue #${issue_num} の auto-close マーカーチェックに失敗したため自動クローズをスキップします。" >&2
    return 1
  fi
  if [[ "${has_marker}" == "true" ]]; then
    echo "Issue #${issue_num} は auto-close マーカー済みのためスキップします。"
    return 0
  fi

  local close_comment
  close_comment=$(printf '## ✅ Auto Close\n\n%s\n\n%s' "${reason_msg}" "${_AUTO_CLOSE_MARKER}")

  if ! gh issue comment "${issue_num}" --repo "${repo}" --body "${close_comment}" >/dev/null 2>&1; then
    echo "WARNING: Issue #${issue_num} への auto-close コメント投稿に失敗しました。" >&2
  fi

  if gh issue close "${issue_num}" --repo "${repo}" --reason completed >/dev/null 2>&1; then
    echo "Issue #${issue_num} を自動クローズしました。"
  else
    echo "WARNING: Issue #${issue_num} の自動クローズに失敗しました。" >&2
    return 1
  fi
}

# auto_close_container_if_done CONTAINER_NUM [REPO]
auto_close_container_if_done() {
  local container_num="${1:?auto_close_container_if_done: CONTAINER_NUM required}"
  local repo
  repo=$(_auto_close_resolve_repo "${2:-}") || return 1

  if _all_sub_issues_closed "${container_num}" "${repo}" >/dev/null; then
    auto_close_issue "${container_num}" "全ての Sub Issue が完了したため、コンテナ Issue を自動クローズします。" "${repo}" || true
  else
    echo "コンテナ Issue #${container_num} は未完了 Sub Issue があるためクローズしません。"
  fi
}

# auto_close_root_if_all_done ROOT_NUM [REPO]
auto_close_root_if_all_done() {
  local root_num="${1:?auto_close_root_if_all_done: ROOT_NUM required}"
  local repo
  repo=$(_auto_close_resolve_repo "${2:-}") || return 1

  if _all_sub_issues_closed "${root_num}" "${repo}" >/dev/null; then
    auto_close_issue "${root_num}" "全ての Sub Issue が完了したため、Root Issue を自動クローズします。" "${repo}" || true
  else
    echo "Root Issue #${root_num} は未完了 Sub Issue があるためクローズしません。"
  fi
}
