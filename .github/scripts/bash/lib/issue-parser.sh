#!/usr/bin/env bash
# issue-parser.sh — Issue body 解析モジュール
#
# Migrated from:
#   - .github/cli/lib/issue_parser.py
#   - Various workflow inline Python scripts
#
# Prerequisites:
#   - bash 4.0+ (associative arrays)
#   - gh CLI installed and authenticated
#   - jq installed (JSON parsing)
#   - GNU grep with -P (PCRE) support (default on Linux; macOS requires `brew install grep`)
#
# Environment variables:
#   GH_TOKEN / GITHUB_TOKEN — GitHub API token (for find_parent_issue)
#   REPO                    — Repository in "owner/repo" format
#   PR_NUMBER               — Current PR number (optional, for find_parent_issue)
#   DRY_RUN                 — Set to "1" to enable dry-run mode
#
# Usage:
#   source ".github/scripts/bash/lib/issue-parser.sh"

# NOTE: No `set -euo pipefail` — this file is sourced as a library and must
# not alter the caller's shell options.

# Guard against double-sourcing
if [[ -n "${_ISSUE_PARSER_SH_LOADED:-}" ]]; then
  return 0 2>/dev/null || true
fi
readonly _ISSUE_PARSER_SH_LOADED=1

# Source gh-api.sh for shared functions (api_call, get_issue)
_ISSUE_PARSER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=gh-api.sh
source "${_ISSUE_PARSER_DIR}/gh-api.sh"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_issue_parser_is_dry_run() {
  [[ "${DRY_RUN:-0}" == "1" ]]
}

_issue_parser_resolve_token() {
  echo "${GH_TOKEN:-${GITHUB_TOKEN:-}}"
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# extract_metadata BODY KEY
#
# Extract HTML comment metadata from issue body.
# Format: <!-- key: value -->
#
# Args:
#   BODY — Issue body text (positional argument)
#   KEY  — Metadata key name (e.g. "root-issue", "branch", "auto-review")
#
# Output:
#   Value string on stdout, or empty string if not found.
#   Returns 0 if found, 1 if not found.
extract_metadata() {
  local body="${1:?extract_metadata: BODY required}"
  local key="${2:?extract_metadata: KEY required}"

  local value
  # Use grep + sed to extract <!-- key: value -->
  # The key is matched literally (special regex chars in key names are unlikely)
  value=$(echo "${body}" | grep -oP "<!--\s*${key}\s*:\s*\K[^>]*?(?=\s*-->)" | head -1) || true

  if [[ -n "${value}" ]]; then
    # Trim whitespace
    value=$(echo "${value}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    echo "${value}"
    return 0
  fi
  return 1
}

# extract_custom_agent BODY
#
# Extract Custom Agent name from issue body.
#
# Supported patterns (priority order):
#   1. ## Custom Agent\n`AgentName`
#   2. > **Custom agent used: AgentName**
#
# Args:
#   BODY — Issue body text
#
# Output:
#   Agent name on stdout, empty if not found.
#   Returns 0 if found, 1 if not found.
extract_custom_agent() {
  local body="${1:?extract_custom_agent: BODY required}"

  local agent=""

  # Pattern 1: ## Custom Agent\n`AgentName`
  # Use sed for multiline matching (more portable than grep -Pzo)
  agent=$(printf '%s' "${body}" | sed -n '/^##[[:space:]]*Custom Agent/,/^$/{ /`/{s/.*`\([^`]*\)`.*/\1/p;q;} }') 2>/dev/null || true

  if [[ -n "${agent}" ]]; then
    echo "${agent}"
    return 0
  fi

  # Pattern 2: > **Custom agent used: AgentName**
  agent=$(printf '%s' "${body}" | grep -oP '>\s*\*\*Custom agent used:\s*\K[^*]+' | head -1) 2>/dev/null || true

  if [[ -n "${agent}" ]]; then
    # Trim whitespace
    agent=$(echo "${agent}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    echo "${agent}"
    return 0
  fi

  return 1
}

# find_parent_issue REPO ISSUE_NUMBER
#
# Resolve parent issue number with 4-stage fallback:
#   Method 1: Issue body <!-- parent-issue: #NNN -->
#   Method 2: Issue body <!-- pr-number: NNN --> → PR closingIssuesReferences
#   Method 3a: GraphQL trackedInIssues
#   Method 3b: <!-- subissues-created --> PR comment
#
# Args:
#   REPO         — Repository in "owner/repo" format
#   ISSUE_NUMBER — Issue number to find parent for
#
# Output:
#   Parent issue number on stdout.
#   Returns 0 if found, 1 if not found.
find_parent_issue() {
  local repo="${1:?find_parent_issue: REPO required}"
  local issue_number="${2:?find_parent_issue: ISSUE_NUMBER required}"

  if _issue_parser_is_dry_run; then
    echo "[DRY_RUN] find_parent_issue ${repo} #${issue_number}" >&2
    echo "0"
    return 0
  fi

  local token
  token=$(_issue_parser_resolve_token)
  if [[ -z "${token}" ]]; then
    echo "WARNING: GH_TOKEN / GITHUB_TOKEN が設定されていません。親 Issue を特定できません。" >&2
    return 1
  fi

  local current_pr="${PR_NUMBER:-}"

  # Get issue body (used by Method 1 and 2)
  local issue_body=""
  local issue_json
  issue_json=$(get_issue "${issue_number}" "${repo}" 2>/dev/null) || true
  if [[ -n "${issue_json}" ]]; then
    issue_body=$(echo "${issue_json}" | jq -r '.body // ""' 2>/dev/null) || true
  fi

  # Method 1: <!-- parent-issue: #NNN -->
  local parent_num
  parent_num=$(echo "${issue_body}" | grep -oP '<!--\s*parent-issue:\s*#\K\d+' | head -1) || true
  if [[ -n "${parent_num}" ]]; then
    echo "  Method 1 (parent-issue comment): #${parent_num}" >&2
    echo "${parent_num}"
    return 0
  fi

  # Method 2: <!-- pr-number: NNN --> → PR's closingIssuesReferences
  local source_pr
  source_pr=$(echo "${issue_body}" | grep -oP '<!--\s*pr-number:\s*\K\d+' | head -1) || true
  if [[ -n "${source_pr}" && "${source_pr}" != "${current_pr}" ]]; then
    local pr_json
    pr_json=$(gh api "/repos/${repo}/pulls/${source_pr}" \
      --header "Accept: application/vnd.github+json" 2>/dev/null) || true
    if [[ -n "${pr_json}" ]]; then
      local pr_body
      pr_body=$(echo "${pr_json}" | jq -r '.body // ""' 2>/dev/null) || true
      local closing_issue
      closing_issue=$(echo "${pr_body}" | grep -oiP '(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\s+(?:[\w\-\.]+/[\w\-\.]+)?#\K\d+' | head -1) || true
      if [[ -n "${closing_issue}" ]]; then
        echo "  Method 2 (pr-number comment): #${closing_issue} via PR #${source_pr}" >&2
        echo "${closing_issue}"
        return 0
      fi
    fi
  fi

  # Method 3a: GraphQL trackedInIssues
  local owner="${repo%/*}"
  local repo_name="${repo#*/}"
  local graphql_result
  graphql_result=$(gh api graphql \
    -f query='
query($owner: String!, $repo: String!, $num: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $num) {
      trackedInIssues(first: 1) {
        nodes { number }
      }
    }
  }
}' \
    -f owner="${owner}" \
    -f repo="${repo_name}" \
    -F num="${issue_number}" 2>/dev/null) || true

  if [[ -n "${graphql_result}" ]]; then
    local tracked_num
    tracked_num=$(echo "${graphql_result}" | jq -r '.data.repository.issue.trackedInIssues.nodes[0].number // empty' 2>/dev/null) || true
    if [[ -n "${tracked_num}" ]]; then
      echo "  Method 3a (GraphQL trackedInIssues): #${tracked_num}" >&2
      echo "${tracked_num}"
      return 0
    fi
  fi

  # Method 3b: <!-- subissues-created --> PR comment
  local timeline_json
  timeline_json=$(gh api "/repos/${repo}/issues/${issue_number}/timeline?per_page=100" \
    --header "Accept: application/vnd.github+json" 2>/dev/null) || true

  if [[ -n "${timeline_json}" ]]; then
    local xref_prs
    xref_prs=$(echo "${timeline_json}" | jq -r '
      [.[]
       | select(.event == "cross-referenced")
       | select(.source.issue.pull_request != null)
       | .source.issue.number
      ] | .[] | tostring' 2>/dev/null) || true

    local xref_pr
    for xref_pr in ${xref_prs}; do
      [[ "${xref_pr}" == "${current_pr}" ]] && continue

      # Check for <!-- subissues-created --> marker in PR comments
      local comments_json
      comments_json=$(gh api "/repos/${repo}/issues/${xref_pr}/comments?per_page=100" \
        --header "Accept: application/vnd.github+json" 2>/dev/null) || { sleep 0.5; continue; }

      local has_marker
      has_marker=$(echo "${comments_json}" | jq 'any(.[]; .body // "" | contains("<!-- subissues-created -->"))' 2>/dev/null) || { sleep 0.5; continue; }

      if [[ "${has_marker}" != "true" ]]; then
        sleep 0.5
        continue
      fi

      # Extract closingIssuesReferences from this PR's body
      local xref_pr_json
      xref_pr_json=$(gh api "/repos/${repo}/pulls/${xref_pr}" \
        --header "Accept: application/vnd.github+json" 2>/dev/null) || { sleep 0.5; continue; }

      local xref_pr_body
      xref_pr_body=$(echo "${xref_pr_json}" | jq -r '.body // ""' 2>/dev/null) || true

      local closing_ref
      closing_ref=$(echo "${xref_pr_body}" | grep -oiP '(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\s+(?:[\w\-\.]+/[\w\-\.]+)?#\K\d+' | head -1) || true

      if [[ -n "${closing_ref}" ]]; then
        echo "  Method 3b (subissues-created): #${closing_ref} via PR #${xref_pr}" >&2
        echo "${closing_ref}"
        return 0
      fi
      sleep 0.5
    done
  fi

  echo "  WARNING: 全 Method で親 Issue を特定できませんでした。" >&2
  return 1
}
