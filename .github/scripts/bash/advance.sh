#!/usr/bin/env bash
# advance.sh — 完了 Issue → 次ステップ起動
#
# Ported from: .github/cli/advance.py
#
# Marks a completed issue as done, collects completed/skipped steps,
# determines next steps via workflow DAG, and activates them.
#
# Usage:
#   ./advance.sh --issue 123 --dry-run
#   ./advance.sh --issue 123 --repo owner/repo
#
# Environment:
#   REPO        — Repository in "owner/repo" format
#   GH_TOKEN    — GitHub API token
#   COPILOT_PAT — Copilot assignment PAT
#   DRY_RUN     — Set to "1" for dry-run mode

set -euo pipefail

# Resolve script directory and source shared libraries
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/gh-api.sh
source "${_SCRIPT_DIR}/lib/gh-api.sh"
# shellcheck source=lib/copilot-assign.sh
source "${_SCRIPT_DIR}/lib/copilot-assign.sh"
# shellcheck source=lib/issue-parser.sh
source "${_SCRIPT_DIR}/lib/issue-parser.sh"
# shellcheck source=lib/workflow-registry.sh
source "${_SCRIPT_DIR}/lib/workflow-registry.sh"
# shellcheck source=lib/auto-close.sh
source "${_SCRIPT_DIR}/lib/auto-close.sh"

# ---------------------------------------------------------------------------
# Title parsing — extract workflow ID and step ID
# ---------------------------------------------------------------------------

# Pattern: [XXX] Step.N.N: Title
# Matches: [AAD] Step.1.1: xxx → workflow=aad, step=1.1
#          [ASDW] Step.2.3T: xxx → workflow=asdw, step=2.3T

extract_step_id_from_title() {
  local title="$1"
  echo "${title}" | grep -oP '\[[A-Z]+\]\s*Step\.\K\d+(?:\.\d+(?:[A-Za-z]*)?)' | head -1
}

detect_workflow_id() {
  local title="$1"
  echo "${title}" | grep -oP '\[\K[A-Z]+(?=\]\s*Step\.)' | head -1 | tr '[:upper:]' '[:lower:]'
}

# ---------------------------------------------------------------------------
# activate_issue — Add labels and assign Copilot
# ---------------------------------------------------------------------------

activate_issue() {
  local issue_num="$1"
  local workflow_id="$2"
  local branch="${3:-main}"
  local repo="${4:-${REPO:-}}"

  local wf_json
  wf_json=$(get_workflow "${workflow_id}") || return 1

  local ready_label running_label
  ready_label=$(echo "${wf_json}" | jq -r '.state_labels.ready // ""')
  running_label=$(echo "${wf_json}" | jq -r '.state_labels.running // ""')

  # Add ready label
  if [[ -n "${ready_label}" ]]; then
    add_label "${issue_num}" "${ready_label}" "${repo}" 2>/dev/null || true
  fi

  # Get issue body and extract custom agent
  local issue_json
  issue_json=$(get_issue "${issue_num}" "${repo}" 2>/dev/null) || true
  local body=""
  if [[ -n "${issue_json}" ]]; then
    body=$(echo "${issue_json}" | jq -r '.body // ""' 2>/dev/null) || true
  fi

  local custom_agent=""
  custom_agent=$(extract_custom_agent "${body}" 2>/dev/null) || true

  # Assign Copilot
  if [[ -n "${custom_agent}" ]]; then
    assign_copilot "${repo}" "${issue_num}" "${custom_agent}" "${branch}" || true
  else
    assign_copilot "${repo}" "${issue_num}" "" "${branch}" || true
  fi

  # Add running label
  if [[ -n "${running_label}" ]]; then
    add_label "${issue_num}" "${running_label}" "${repo}" 2>/dev/null || true
  fi

  return 0
}

# ---------------------------------------------------------------------------
# Collect completed/skipped step IDs from Root Issue's Sub-Issues
# ---------------------------------------------------------------------------

_fetch_all_sub_issues() {
  local root_issue="$1" prefix="$2" repo="$3"

  # Get container step IDs from workflow registry (for 2-level hierarchy detection)
  local wf_id
  wf_id=$(echo "${prefix}" | tr '[:upper:]' '[:lower:]')
  local wf_json container_ids_json="[]"
  wf_json=$(get_workflow "${wf_id}" 2>/dev/null) || true
  if [[ -n "${wf_json}" ]]; then
    container_ids_json=$(echo "${wf_json}" | jq '[.steps[] | select(.is_container == true) | .id]' 2>/dev/null) || true
  fi

  local page=1 per_page=100 all_subs="[]"
  while true; do
    local page_json
    page_json=$(gh api "/repos/${repo}/issues/${root_issue}/sub_issues?per_page=${per_page}&page=${page}" \
      --header "Accept: application/vnd.github+json" 2>/dev/null) || break

    local count
    count=$(echo "${page_json}" | jq 'length' 2>/dev/null) || break

    all_subs=$(echo "${all_subs}" "${page_json}" | jq -s '.[0] + .[1]')

    # For each sub-issue, check if it's a container and fetch its children
    local sub_count sub_i
    sub_count=$(echo "${page_json}" | jq 'length' 2>/dev/null) || true
    for (( sub_i=0; sub_i<${sub_count:-0}; sub_i++ )); do
      local sub_title sub_num
      sub_title=$(echo "${page_json}" | jq -r ".[$sub_i].title // \"\"" 2>/dev/null) || continue
      sub_num=$(echo "${page_json}" | jq -r ".[$sub_i].number // empty" 2>/dev/null) || continue
      [[ -z "${sub_num}" ]] && continue

      # Extract step ID from title and check if it's a container
      local sub_step_id
      sub_step_id=$(echo "${sub_title}" | grep -oP "\\[${prefix}\\]\\s*Step\\.\\K\\d+(?:\\.\\d+(?:[A-Za-z]*)?)?") || continue
      [[ -z "${sub_step_id}" ]] && continue

      local is_container
      is_container=$(echo "${container_ids_json}" | jq --arg sid "${sub_step_id}" 'index($sid) != null' 2>/dev/null) || true
      if [[ "${is_container}" != "true" ]]; then
        continue
      fi

      # Fetch children of this container issue
      local child_page=1
      while true; do
        local child_json
        child_json=$(gh api "/repos/${repo}/issues/${sub_num}/sub_issues?per_page=100&page=${child_page}" \
          --header "Accept: application/vnd.github+json" 2>/dev/null) || break
        local child_count
        child_count=$(echo "${child_json}" | jq 'length' 2>/dev/null) || break
        if (( child_count > 0 )); then
          all_subs=$(echo "${all_subs}" "${child_json}" | jq -s '.[0] + .[1]')
        fi
        if (( child_count < 100 )); then
          break
        fi
        child_page=$(( child_page + 1 ))
      done
    done

    if (( count < per_page )); then
      break
    fi
    page=$(( page + 1 ))
  done

  echo "${all_subs}"
}

collect_completed_step_ids() {
  local root_issue="$1" workflow_id="$2" repo="$3" cached_subs="${4:-}"

  local prefix
  prefix=$(echo "${workflow_id}" | tr '[:lower:]' '[:upper:]')

  local subs_json
  if [[ -n "${cached_subs}" ]]; then
    subs_json="${cached_subs}"
  else
    subs_json=$(_fetch_all_sub_issues "${root_issue}" "${prefix}" "${repo}")
  fi

  # Extract step IDs from closed sub-issues with matching title pattern
  echo "${subs_json}" | jq -r --arg pfx "${prefix}" '
    [.[]
     | select(.state == "closed")
     | .title
     | select(test("\\[" + $pfx + "\\]\\s*Step\\.\\d"))
     | capture("\\[" + $pfx + "\\]\\s*Step\\.(?<step>\\d+(?:\\.\\d+(?:[A-Za-z]*)?))")
     | .step
    ] | unique | .[]' 2>/dev/null || true
}

collect_skipped_step_ids() {
  local root_issue="$1" workflow_id="$2" repo="$3" cached_subs="${4:-}"

  local prefix
  prefix=$(echo "${workflow_id}" | tr '[:lower:]' '[:upper:]')

  local subs_json
  if [[ -n "${cached_subs}" ]]; then
    subs_json="${cached_subs}"
  else
    subs_json=$(_fetch_all_sub_issues "${root_issue}" "${prefix}" "${repo}")
  fi

  # Get all step IDs that have Sub-Issues created
  local created_step_ids
  created_step_ids=$(echo "${subs_json}" | jq -r --arg pfx "${prefix}" '
    [.[]
     | .title
     | select(test("\\[" + $pfx + "\\]\\s*Step\\.\\d"))
     | capture("\\[" + $pfx + "\\]\\s*Step\\.(?<step>\\d+(?:\\.\\d+(?:[A-Za-z]*)?))")
     | .step
    ] | unique | .[]' 2>/dev/null) || true

  # Get all non-container step IDs from workflow
  local wf_json
  wf_json=$(get_workflow "${workflow_id}") || return 1

  local all_step_ids
  all_step_ids=$(echo "${wf_json}" | jq -r '[.steps[] | select(.is_container == false) | .id] | .[]' 2>/dev/null) || true

  # Skipped = all steps - created steps
  local step_id
  for step_id in ${all_step_ids}; do
    if ! echo "${created_step_ids}" | grep -qxF "${step_id}"; then
      echo "${step_id}"
    fi
  done
}

# ---------------------------------------------------------------------------
# Find step issue number by title pattern
# ---------------------------------------------------------------------------

_find_step_issue_number() {
  local step_id="$1" workflow_id="$2" root_issue="$3" repo="$4" cached_subs="${5:-}"

  local prefix
  prefix=$(echo "${workflow_id}" | tr '[:lower:]' '[:upper:]')

  local subs_json
  if [[ -n "${cached_subs}" ]]; then
    subs_json="${cached_subs}"
  else
    subs_json=$(_fetch_all_sub_issues "${root_issue}" "${prefix}" "${repo}")
  fi

  # Escape regex metacharacters in step_id (e.g. "1.1" → "1\\.1")
  echo "${subs_json}" | jq -r --arg pfx "${prefix}" --arg sid "${step_id}" '
    ($sid | gsub("\\."; "\\.")) as $escaped_sid |
    [.[]
     | select(.title | test("\\[" + $pfx + "\\]\\s*Step\\." + $escaped_sid + "([^0-9]|$)"))
     | .number
    ] | first // empty' 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Propagate PR labels (auto-context-review / auto-qa)
# ---------------------------------------------------------------------------

propagate_pr_labels() {
  local issue_num="$1" body="$2" repo="$3"

  # Find linked PRs via timeline
  local timeline_json
  timeline_json=$(gh api "/repos/${repo}/issues/${issue_num}/timeline?per_page=100" \
    --header "Accept: application/vnd.github+json" 2>/dev/null) || return 0

  local pr_numbers
  pr_numbers=$(echo "${timeline_json}" | jq -r '
    [.[]
     | select(.event == "cross-referenced")
     | select(.source.issue.pull_request != null)
     | select(.source.issue.state == "open")
     | .source.issue.number
    ] | unique | .[]' 2>/dev/null) || return 0

  local auto_review auto_qa
  auto_review=$(extract_metadata "${body}" "auto-context-review" 2>/dev/null) || true
  auto_qa=$(extract_metadata "${body}" "auto-qa" 2>/dev/null) || true

  local pr_num
  for pr_num in ${pr_numbers}; do
    if [[ "${auto_review}" == "true" ]]; then
      add_label "${pr_num}" "auto-context-review" "${repo}" 2>/dev/null || true
    fi
    if [[ "${auto_qa}" == "true" ]]; then
      add_label "${pr_num}" "auto-qa" "${repo}" 2>/dev/null || true
    fi
  done
}

# ---------------------------------------------------------------------------
# Mark container done
# ---------------------------------------------------------------------------

_mark_container_done() {
  local step_id="$1" workflow_id="$2" root_issue="$3" repo="$4"
  shift 4
  local completed_json="$1" skipped_json="$2"

  local wf_json
  wf_json=$(get_workflow "${workflow_id}") || return 0

  local done_label
  done_label=$(echo "${wf_json}" | jq -r '.state_labels.done // ""')

  # Find parent container for this step
  local container_id=""
  local parts
  IFS='.' read -ra parts <<< "${step_id}"
  if (( ${#parts[@]} > 0 )); then
    local prefix="${parts[0]}"
    local is_container
    is_container=$(echo "${wf_json}" | jq --arg sid "${prefix}" '.steps[] | select(.id == $sid and .is_container == true) | .id' 2>/dev/null) || true
    if [[ -n "${is_container}" ]]; then
      container_id="${prefix}"
    fi
  fi

  [[ -z "${container_id}" ]] && return 0

  # Check if all child steps of container are completed or skipped
  local all_child_ids
  all_child_ids=$(echo "${wf_json}" | jq -r --arg cid "${container_id}" '
    [.steps[]
     | select(.is_container == false)
     | select(.id | startswith($cid + "."))
     | .id
    ] | .[]' 2>/dev/null) || return 0

  local child_id all_done=true
  for child_id in ${all_child_ids}; do
    if ! echo "${completed_json}" | jq -e --arg id "${child_id}" 'index($id) != null' > /dev/null 2>&1; then
      if ! echo "${skipped_json}" | jq -e --arg id "${child_id}" 'index($id) != null' > /dev/null 2>&1; then
        all_done=false
        break
      fi
    fi
  done

  if [[ "${all_done}" == true && -n "${done_label}" ]]; then
    local prefix
    prefix=$(echo "${workflow_id}" | tr '[:lower:]' '[:upper:]')
    local cached_subs
    cached_subs=$(_fetch_all_sub_issues "${root_issue}" "${prefix}" "${repo}")
    local container_issue_num
    container_issue_num=$(_find_step_issue_number "${container_id}" "${workflow_id}" "${root_issue}" "${repo}" "${cached_subs}")
    if [[ -n "${container_issue_num}" ]]; then
      add_label "${container_issue_num}" "${done_label}" "${repo}" 2>/dev/null || true
      echo "  コンテナ Step.${container_id} (#${container_issue_num}) に ${done_label} ラベルを付与しました。"
      auto_close_container_if_done "${container_issue_num}" "${repo}" || true
    fi
  fi
}

# ---------------------------------------------------------------------------
# Mark workflow done
# ---------------------------------------------------------------------------

_mark_workflow_done() {
  local workflow_id="$1" root_issue="$2" repo="$3"

  local wf_json
  wf_json=$(get_workflow "${workflow_id}") || return 0

  local done_label
  done_label=$(echo "${wf_json}" | jq -r '.state_labels.done // ""')

  if [[ -n "${done_label}" ]]; then
    add_label "${root_issue}" "${done_label}" "${repo}" 2>/dev/null || true
    echo "  ワークフロー完了: Root Issue #${root_issue} に ${done_label} ラベルを付与しました。"
  fi

  local wf_name
  wf_name=$(echo "${wf_json}" | jq -r '.name // ""')
  post_comment "${root_issue}" "## ✅ ワークフロー完了\n\n**${wf_name}** のすべてのステップが完了しました。" "${repo}" \
    || echo "::warning::ワークフロー完了コメント投稿に失敗しました: issue #${root_issue}" >&2
  auto_close_root_if_all_done "${root_issue}" "${repo}" || true
}

# ---------------------------------------------------------------------------
# Main advance function
# ---------------------------------------------------------------------------

advance() {
  local issue_num="$1"
  local repo="${2:-${REPO:-}}"
  local dry_run="${DRY_RUN:-0}"

  echo "=== advance: Issue #${issue_num} ==="
  if [[ "${dry_run}" == "1" ]]; then
    echo "🔍 ドライラン: 書き込み API 呼び出しなし。次ステップの特定・表示のみ。"
  fi

  # 1. Fetch issue
  local issue_json
  issue_json=$(get_issue "${issue_num}" "${repo}" 2>/dev/null) || {
    echo "ERROR: Issue #${issue_num} の取得に失敗" >&2
    return 1
  }

  local title body
  title=$(echo "${issue_json}" | jq -r '.title // ""')
  body=$(echo "${issue_json}" | jq -r '.body // ""')
  local labels_json
  labels_json=$(echo "${issue_json}" | jq '.labels // []')

  echo "  タイトル: ${title}"

  # 2. Extract step ID and workflow ID
  local step_id workflow_id
  step_id=$(extract_step_id_from_title "${title}")
  workflow_id=$(detect_workflow_id "${title}")

  if [[ -z "${step_id}" ]]; then
    echo "ERROR: Step 番号が特定できません（title: ${title}）" >&2
    return 1
  fi
  if [[ -z "${workflow_id}" ]]; then
    echo "ERROR: ワークフロー ID が特定できません（title: ${title}）" >&2
    return 1
  fi

  local wf_json
  wf_json=$(get_workflow "${workflow_id}") || {
    echo "ERROR: ワークフロー '${workflow_id}' が見つかりません。" >&2
    return 1
  }

  echo "  ワークフロー: $(echo "${workflow_id}" | tr '[:lower:]' '[:upper:]'), Step: ${step_id}"

  # 3. Extract root issue and branch
  local root_issue_raw
  root_issue_raw=$(extract_metadata "${body}" "root-issue" 2>/dev/null) || true
  if [[ -z "${root_issue_raw}" ]]; then
    echo "ERROR: Root Issue 番号が取得できません。スキップ。" >&2
    return 1
  fi
  local root_issue_num
  root_issue_num=$(echo "${root_issue_raw}" | tr -d '#' | tr -d ' ')

  local branch
  branch=$(extract_metadata "${body}" "branch" 2>/dev/null) || true
  branch="${branch:-main}"

  echo "  Root Issue: #${root_issue_num}"
  echo "  ブランチ: ${branch}"

  # 4. Add done label
  local done_label
  done_label=$(echo "${wf_json}" | jq -r '.state_labels.done // ""')
  if [[ -n "${done_label}" ]]; then
    local has_label
    has_label=$(echo "${labels_json}" | jq -r --arg lbl "${done_label}" 'if index($lbl) then "true" else "false" end' 2>/dev/null) || true
    if [[ "${has_label}" != "true" ]]; then
      if [[ "${dry_run}" == "1" ]]; then
        echo "  [dry-run] ${done_label} ラベルを付与します（スキップ）。"
      else
        add_label "${issue_num}" "${done_label}" "${repo}" 2>/dev/null || true
        echo "  ${done_label} ラベルを付与しました。"
      fi
    fi
  fi

  # 5. PR label propagation
  if [[ "${dry_run}" != "1" ]]; then
    propagate_pr_labels "${issue_num}" "${body}" "${repo}"
  fi

  # 6. Collect completed / skipped steps
  local completed_ids=() skipped_ids=()
  if [[ "${dry_run}" == "1" ]]; then
    completed_ids=("${step_id}")
  else
    local prefix
    prefix=$(echo "${workflow_id}" | tr '[:lower:]' '[:upper:]')
    local cached_subs
    cached_subs=$(_fetch_all_sub_issues "${root_issue_num}" "${prefix}" "${repo}")

    while IFS= read -r sid; do
      [[ -n "${sid}" ]] && completed_ids+=("${sid}")
    done < <(collect_completed_step_ids "${root_issue_num}" "${workflow_id}" "${repo}" "${cached_subs}")

    # Ensure current step is in completed
    local found=false
    for cid in "${completed_ids[@]+"${completed_ids[@]}"}"; do
      [[ "${cid}" == "${step_id}" ]] && found=true
    done
    [[ "${found}" == false ]] && completed_ids+=("${step_id}")

    while IFS= read -r sid; do
      [[ -n "${sid}" ]] && skipped_ids+=("${sid}")
    done < <(collect_skipped_step_ids "${root_issue_num}" "${workflow_id}" "${repo}" "${cached_subs}")

    # Remove completed from skipped
    local new_skipped=()
    for sid in "${skipped_ids[@]+"${skipped_ids[@]}"}"; do
      local is_completed=false
      for cid in "${completed_ids[@]+"${completed_ids[@]}"}"; do
        [[ "${sid}" == "${cid}" ]] && is_completed=true
      done
      [[ "${is_completed}" == false ]] && new_skipped+=("${sid}")
    done
    skipped_ids=("${new_skipped[@]+"${new_skipped[@]}"}")
  fi

  # Build JSON arrays for display and get_next_steps
  local completed_json skipped_json
  completed_json=$(printf '%s\n' "${completed_ids[@]+"${completed_ids[@]}"}" | jq -R . | jq -s .)
  skipped_json=$(printf '%s\n' "${skipped_ids[@]+"${skipped_ids[@]}"}" | jq -R . | jq -s .)
  # Remove empty strings
  completed_json=$(echo "${completed_json}" | jq '[.[] | select(. != "")]')
  skipped_json=$(echo "${skipped_json}" | jq '[.[] | select(. != "")]')

  echo "  完了済みステップ: ${completed_json}"
  echo "  スキップ済みステップ: ${skipped_json}"

  # 7. Mark container done
  if [[ "${dry_run}" != "1" ]]; then
    _mark_container_done "${step_id}" "${workflow_id}" "${root_issue_num}" "${repo}" "${completed_json}" "${skipped_json}"
  fi

  # 8. Get next steps
  local next_steps_json
  next_steps_json=$(get_next_steps "${workflow_id}" "${completed_json}" "${skipped_json}") || true

  # Filter blocked steps (block_unless check)
  local blocked_label
  blocked_label=$(echo "${wf_json}" | jq -r '.state_labels.blocked // ""')

  local activatable_json="[]"
  local step_count
  step_count=$(echo "${next_steps_json}" | jq 'length' 2>/dev/null) || true

  local s
  for (( s=0; s<${step_count:-0}; s++ )); do
    local ns
    ns=$(echo "${next_steps_json}" | jq ".[$s]")
    local ns_id
    ns_id=$(echo "${ns}" | jq -r '.id')
    local block_unless
    block_unless=$(echo "${ns}" | jq -r '.block_unless // [] | .[]' 2>/dev/null) || true

    if [[ -n "${block_unless}" ]]; then
      local unmet=()
      for dep in ${block_unless}; do
        if ! echo "${completed_json}" | jq -e --arg id "${dep}" 'index($id) != null' > /dev/null 2>&1; then
          unmet+=("${dep}")
        fi
      done
      if (( ${#unmet[@]} > 0 )); then
        echo "  Step.${ns_id}: block_unless 条件未達 (未完了: [${unmet[*]}])。blocked 状態にします。"
        if [[ "${dry_run}" != "1" && -n "${blocked_label}" ]]; then
          local prefix
          prefix=$(echo "${workflow_id}" | tr '[:lower:]' '[:upper:]')
          local step_issue
          step_issue=$(_find_step_issue_number "${ns_id}" "${workflow_id}" "${root_issue_num}" "${repo}" "${cached_subs:-}")
          if [[ -n "${step_issue}" ]]; then
            add_label "${step_issue}" "${blocked_label}" "${repo}" 2>/dev/null || true
          fi
        fi
        continue
      fi
    fi
    activatable_json=$(echo "${activatable_json}" | jq --argjson ns "${ns}" '. + [$ns]')
  done

  local act_count
  act_count=$(echo "${activatable_json}" | jq 'length' 2>/dev/null) || true

  if (( ${act_count:-0} == 0 )); then
    echo "  次のステップはありません。ワークフロー完了を確認します..."

    # Check if all non-container steps done or skipped
    local all_nc_ids
    all_nc_ids=$(echo "${wf_json}" | jq -r '[.steps[] | select(.is_container == false) | .id]')
    local all_done
    all_done=$(echo "${all_nc_ids}" | jq --argjson c "${completed_json}" --argjson s "${skipped_json}" '
      all(.[]; . as $id | ($c | index($id) != null) or ($s | index($id) != null))' 2>/dev/null) || true

    if [[ "${all_done}" == "true" ]]; then
      if [[ "${dry_run}" == "1" ]]; then
        echo "  [dry-run] ワークフロー完了ラベルを付与します（スキップ）。"
      else
        _mark_workflow_done "${workflow_id}" "${root_issue_num}" "${repo}"
      fi
    else
      echo "  まだ未完了のステップがあります（依存関係未解決）。"
    fi
    return 0
  fi

  # Display next steps
  local next_ids
  next_ids=$(echo "${activatable_json}" | jq -r '[.[].id]')
  echo "  次のステップ: ${next_ids}"

  if [[ "${dry_run}" == "1" ]]; then
    for (( s=0; s<act_count; s++ )); do
      local ns
      ns=$(echo "${activatable_json}" | jq ".[$s]")
      local ns_id ns_title ns_agent
      ns_id=$(echo "${ns}" | jq -r '.id')
      ns_title=$(echo "${ns}" | jq -r '.title')
      ns_agent=$(echo "${ns}" | jq -r '.custom_agent // ""')
      local agent_str=""
      [[ -n "${ns_agent}" ]] && agent_str=" [${ns_agent}]"
      echo "  [dry-run] Step.${ns_id}: ${ns_title}${agent_str} を起動予定"
    done
    echo ""
    echo "🔍 ドライラン完了: ${act_count} 件のステップを起動予定"
    echo ""
    return 0
  fi

  # 9. Activate next steps
  local activated=0
  for (( s=0; s<act_count; s++ )); do
    local ns
    ns=$(echo "${activatable_json}" | jq ".[$s]")
    local ns_id ns_title
    ns_id=$(echo "${ns}" | jq -r '.id')
    ns_title=$(echo "${ns}" | jq -r '.title')

    local prefix
    prefix=$(echo "${workflow_id}" | tr '[:lower:]' '[:upper:]')
    local step_issue_num
    step_issue_num=$(_find_step_issue_number "${ns_id}" "${workflow_id}" "${root_issue_num}" "${repo}" "${cached_subs:-}")

    if [[ -n "${step_issue_num}" ]]; then
      echo "  Step.${ns_id} → Issue #${step_issue_num} を起動..."
      if activate_issue "${step_issue_num}" "${workflow_id}" "${branch}" "${repo}"; then
        activated=$(( activated + 1 ))
      fi
    else
      echo "  Step.${ns_id} の Issue が見つかりません（スキップ済み？）"
    fi
  done

  echo "=== advance 完了: ${activated} 件のステップを起動 ==="
  return 0
}

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

usage() {
  cat <<'EOF'
Usage:
  advance.sh --issue <number> [--repo <owner/repo>] [--dry-run]

Options:
  --issue <number>     Completed issue number (required)
  --repo <owner/repo>  Repository (env: REPO)
  --dry-run            Preview without API calls
  -h, --help           Show this help
EOF
}

main() {
  local issue="" repo="${REPO:-}"

  while (( $# > 0 )); do
    case "$1" in
      --issue)    issue="${2:?--issue requires a number}"; shift 2 ;;
      --repo)     repo="${2:?--repo requires an argument}"; shift 2 ;;
      --dry-run)  export DRY_RUN=1; shift ;;
      -h|--help)  usage; exit 0 ;;
      *)          echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
    esac
  done

  if [[ -z "${issue}" ]]; then
    echo "Error: --issue is required" >&2
    usage >&2
    exit 1
  fi

  REPO="${repo}" advance "${issue}" "${repo}"
}

main "$@"
