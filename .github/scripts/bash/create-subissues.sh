#!/usr/bin/env bash
# create-subissues.sh — subissues.md パース → Sub Issue 一括作成
#
# Ported from: .github/cli/create_subissues.py
#
# Parses a subissues.md file on <!-- subissue --> markers, extracts metadata
# (title, labels, custom_agent, depends_on), creates GitHub Issues, links
# them to a parent, and assigns Copilot to root nodes.
#
# Usage:
#   ./create-subissues.sh --file work/subissues.md --parent-issue 100 --dry-run
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

# ---------------------------------------------------------------------------
# Metadata extraction from subissue block text
# ---------------------------------------------------------------------------

_extract_comment() {
  local key="$1" text="$2"
  local val
  val=$(echo "${text}" | grep -oP "<!--\s*${key}:\s*\K.*?(?=\s*-->)" | head -1) || true
  if [[ -n "${val}" ]]; then
    echo "${val}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
  fi
}

# ---------------------------------------------------------------------------
# Parse subissues.md into block arrays
# ---------------------------------------------------------------------------

# Output: Sets global arrays _BLOCK_TITLES, _BLOCK_LABELS, _BLOCK_AGENTS,
#         _BLOCK_DEPENDS, _BLOCK_BODIES, _BLOCK_COUNT
parse_subissues() {
  local file="$1"
  # File is read line-by-line below, not in bulk

  _BLOCK_TITLES=()
  _BLOCK_LABELS=()
  _BLOCK_AGENTS=()
  _BLOCK_DEPENDS=()
  _BLOCK_BODIES=()
  _BLOCK_COUNT=0

  # Known metadata keys to strip from body
  local known_meta_keys="title|labels|custom_agent|depends_on"

  # Split content on <!-- subissue --> markers
  # We use awk to split and process blocks
  local block_idx=0
  local in_block=false
  local current_block=""

  while IFS= read -r line || [[ -n "${line}" ]]; do
    if echo "${line}" | grep -qP '<!--\s*subissue\s*-->'; then
      # Process previous block if exists
      if [[ "${in_block}" == true && -n "${current_block}" ]]; then
        _process_block "${block_idx}" "${current_block}" "${known_meta_keys}"
      fi
      block_idx=$(( block_idx + 1 ))
      in_block=true
      current_block=""
      continue
    fi
    if [[ "${in_block}" == true ]]; then
      current_block+="${line}"$'\n'
    fi
  done < "${file}"

  # Process the last block
  if [[ "${in_block}" == true && -n "${current_block}" ]]; then
    _process_block "${block_idx}" "${current_block}" "${known_meta_keys}"
  fi

  _BLOCK_COUNT=${#_BLOCK_TITLES[@]}
}

_process_block() {
  # $1 = block_idx (unused, reserved for future use)
  local raw_block="$2" known_keys="$3"

  # Trim the block
  raw_block=$(echo "${raw_block}" | sed '/^$/{ :a; N; /^\n*$/ba; }' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')

  if [[ -z "${raw_block}" ]]; then
    return
  fi

  local title labels_raw custom_agent depends_raw
  title=$(_extract_comment "title" "${raw_block}")
  labels_raw=$(_extract_comment "labels" "${raw_block}")
  custom_agent=$(_extract_comment "custom_agent" "${raw_block}")
  depends_raw=$(_extract_comment "depends_on" "${raw_block}")

  # Build body: strip known metadata comments
  local body=""
  while IFS= read -r line; do
    if echo "${line}" | grep -qP "^\s*<!--\s*(${known_keys})\s*:"; then
      continue
    fi
    body+="${line}"$'\n'
  done <<< "${raw_block}"

  # Trim body and remove leading/trailing --- separators
  body=$(echo "${body}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  body=$(echo "${body}" | sed 's/^---[[:space:]]*//' | sed 's/[[:space:]]*---[[:space:]]*$//')
  body=$(echo "${body}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

  _BLOCK_TITLES+=("${title}")
  _BLOCK_LABELS+=("${labels_raw}")
  _BLOCK_AGENTS+=("${custom_agent}")
  _BLOCK_DEPENDS+=("${depends_raw}")
  _BLOCK_BODIES+=("${body}")
}

# ---------------------------------------------------------------------------
# Dry-run report
# ---------------------------------------------------------------------------

_dry_run_report() {
  local parent_issue="${1:-}"

  echo ""
  echo "=== Dry-Run Report ==="
  if [[ -n "${parent_issue}" && "${parent_issue}" != "0" ]]; then
    echo "Parent issue: #${parent_issue}"
  else
    echo "No parent issue"
  fi
  echo "Total blocks: ${_BLOCK_COUNT}"
  echo ""

  local root_nodes=()
  local dep_nodes=()

  local i
  for (( i=0; i<_BLOCK_COUNT; i++ )); do
    local block_num=$(( i + 1 ))
    local title="${_BLOCK_TITLES[$i]:-"(no title)"}"
    local agent="${_BLOCK_AGENTS[$i]:-"—"}"
    local labels="${_BLOCK_LABELS[$i]:-"—"}"
    local deps="${_BLOCK_DEPENDS[$i]:-}"

    [[ -z "${agent}" ]] && agent="—"
    [[ -z "${labels}" ]] && labels="—"

    echo "Block ${block_num}: ${title}"
    echo "  Agent: ${agent}"
    echo "  Labels: ${labels}"

    if [[ -n "${deps}" ]]; then
      # Convert comma-separated to array format for display
      local dep_arr=()
      IFS=',' read -ra dep_parts <<< "${deps}"
      for d in "${dep_parts[@]}"; do
        d=$(echo "${d}" | tr -d ' ')
        [[ -n "${d}" ]] && dep_arr+=("${d}")
      done
      echo "  Depends on: [$(printf '%s, ' "${dep_arr[@]}" | sed 's/, $//')]"
      dep_nodes+=("${block_num}")
    else
      if [[ -n "${_BLOCK_AGENTS[$i]}" ]]; then
        echo "  Root node — will auto-assign Copilot"
      else
        echo "  Root node — no custom_agent, Copilot will not be auto-assigned"
      fi
      root_nodes+=("${block_num}")
    fi
    echo ""
  done

  local _root_display _dep_display
  if (( ${#root_nodes[@]} > 0 )); then
    _root_display=$(printf '%s, ' "${root_nodes[@]}" | sed 's/, $//')
  else
    _root_display=""
  fi
  if (( ${#dep_nodes[@]} > 0 )); then
    _dep_display=$(printf '%s, ' "${dep_nodes[@]}" | sed 's/, $//')
  else
    _dep_display=""
  fi
  echo "Root nodes (auto-assign): [${_root_display}]"
  echo "Dependent nodes (wait): [${_dep_display}]"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

usage() {
  cat <<'EOF'
Usage:
  create-subissues.sh --file <path> [--parent-issue <num>] [--pr-number <num>]
                      [--base-branch <branch>] [--repo <owner/repo>] [--dry-run]

Options:
  --file <path>          Path to subissues.md file (required)
  --parent-issue <num>   Explicit parent issue number
  --pr-number <num>      PR number (for parent detection / summary comment)
  --base-branch <branch> Base branch for Copilot assignment (default: main)
  --repo <owner/repo>    Repository (env: REPO)
  --dry-run              Preview without creating issues
  -h, --help             Show this help
EOF
}

main() {
  local file="" parent_issue="" pr_number="" base_branch="main" repo="${REPO:-}"

  while (( $# > 0 )); do
    case "$1" in
      --file)       file="${2:?--file requires an argument}"; shift 2 ;;
      --parent-issue) parent_issue="${2:?--parent-issue requires an argument}"; shift 2 ;;
      --pr-number)  pr_number="${2:?--pr-number requires an argument}"; shift 2 ;;
      --base-branch) base_branch="${2:?--base-branch requires an argument}"; shift 2 ;;
      --repo)       repo="${2:?--repo requires an argument}"; shift 2 ;;
      --dry-run)    export DRY_RUN=1; shift ;;
      -h|--help)    usage; exit 0 ;;
      *)            echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
    esac
  done

  if [[ -z "${file}" ]]; then
    echo "Error: --file is required" >&2
    usage >&2
    exit 1
  fi

  if [[ ! -f "${file}" ]]; then
    echo "Error: ${file} not found" >&2
    exit 1
  fi

  # Parse the subissues.md
  parse_subissues "${file}"

  if (( _BLOCK_COUNT == 0 )); then
    echo "No <!-- subissue --> blocks found in ${file}"
    exit 0
  fi

  echo "Found ${_BLOCK_COUNT} sub-issue block(s) in ${file}"

  # Detect parent issue if not explicitly provided
  if [[ -z "${parent_issue}" && -n "${pr_number}" && -n "${repo}" ]]; then
    parent_issue=$(detect_parent_issue "${repo}" "${pr_number}" 2>/dev/null) || true
  fi

  if [[ -n "${parent_issue}" && "${parent_issue}" != "0" ]]; then
    echo "Parent issue: #${parent_issue}"
  else
    echo "No parent issue detected — sub-issue links will not be created."
  fi

  # Dry-run mode
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    _dry_run_report "${parent_issue}"
    exit 0
  fi

  # --- Live mode: Create issues ---
  local resolved_repo="${repo}"
  if [[ -z "${resolved_repo}" ]]; then
    echo "Error: REPO is required for issue creation" >&2
    exit 1
  fi

  # Check parent labels for propagation
  local has_context_review=false has_qa=false
  if [[ -n "${parent_issue}" && "${parent_issue}" != "0" ]]; then
    local parent_json
    parent_json=$(get_issue "${parent_issue}" "${resolved_repo}" 2>/dev/null) || true
    if [[ -n "${parent_json}" ]]; then
      if echo "${parent_json}" | jq -r '.labels[]' 2>/dev/null | grep -q "auto-context-review"; then
        has_context_review=true
        echo "  auto-context-review ラベル伝播: true"
      fi
      if echo "${parent_json}" | jq -r '.labels[]' 2>/dev/null | grep -q "auto-qa"; then
        has_qa=true
        echo "  auto-qa ラベル伝播: true"
      fi
    fi
  fi

  # Pass 1: Create all issues
  echo "--- Pass 1: Creating issues ---"
  declare -A _ISSUE_MAP_NUM   # block_index -> issue_number
  declare -A _ISSUE_MAP_ID    # block_index -> issue_database_id
  declare -A _ISSUE_MAP_AGENT # block_index -> custom_agent

  local i
  for (( i=0; i<_BLOCK_COUNT; i++ )); do
    local block_num=$(( i + 1 ))
    local title="${_BLOCK_TITLES[$i]}"
    local agent="${_BLOCK_AGENTS[$i]}"
    local body="${_BLOCK_BODIES[$i]}"
    local labels_raw="${_BLOCK_LABELS[$i]}"
    local deps="${_BLOCK_DEPENDS[$i]}"

    if [[ -z "${title}" ]]; then
      echo "  Block ${block_num}: missing title — skipped"
      continue
    fi

    # Append custom agent line
    if [[ -n "${agent}" ]]; then
      body+=$'\n\n'"$(printf '> **Custom agent used: %s**' "${agent}")"
    fi

    # Prepend metadata comments
    local meta_lines=""
    if [[ -n "${parent_issue}" && "${parent_issue}" != "0" ]]; then
      meta_lines+="<!-- parent-issue: #${parent_issue} -->"$'\n'
    fi
    if [[ -n "${pr_number}" ]]; then
      meta_lines+="<!-- pr-number: ${pr_number} -->"$'\n'
    fi
    meta_lines+="<!-- pr-head-branch: ${base_branch} -->"$'\n'
    body="${meta_lines}${body}"

    # Build label list
    local all_labels=()
    if [[ -n "${labels_raw}" ]]; then
      IFS=',' read -ra label_parts <<< "${labels_raw}"
      for lbl in "${label_parts[@]}"; do
        lbl=$(echo "${lbl}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        [[ -n "${lbl}" ]] && all_labels+=("${lbl}")
      done
    fi
    if [[ "${has_context_review}" == true ]]; then
      local found=false
      for lbl in "${all_labels[@]+"${all_labels[@]}"}"; do
        [[ "${lbl}" == "auto-context-review" ]] && found=true
      done
      [[ "${found}" == false ]] && all_labels+=("auto-context-review")
    fi
    if [[ "${has_qa}" == true ]]; then
      local found=false
      for lbl in "${all_labels[@]+"${all_labels[@]}"}"; do
        [[ "${lbl}" == "auto-qa" ]] && found=true
      done
      [[ "${found}" == false ]] && all_labels+=("auto-qa")
    fi

    # Build JSON labels array
    local labels_json="[]"
    if (( ${#all_labels[@]} > 0 )); then
      labels_json=$(printf '%s\n' "${all_labels[@]}" | jq -R . | jq -s .)
    fi

    # Create labels
    for lbl in "${all_labels[@]+"${all_labels[@]}"}"; do
      create_label "${lbl}" "bfd4f2" "" "${resolved_repo}" 2>/dev/null || true
    done

    echo "  Creating: ${title}"
    local result
    result=$(create_issue "${title}" "${body}" "${labels_json}" "${resolved_repo}") || {
      echo "  Failed to create: ${title}" >&2
      continue
    }

    local issue_num issue_id
    issue_num=$(echo "${result}" | awk '{print $1}')
    issue_id=$(echo "${result}" | awk '{print $2}')

    echo "  Created #${issue_num}: ${title}"
    _ISSUE_MAP_NUM[${block_num}]="${issue_num}"
    _ISSUE_MAP_ID[${block_num}]="${issue_id}"
    _ISSUE_MAP_AGENT[${block_num}]="${agent}"

    # Link to parent
    if [[ -n "${parent_issue}" && "${parent_issue}" != "0" && -n "${issue_id}" ]]; then
      sleep 2
      if link_sub_issue "${parent_issue}" "${issue_id}" "${resolved_repo}"; then
        echo "  Linked #${issue_num} to parent #${parent_issue}"
      else
        echo "  Warning: failed to link #${issue_num} to parent #${parent_issue}"
      fi
    fi

    sleep 1
  done

  # Pass 2: Copilot assignment and dependency body update
  echo "--- Pass 2: Copilot assignment and dependency body update ---"
  for (( i=0; i<_BLOCK_COUNT; i++ )); do
    local block_num=$(( i + 1 ))
    local deps="${_BLOCK_DEPENDS[$i]}"
    local agent="${_BLOCK_AGENTS[$i]}"
    local issue_num="${_ISSUE_MAP_NUM[${block_num}]:-}"

    [[ -z "${issue_num}" ]] && continue

    if [[ -z "${deps}" ]]; then
      # Root node: assign Copilot
      if [[ -n "${agent}" ]]; then
        if assign_copilot "${resolved_repo}" "${issue_num}" "${agent}" "${base_branch}"; then
          echo "  #${issue_num}: Copilot assign ✅ 即時"
        else
          echo "  #${issue_num}: Copilot assign ⚠️ 失敗"
        fi
      fi
    else
      # Dependent node: update body with prerequisite links
      local dep_refs=()
      IFS=',' read -ra dep_parts <<< "${deps}"
      for d in "${dep_parts[@]}"; do
        d=$(echo "${d}" | tr -d ' ')
        [[ -n "${d}" ]] && {
          local dep_num="${_ISSUE_MAP_NUM[${d}]:-}"
          [[ -n "${dep_num}" ]] && dep_refs+=("#${dep_num}")
        }
      done

      if (( ${#dep_refs[@]} > 0 )); then
        # Update issue body with dependencies section
        local current_json
        current_json=$(get_issue "${issue_num}" "${resolved_repo}" 2>/dev/null) || true
        if [[ -n "${current_json}" ]]; then
          local current_body
          current_body=$(echo "${current_json}" | jq -r '.body // ""' 2>/dev/null)
          local dep_section
          dep_section=$'\n\n## ⏳ 前提条件（Dependencies）\n\n以下のIssueが完了してから、このIssueにCopilot cloud agentをアサインしてください:\n'
          for ref in "${dep_refs[@]}"; do
            dep_section+="- ${ref}"$'\n'
          done
          local new_body="${current_body}${dep_section}"

          local tmpfile
          tmpfile=$(mktemp)
          printf '%s' "${new_body}" > "${tmpfile}"
          gh issue edit "${issue_num}" --repo "${resolved_repo}" --body-file "${tmpfile}" > /dev/null 2>&1 || true
          rm -f "${tmpfile}"
        fi
      fi

      echo "  #${issue_num}: ⏳ 待ち (依存: ${dep_refs[*]:-未解決})"
    fi
  done

  echo "Done."
}

main "$@"
