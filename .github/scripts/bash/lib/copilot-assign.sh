#!/usr/bin/env bash
# copilot-assign.sh — Copilot cloud agent アサインモジュール
#
# Migrated from:
#   - .github/cli/lib/copilot_assign.py
#   - .github/scripts/abd-common.sh  assign_copilot()
#
# Prerequisites:
#   - bash 4.0+ (associative arrays)
#   - gh CLI installed and authenticated
#   - jq installed (JSON parsing)
#
# Environment variables:
#   GH_TOKEN / GITHUB_TOKEN — GitHub REST API token (idempotency checks / comments)
#   COPILOT_PAT             — Copilot assignment PAT (GraphQL mutation)
#   REPO                    — Repository in "owner/repo" format
#   DRY_RUN                 — Set to "1" to enable dry-run mode
#
# Usage:
#   source ".github/scripts/bash/lib/copilot-assign.sh"

# NOTE: No `set -euo pipefail` — this file is sourced as a library and must
# not alter the caller's shell options.

# Guard against double-sourcing
if [[ -n "${_COPILOT_ASSIGN_SH_LOADED:-}" ]]; then
  return 0 2>/dev/null || true
fi
readonly _COPILOT_ASSIGN_SH_LOADED=1

# Source gh-api.sh for shared functions (post_comment, get_issue)
# Resolve relative to this script's directory
_COPILOT_ASSIGN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=gh-api.sh
source "${_COPILOT_ASSIGN_DIR}/gh-api.sh"

# GraphQL Features header (enables Copilot assignment API)
_GRAPHQL_FEATURES="issues_copilot_assignment_api_support,coding_agent_model_selection"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_copilot_assign_is_dry_run() {
  [[ "${DRY_RUN:-0}" == "1" ]]
}

_resolve_gh_token() {
  echo "${GH_TOKEN:-${GITHUB_TOKEN:-}}"
}

# _is_copilot_assigned REPO ISSUE_NUMBER
#
# Check whether copilot-swe-agent is already assigned (idempotency guard).
# Returns 0 if assigned, 1 if not.
_is_copilot_assigned() {
  local repo="${1}"
  local issue_number="${2}"

  local issue_json
  issue_json=$(get_issue "${issue_number}" "${repo}" 2>/dev/null) || return 1

  local assignees
  assignees=$(echo "${issue_json}" | jq -r '.assignees[]?' 2>/dev/null) || return 1

  if echo "${assignees}" | grep -qE '^(copilot-swe-agent|Copilot)$'; then
    return 0
  fi
  return 1
}

# _has_open_pr REPO ISSUE_NUMBER
#
# Check whether an open PR already exists for the issue (idempotency guard).
# Returns 0 if found, 1 if not.
_has_open_pr() {
  local repo="${1}"
  local issue_number="${2}"

  local gh_token
  gh_token=$(_resolve_gh_token)
  if [[ -z "${gh_token}" ]]; then
    return 1
  fi

  local timeline_json
  timeline_json=$(gh api "/repos/${repo}/issues/${issue_number}/timeline?per_page=100" \
    --header "Accept: application/vnd.github+json" 2>/dev/null) || return 1

  local has_pr
  has_pr=$(echo "${timeline_json}" | jq '[
    .[]
    | select(.event == "cross-referenced")
    | select(.source.issue.pull_request != null)
    | select(.source.issue.state == "open")
  ] | length > 0' 2>/dev/null) || return 1

  [[ "${has_pr}" == "true" ]]
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# assign_copilot REPO ISSUE_NUMBER [CUSTOM_AGENT] [BASE_BRANCH] [CUSTOM_INSTRUCTIONS] [MAX_RETRIES] [MODEL]
#
# 3-stage dispatch for Copilot assignment:
#   1. `copilot assign` (future: standalone copilot CLI with assign subcommand)
#   2. `gh issue edit --add-assignee @copilot` (no Custom Agent)
#   3. `gh api graphql` with GraphQL mutation (Custom Agent — current primary path)
#
# Args:
#   REPO                — Repository in "owner/repo" format
#   ISSUE_NUMBER        — Issue number to assign
#   CUSTOM_AGENT        — Custom Agent name (optional)
#   BASE_BRANCH         — Base branch for Copilot (default: "main")
#   CUSTOM_INSTRUCTIONS — Custom instructions text (optional)
#   MAX_RETRIES         — Maximum retry count (default: 3)
#   MODEL               — Copilot model (default: "")
#
# Returns:
#   0 on success (or already assigned), 1 on failure
assign_copilot() {
  local repo="${1:?assign_copilot: REPO required}"
  local issue_number="${2:?assign_copilot: ISSUE_NUMBER required}"
  local custom_agent="${3:-}"
  local base_branch="${4:-main}"
  local custom_instructions="${5:-}"
  local max_retries="${6:-3}"
  local model="${7:-}"

  echo "=== Copilot アサイン開始: Issue #${issue_number} ==="
  echo "  custom_agent: ${custom_agent}"
  echo "  base_branch: ${base_branch}"

  if _copilot_assign_is_dry_run; then
    echo "[DRY_RUN] assign_copilot ${repo} #${issue_number} agent=${custom_agent}" >&2
    return 0
  fi

  local gh_token
  gh_token=$(_resolve_gh_token)

  # Idempotency guard: already assigned check
  if [[ -n "${gh_token}" ]] && _is_copilot_assigned "${repo}" "${issue_number}"; then
    echo "  copilot-swe-agent は既にアサイン済みです。スキップします。"
    return 0
  fi

  # Idempotency guard: open PR check
  if [[ -n "${gh_token}" ]] && _has_open_pr "${repo}" "${issue_number}"; then
    echo "  Issue #${issue_number} に紐づく Open な PR が既に存在します。スキップします。"
    return 0
  fi

  # Stage 1: Try standalone `copilot assign` (future support)
  if command -v copilot &>/dev/null; then
    if copilot assign --issue "${issue_number}" --repo "${repo}" 2>/dev/null; then
      echo "  Stage 1: copilot assign 成功"
      echo "=== Copilot アサイン完了: Issue #${issue_number} ==="
      return 0
    fi
  fi

  # Stage 2: Simple assignee (no Custom Agent)
  if [[ -z "${custom_agent}" ]]; then
    if gh issue edit "${issue_number}" -R "${repo}" --add-assignee "@copilot" 2>/dev/null; then
      echo "  Stage 2: gh issue edit --add-assignee 成功"
      echo "=== Copilot アサイン完了: Issue #${issue_number} ==="
      sleep 2
      return 0
    fi
    echo "  Stage 2 failed, falling through to Stage 3 (GraphQL)" >&2
  fi

  # Stage 3: GraphQL mutation (Custom Agent support — current primary path)
  local copilot_pat="${COPILOT_PAT:-}"
  if [[ -z "${copilot_pat}" ]]; then
    echo "WARNING: COPILOT_PAT が設定されていません。Copilot アサインをスキップします。" >&2
    echo "  → Copilot アサイン権限を持つ PAT を作成し、COPILOT_PAT 環境変数に設定してください。" >&2
    return 1
  fi
  local owner="${repo%/*}"
  local repo_name="${repo#*/}"
  local wait=5

  local attempt
  for attempt in $(seq 1 "${max_retries}"); do
    echo "  アサイン試行 ${attempt}/${max_retries}..."

    # Fetch bot_id, issue_node_id, repo_node_id in one query
    local query_result
    query_result=$(GH_TOKEN="${copilot_pat}" gh api graphql \
      -f query='
query($owner: String!, $repoName: String!, $issueNumber: Int!) {
  repository(owner: $owner, name: $repoName) {
    id
    issue(number: $issueNumber) { id }
    suggestedActors(capabilities: [CAN_BE_ASSIGNED], first: 100) {
      nodes {
        login
        ... on Bot { id databaseId }
      }
    }
  }
}' \
      -f owner="${owner}" \
      -f repoName="${repo_name}" \
      -F issueNumber="${issue_number}" 2>&1) || {
      echo "WARNING: GraphQL クエリ失敗 (試行 ${attempt}/${max_retries})" >&2
      if ((attempt < max_retries)); then
        sleep "${wait}"
        wait=$((wait * 2))
      fi
      continue
    }

    local bot_id issue_node_id repo_node_id
    bot_id=$(echo "${query_result}" | jq -r '
      [.data.repository.suggestedActors.nodes[]
       | select(.login == "copilot-swe-agent")
       | .id] | first // ""' 2>/dev/null)
    issue_node_id=$(echo "${query_result}" | jq -r '.data.repository.issue.id // ""' 2>/dev/null)
    repo_node_id=$(echo "${query_result}" | jq -r '.data.repository.id // ""' 2>/dev/null)

    if [[ -z "${bot_id}" ]]; then
      echo "WARNING: copilot-swe-agent の Bot ID を取得できませんでした。試行 ${attempt}/${max_retries}" >&2
      if ((attempt < max_retries)); then sleep "${wait}"; wait=$((wait * 2)); fi
      continue
    fi
    if [[ -z "${issue_node_id}" ]]; then
      echo "WARNING: Issue #${issue_number} の Node ID を取得できませんでした。試行 ${attempt}/${max_retries}" >&2
      if ((attempt < max_retries)); then sleep "${wait}"; wait=$((wait * 2)); fi
      continue
    fi
    if [[ -z "${repo_node_id}" ]]; then
      echo "WARNING: Repository の Node ID を取得できませんでした。試行 ${attempt}/${max_retries}" >&2
      if ((attempt < max_retries)); then sleep "${wait}"; wait=$((wait * 2)); fi
      continue
    fi

    echo "  Bot ID: ${bot_id}, Issue Node ID: ${issue_node_id}, Repo Node ID: ${repo_node_id}"

    # Run the assignment mutation
    local mutation_result
    mutation_result=$(GH_TOKEN="${copilot_pat}" gh api graphql \
      --header "GraphQL-Features: ${_GRAPHQL_FEATURES}" \
      -f query='
mutation(
  $assignableId: ID!,
  $botId: ID!,
  $targetRepositoryId: ID!,
  $baseRef: String!,
  $customInstructions: String!,
  $customAgent: String!,
  $model: String!
) {
  addAssigneesToAssignable(input: {
    assignableId: $assignableId,
    assigneeIds: [$botId],
    agentAssignment: {
      targetRepositoryId: $targetRepositoryId,
      baseRef: $baseRef,
      customInstructions: $customInstructions,
      customAgent: $customAgent,
      model: $model
    }
  }) {
    assignable {
      ... on Issue {
        id
        title
        assignees(first: 10) {
          nodes { login }
        }
      }
    }
  }
}' \
      -f assignableId="${issue_node_id}" \
      -f botId="${bot_id}" \
      -f targetRepositoryId="${repo_node_id}" \
      -f baseRef="${base_branch}" \
      -f customInstructions="${custom_instructions}" \
      -f customAgent="${custom_agent:-}" \
      -f model="${model}" 2>&1) || {
      echo "WARNING: GraphQL mutation 失敗 (試行 ${attempt}/${max_retries})" >&2
      if ((attempt < max_retries)); then sleep "${wait}"; wait=$((wait * 2)); fi
      continue
    }

    # Check if copilot-swe-agent is in the assignees
    local is_assigned
    is_assigned=$(echo "${mutation_result}" | jq -r '
      [.data.addAssigneesToAssignable.assignable.assignees.nodes[]?.login]
      | any(. == "copilot-swe-agent" or . == "Copilot")' 2>/dev/null)

    if [[ "${is_assigned}" == "true" ]]; then
      echo "  copilot-swe-agent のアサインを確認しました。"
      echo "=== Copilot アサイン完了: Issue #${issue_number} ==="
      sleep 2
      return 0
    fi

    echo "WARNING: copilot-swe-agent が assignees に含まれていません。試行 ${attempt}/${max_retries}" >&2
    if ((attempt < max_retries)); then
      sleep "${wait}"
      wait=$((wait * 2))
    fi
  done

  # All retries exhausted — post failure comment
  local fail_msg
  fail_msg="⚠️ Copilot cloud agent (copilot-swe-agent) を Issue #${issue_number} にアサインできませんでした。

手動でアサインする手順:
1. Issue #${issue_number} を開く
2. 右サイドバーの「Assignees」から \`copilot-swe-agent\` を選択する

失敗原因として考えられるもの:
- \`COPILOT_PAT\` の権限不足または失効
- Copilot cloud agent が有効化されていない
- GraphQL API の一時的な障害"

  local comment_token="${gh_token:-${copilot_pat}}"
  if [[ -n "${comment_token}" ]]; then
    post_comment "${issue_number}" "${fail_msg}" "${repo}" 2>/dev/null || {
      echo "WARNING: アサイン失敗通知の投稿にも失敗しました。" >&2
    }
    echo "WARNING: Issue #${issue_number} へのアサイン失敗通知を投稿しました。" >&2
  fi
  return 1
}
