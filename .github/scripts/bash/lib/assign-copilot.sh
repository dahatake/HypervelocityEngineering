#!/usr/bin/env bash
# assign-copilot.sh — Copilot cloud agent を Issue にアサインする共通関数
#
# 依存環境変数:
#   GH_TOKEN      — GitHub API トークン（Issue 読み取り用）
#   COPILOT_PAT   — Copilot アサイン用 PAT
#   REPO          — owner/repo 形式
#   GITHUB_WORKSPACE — ワークスペースパス（外部 .py ファイル参照用）
#
# 使用方法:
#   source "${GITHUB_WORKSPACE}/.github/scripts/bash/lib/assign-copilot.sh"
#   assign_copilot <issue_num> [custom_agent] [base_branch] [custom_instructions] [model_raw]

_SCRIPT_DIR="${GITHUB_WORKSPACE}/.github/scripts/bash/lib"

extract_model() {
  local body="$1"
  printf '%s' "${body}" | python3 "${_SCRIPT_DIR}/extract-model.py"
}

extract_review_model() {
  local body="$1"
  printf '%s' "${body}" | python3 "${_SCRIPT_DIR}/extract-review-model.py"
}

extract_qa_model() {
  local body="$1"
  printf '%s' "${body}" | python3 "${_SCRIPT_DIR}/extract-qa-model.py"
}

resolve_model() {
  local raw="$1"
  if [[ -z "${raw}" || "${raw}" == "Auto" ]]; then
    echo "Auto"; return
  fi
  echo "${raw}"
}

assign_copilot() {
  local issue_num="$1"
  local custom_agent="${2:-}"
  local base_branch="${3:-main}"
  local custom_instructions="${4:-}"
  local model_raw="${5:-}"
  local selected_model
  selected_model="$(resolve_model "${model_raw}")"

  echo "=== Copilot アサイン開始: Issue #${issue_num} ==="
  echo "  custom_agent: ${custom_agent}"
  echo "  base_branch: ${base_branch}"

  # 冪等化ガード: 既に copilot-swe-agent がアサインされている場合はスキップ
  local current_assignees
  current_assignees=$(curl -s \
    -H "Authorization: Bearer ${GH_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${REPO}/issues/${issue_num}" \
    | python3 "${_SCRIPT_DIR}/check-assignees.py") || true

  if [[ "${current_assignees}" == "true" ]]; then
    echo "  copilot-swe-agent は既にアサイン済みです。スキップします。"
    return 0
  fi

  # 冪等化ガード: 対象 Issue に紐づく Open な PR が既に存在する場合はスキップ
  local existing_prs
  existing_prs=$(curl -s \
    -H "Authorization: Bearer ${GH_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${REPO}/issues/${issue_num}/timeline?per_page=100" \
    | python3 "${_SCRIPT_DIR}/check-existing-prs.py") || true

  if [[ "${existing_prs}" == "true" ]]; then
    echo "  Issue #${issue_num} に紐づく Open な PR が既に存在します。スキップします。"
    return 0
  fi

  if [[ -z "${COPILOT_PAT:-}" ]]; then
    echo "WARNING: COPILOT_PAT が設定されていません。Copilot アサインをスキップします。" >&2
    return 2  # 2 = skipped (not failure)
  fi

  local OWNER="${REPO%/*}"
  local REPO_NAME="${REPO#*/}"

  local max_assign_retry=3
  local assign_wait=5
  local assign_success=false

  for assign_attempt in $(seq 1 "${max_assign_retry}"); do
    echo "  アサイン試行 ${assign_attempt}/${max_assign_retry}..."

    local query_result
    query_result=$(GH_TOKEN="${COPILOT_PAT}" gh api graphql \
      -f query="
query(\$issueNumber: Int!) {
  repository(owner: \"${OWNER}\", name: \"${REPO_NAME}\") {
    id
    issue(number: \$issueNumber) { id }
    suggestedActors(capabilities: [CAN_BE_ASSIGNED], first: 100) {
      nodes {
        login
        ... on Bot { id databaseId }
      }
    }
  }
}
      " \
      -F issueNumber="${issue_num}" \
      2>&1) || true

    if [[ -z "${query_result}" ]]; then
      echo "WARNING: GraphQL クエリの実行に失敗しました。試行 ${assign_attempt}/${max_assign_retry}" >&2
      sleep "${assign_wait}"
      assign_wait=$((assign_wait * 2))
      continue
    fi

    # JSON として不正な場合は生レスポンスの先頭をログ出力（真因切り分け用）
    if ! printf '%s' "${query_result}" | python3 -c 'import sys,json; json.load(sys.stdin)' 2>/dev/null; then
      echo "  DEBUG: GraphQL non-JSON response (head 800 chars):" >&2
      printf '%s' "${query_result}" | head -c 800 >&2
      echo "" >&2
    fi

    local bot_id issue_node_id repo_node_id
    IFS=$'\t' read -r bot_id issue_node_id repo_node_id < <(printf '%s' "${query_result}" | python3 "${_SCRIPT_DIR}/parse-graphql-ids.py") || true

    if [[ -z "${bot_id}" ]]; then
      echo "WARNING: copilot-swe-agent の Bot ID を取得できませんでした。試行 ${assign_attempt}/${max_assign_retry}" >&2
      sleep "${assign_wait}"
      assign_wait=$((assign_wait * 2))
      continue
    fi
    if [[ -z "${issue_node_id}" ]]; then
      echo "WARNING: Issue #${issue_num} の Node ID を取得できませんでした。試行 ${assign_attempt}/${max_assign_retry}" >&2
      sleep "${assign_wait}"
      assign_wait=$((assign_wait * 2))
      continue
    fi
    if [[ -z "${repo_node_id}" ]]; then
      echo "WARNING: Repository の Node ID を取得できませんでした。試行 ${assign_attempt}/${max_assign_retry}" >&2
      sleep "${assign_wait}"
      assign_wait=$((assign_wait * 2))
      continue
    fi
    echo "  Bot ID: ${bot_id}, Issue Node ID: ${issue_node_id}, Repo Node ID: ${repo_node_id}"

    local result
    # resolve_model() により selected_model は空文字にならず "Auto" または実モデル名になる。
    # Auto 選択時は model 変数を渡さず GitHub 側の自動選択に委譲する。
    local query
    local -a gh_args=(
      -H 'GraphQL-Features: issues_copilot_assignment_api_support,coding_agent_model_selection'
      -f "assignableId=${issue_node_id}"
      -f "botId=${bot_id}"
      -f "targetRepositoryId=${repo_node_id}"
      -f "baseRef=${base_branch}"
      -f "customInstructions=${custom_instructions}"
      -f "customAgent=${custom_agent}"
    )
    if [[ "${selected_model}" != "Auto" ]]; then
      query="
mutation(\$assignableId: ID!, \$botId: ID!, \$targetRepositoryId: ID!, \$baseRef: String!, \$customInstructions: String!, \$customAgent: String!, \$model: String!) {
  addAssigneesToAssignable(input: {
    assignableId: \$assignableId,
    assigneeIds: [\$botId],
    agentAssignment: {
      targetRepositoryId: \$targetRepositoryId,
      baseRef: \$baseRef,
      customInstructions: \$customInstructions,
      customAgent: \$customAgent,
      model: \$model
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
}
      "
      gh_args+=(-f "model=${selected_model}")
    else
      query="
mutation(\$assignableId: ID!, \$botId: ID!, \$targetRepositoryId: ID!, \$baseRef: String!, \$customInstructions: String!, \$customAgent: String!) {
  addAssigneesToAssignable(input: {
    assignableId: \$assignableId,
    assigneeIds: [\$botId],
    agentAssignment: {
      targetRepositoryId: \$targetRepositoryId,
      baseRef: \$baseRef,
      customInstructions: \$customInstructions,
      customAgent: \$customAgent
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
}
      "
    fi
    gh_args+=(-f "query=${query}")
    result=$(GH_TOKEN="${COPILOT_PAT}" gh api graphql "${gh_args[@]}" 2>&1) || true

    # JSON として不正な場合は生レスポンスの先頭をログ出力（真因切り分け用）
    if ! printf '%s' "${result}" | python3 -c 'import sys,json; json.load(sys.stdin)' 2>/dev/null; then
      echo "  DEBUG: GraphQL mutation non-JSON response (head 800 chars):" >&2
      printf '%s' "${result}" | head -c 800 >&2
      echo "" >&2
    else
      echo "  GraphQL mutation レスポンス: ${result}"
    fi

    local has_errors
    has_errors=$(echo "${result}" | python3 "${_SCRIPT_DIR}/check-mutation-errors.py") || true

    if [[ "${has_errors}" == "true" ]]; then
      echo "WARNING: GraphQL mutation にエラーが含まれています。試行 ${assign_attempt}/${max_assign_retry}" >&2
      sleep "${assign_wait}"
      assign_wait=$((assign_wait * 2))
      continue
    fi

    local is_assigned
    is_assigned=$(echo "${result}" | python3 "${_SCRIPT_DIR}/check-assignment-result.py") || true

    if [[ "${is_assigned}" == "true" ]]; then
      echo "  copilot-swe-agent のアサインを確認しました。"
      assign_success=true
      break
    fi

    echo "WARNING: copilot-swe-agent が assignees に含まれていません。試行 ${assign_attempt}/${max_assign_retry}" >&2
    sleep "${assign_wait}"
    assign_wait=$((assign_wait * 2))
  done

  if [[ "${assign_success}" != "true" ]]; then
    echo "WARNING: Issue #${issue_num} へのアサインに失敗しました。" >&2
    return 1
  fi

  echo "=== Copilot アサイン完了: Issue #${issue_num} ==="
  sleep 2
}
