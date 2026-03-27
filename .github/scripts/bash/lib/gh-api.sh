#!/usr/bin/env bash
# gh-api.sh — GitHub REST API utilities (gh CLI wrapper)
#
# Migrated from:
#   - .github/cli/lib/github_api.py
#   - .github/scripts/abd-common.sh (api_call, create_issue, link_sub_issue, add_label, post_comment)
#
# Prerequisites:
#   - bash 4.0+ (associative arrays)
#   - gh CLI installed and authenticated (gh auth status)
#   - jq installed (JSON parsing)
#
# Environment variables:
#   REPO      — Repository in "owner/repo" format (required unless passed as argument)
#   DRY_RUN   — Set to "1" to enable dry-run mode (prints commands instead of executing)
#
# Usage:
#   source ".github/scripts/bash/lib/gh-api.sh"

# NOTE: No `set -euo pipefail` — this file is sourced as a library and must
# not alter the caller's shell options.

# Guard against double-sourcing
if [[ -n "${_GH_API_SH_LOADED:-}" ]]; then
  return 0 2>/dev/null || true
fi
readonly _GH_API_SH_LOADED=1

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_gh_api_resolve_repo() {
  local repo="${1:-}"
  if [[ -n "${repo}" ]]; then
    echo "${repo}"
    return 0
  fi
  if [[ -n "${REPO:-}" ]]; then
    echo "${REPO}"
    return 0
  fi
  echo "ERROR: Repository not specified. Set REPO environment variable (owner/repo)." >&2
  return 1
}

_gh_api_is_dry_run() {
  [[ "${DRY_RUN:-0}" == "1" ]]
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# api_call METHOD ENDPOINT [DATA] [REPO]
#
# Lightweight wrapper around `gh api`. Retry logic is delegated to gh CLI's
# built-in retry mechanism (--retry for transient errors).
#
# Args:
#   METHOD   — HTTP method (GET, POST, PATCH, DELETE)
#   ENDPOINT — API endpoint path (e.g. /repos/{owner}/{repo}/issues)
#   DATA     — Optional JSON request body (string)
#   REPO     — Optional repository override (owner/repo)
#
# Returns:
#   JSON response on stdout. Returns 0 on success, 1 on error.
api_call() {
  local method="${1:?api_call: METHOD required}"
  local endpoint="${2:?api_call: ENDPOINT required}"
  local data="${3:-}"
  local repo="${4:-}"

  repo=$(_gh_api_resolve_repo "${repo}") || return 1

  if _gh_api_is_dry_run; then
    echo "[DRY_RUN] gh api -X ${method} ${endpoint}" >&2
    if [[ -n "${data}" ]]; then
      echo "[DRY_RUN]   --input (json data)" >&2
    fi
    echo "{}"
    return 0
  fi

  local -a cmd=(gh api -X "${method}" --header "Accept: application/vnd.github+json" --retry 3)

  if [[ -n "${data}" ]]; then
    cmd+=(--input -)
    echo "${data}" | "${cmd[@]}" "${endpoint}"
  else
    "${cmd[@]}" "${endpoint}"
  fi
}

# create_issue TITLE BODY LABELS_JSON [REPO]
#
# Create a GitHub Issue and print "number id" (space-separated) to stdout.
#
# Args:
#   TITLE       — Issue title
#   BODY        — Issue body in Markdown
#   LABELS_JSON — JSON array string of label names, e.g. '["bug","help wanted"]'
#   REPO        — Optional repository override
#
# Output:
#   "NUMBER ID" on stdout (e.g. "42 123456789")
create_issue() {
  local title="${1:?create_issue: TITLE required}"
  local body="${2:?create_issue: BODY required}"
  local labels_json="${3:?create_issue: LABELS_JSON required}"
  local repo="${4:-}"

  repo=$(_gh_api_resolve_repo "${repo}") || return 1

  if _gh_api_is_dry_run; then
    echo "[DRY_RUN] gh issue create -R ${repo} --title '${title}' --body-file ... --label ..." >&2
    echo "0 0"
    return 0
  fi

  # Build label args from JSON array
  local -a label_args=()
  local label
  while IFS= read -r label; do
    if [[ -n "${label}" ]]; then
      label_args+=(--label "${label}")
    fi
  done < <(echo "${labels_json}" | jq -r '.[]' 2>/dev/null)

  # Use --body-file to avoid command-line length limits
  local tmpfile
  tmpfile=$(mktemp)
  # shellcheck disable=SC2064
  trap "rm -f '${tmpfile}'" RETURN
  printf '%s' "${body}" > "${tmpfile}"

  local result
  result=$(gh issue create \
    -R "${repo}" \
    --title "${title}" \
    --body-file "${tmpfile}" \
    "${label_args[@]}" 2>&1) || {
    echo "ERROR: create_issue failed: ${result}" >&2
    return 1
  }

  # gh issue create prints the URL; extract the issue number from it
  local issue_url="${result}"
  local issue_number
  issue_number=$(echo "${issue_url}" | grep -oE '[0-9]+$') || {
    echo "ERROR: Could not extract issue number from: ${issue_url}" >&2
    return 1
  }

  # Fetch the numeric database ID (required by link_sub_issue)
  local issue_json
  issue_json=$(gh api "/repos/${repo}/issues/${issue_number}" \
    --header "Accept: application/vnd.github+json" 2>&1) || {
    echo "ERROR: Could not fetch issue details for #${issue_number}" >&2
    return 1
  }

  local issue_id
  issue_id=$(echo "${issue_json}" | jq -r '.id') || {
    echo "ERROR: Could not extract id from issue JSON" >&2
    return 1
  }

  echo "${issue_number} ${issue_id}"
}

# link_sub_issue PARENT_NUM CHILD_ID [REPO]
#
# Link an issue as a sub-issue of a parent issue (idempotent).
# Uses the GitHub Sub Issues API:
#   POST /repos/{owner}/{repo}/issues/{parent}/sub_issues
#
# Args:
#   PARENT_NUM — Parent issue number
#   CHILD_ID   — Sub-issue numeric database ID (from create_issue)
#   REPO       — Optional repository override
#
# Returns:
#   0 on success (or already linked), 1 on error.
link_sub_issue() {
  local parent_num="${1:?link_sub_issue: PARENT_NUM required}"
  local child_id="${2:?link_sub_issue: CHILD_ID required}"
  local repo="${3:-}"

  repo=$(_gh_api_resolve_repo "${repo}") || return 1

  if _gh_api_is_dry_run; then
    echo "[DRY_RUN] gh api POST /repos/${repo}/issues/${parent_num}/sub_issues --field sub_issue_id=${child_id}" >&2
    sleep 1
    return 0
  fi

  local _link_rc=0
  gh api -X POST "/repos/${repo}/issues/${parent_num}/sub_issues" \
    --header "Accept: application/vnd.github+json" \
    --input - <<EOF > /dev/null 2>&1 || _link_rc=$?
{"sub_issue_id":${child_id}}
EOF
  if (( _link_rc != 0 )); then
    echo "WARNING: link_sub_issue 失敗: parent=#${parent_num} child_id=${child_id}" >&2
  fi
  sleep 1
  return "${_link_rc}"
}

# add_label ISSUE_NUM LABEL [REPO]
#
# Add a label to an issue or pull request.
#
# Args:
#   ISSUE_NUM — Issue or PR number
#   LABEL     — Label name
#   REPO      — Optional repository override
add_label() {
  local issue_num="${1:?add_label: ISSUE_NUM required}"
  local label="${2:?add_label: LABEL required}"
  local repo="${3:-}"

  repo=$(_gh_api_resolve_repo "${repo}") || return 1

  if _gh_api_is_dry_run; then
    echo "[DRY_RUN] gh issue edit ${issue_num} -R ${repo} --add-label '${label}'" >&2
    sleep 1
    return 0
  fi

  gh issue edit "${issue_num}" -R "${repo}" --add-label "${label}" > /dev/null
  sleep 1
}

# create_label NAME COLOR [DESCRIPTION] [REPO]
#
# Create a repository label. 422 (already exists) is silently ignored.
#
# Args:
#   NAME        — Label name
#   COLOR       — Hex color string without leading '#' (e.g. "0E8A16")
#   DESCRIPTION — Optional label description
#   REPO        — Optional repository override
#
# Returns:
#   0 if created or already existed, 1 on other errors.
create_label() {
  local name="${1:?create_label: NAME required}"
  local color="${2:?create_label: COLOR required}"
  local description="${3:-}"
  local repo="${4:-}"

  repo=$(_gh_api_resolve_repo "${repo}") || return 1

  if _gh_api_is_dry_run; then
    echo "[DRY_RUN] gh api POST /repos/${repo}/labels --field name='${name}' --field color='${color}'" >&2
    sleep 1
    return 0
  fi

  local result payload
  payload=$(jq -n --arg name "${name}" --arg color "${color}" --arg desc "${description}" \
    '{name: $name, color: $color, description: $desc}')
  if result=$(gh api -X POST "/repos/${repo}/labels" \
    --header "Accept: application/vnd.github+json" \
    --input - <<< "${payload}" 2>&1
  ); then
    echo "ラベル作成: ${name}" >&2
  else
    # Check if it's a 422 (already exists) — gh api returns non-zero for HTTP errors
    if echo "${result}" | grep -q "already_exists\|already exists\|422"; then
      echo "ラベル既存（スキップ）: ${name}" >&2
    else
      echo "ラベル作成エラー: ${name} — ${result}" >&2
      sleep 1
      return 1
    fi
  fi
  sleep 1
  return 0
}

# post_comment ISSUE_NUM BODY [REPO]
#
# Post a comment on an issue or pull request.
#
# Args:
#   ISSUE_NUM — Issue or PR number
#   BODY      — Comment body in Markdown
#   REPO      — Optional repository override
post_comment() {
  local issue_num="${1:?post_comment: ISSUE_NUM required}"
  local body="${2:?post_comment: BODY required}"
  local repo="${3:-}"

  repo=$(_gh_api_resolve_repo "${repo}") || return 1

  if _gh_api_is_dry_run; then
    echo "[DRY_RUN] gh issue comment ${issue_num} -R ${repo} --body-file ..." >&2
    sleep 1
    return 0
  fi

  # Use --body-file to avoid command-line length limits
  local tmpfile
  tmpfile=$(mktemp)
  # shellcheck disable=SC2064
  trap "rm -f '${tmpfile}'" RETURN
  printf '%s' "${body}" > "${tmpfile}"

  gh issue comment "${issue_num}" -R "${repo}" --body-file "${tmpfile}" > /dev/null
  sleep 1
}

# get_issue ISSUE_NUM [REPO]
#
# Fetch issue details and return JSON with normalised fields.
#
# Output JSON keys:
#   number, title, body, state, labels (array of names), assignees (array of logins), id, node_id
#
# Args:
#   ISSUE_NUM — Issue number
#   REPO      — Optional repository override
get_issue() {
  local issue_num="${1:?get_issue: ISSUE_NUM required}"
  local repo="${2:-}"

  repo=$(_gh_api_resolve_repo "${repo}") || return 1

  if _gh_api_is_dry_run; then
    echo "[DRY_RUN] gh issue view ${issue_num} -R ${repo} --json ..." >&2
    echo '{"number":0,"title":"","body":"","state":"","labels":[],"assignees":[],"id":0,"node_id":""}'
    return 0
  fi

  local raw
  raw=$(gh api "/repos/${repo}/issues/${issue_num}" \
    --header "Accept: application/vnd.github+json" 2>&1) || {
    echo "ERROR: get_issue failed for #${issue_num}: ${raw}" >&2
    return 1
  }

  # Normalise: extract label names and assignee logins into flat arrays
  echo "${raw}" | jq '{
    number: .number,
    title: (.title // ""),
    body: (.body // ""),
    state: (.state // ""),
    labels: [.labels[]?.name // empty],
    assignees: [.assignees[]?.login // empty],
    id: (.id // 0),
    node_id: (.node_id // "")
  }'
}
