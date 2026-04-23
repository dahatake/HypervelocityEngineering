#!/usr/bin/env bash
# orchestrate.sh — ワークフロー起動（Issue 一括作成 + Copilot アサイン）
#
# Ported from: .github/cli/orchestrate.py
#
# Creates Root Issue, Sub-Issues from templates, establishes parent-child
# links, and assigns Copilot to the first executable step.
#
# Usage:
#   ./orchestrate.sh --workflow aad --branch main --steps 1.1,1.2 --dry-run
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
# shellcheck source=lib/workflow-registry.sh
source "${_SCRIPT_DIR}/lib/workflow-registry.sh"

# Templates base path: .github/scripts/templates/
_TEMPLATES_BASE="$(cd "${_SCRIPT_DIR}/../templates" && pwd)"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

declare -A _WORKFLOW_DISPLAY_NAMES=(
  [aas]="App Architecture Design"
  [aad]="App Detail Design"
  [asdw]="App Dev Microservice Azure"
  [abd]="Batch Design"
  [abdv]="Batch Dev"
  [adoc]="Source Codeからのドキュメント作成"
)

declare -A _TRIGGER_LABELS=(
  [aas]="auto-app-selection"
  [aad]="auto-app-detail-design"
  [asdw]="auto-app-dev-microservice"
  [abd]="auto-batch-design"
  [abdv]="auto-batch-dev"
  [adoc]="auto-app-documentation"
)

declare -A _WORKFLOW_PREFIX=(
  [aas]="AAS"
  [aad]="AAD"
  [asdw]="ASDW"
  [abd]="ABD"
  [abdv]="ABDV"
  [adoc]="ADOC"
)

# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

_load_template() {
  local template_path="$1"
  local full_path="${_TEMPLATES_BASE}/${template_path}"
  if [[ ! -f "${full_path}" ]]; then
    echo "  ⚠️ テンプレートが見つかりません: ${template_path}" >&2
    return 1
  fi
  cat "${full_path}"
}

_build_root_ref() {
  local root_issue_num="$1"
  local branch="${2:-main}"
  local resource_group="${3:-}"
  local app_id="${4:-}"
  local batch_job_id="${5:-}"
  local auto_review="${6:-true}"
  local auto_qa="${7:-true}"

  local parts=()
  parts+=("<!-- root-issue: #${root_issue_num} -->")
  parts+=("<!-- branch: ${branch} -->")

  [[ -n "${resource_group}" ]] && parts+=("<!-- resource-group: ${resource_group} -->")
  [[ -n "${app_id}" ]]         && parts+=("<!-- app-id: ${app_id} -->")
  [[ -n "${batch_job_id}" ]]   && parts+=("<!-- batch-job-ids: ${batch_job_id} -->")

  parts+=("<!-- auto-review: ${auto_review} -->")
  parts+=("<!-- auto-context-review: true -->")
  parts+=("<!-- auto-qa: ${auto_qa} -->")

  local IFS=$'\n'
  echo "${parts[*]}"
}

_build_additional_section() {
  local additional_comment="${1:-}"
  if [[ -n "${additional_comment}" ]]; then
    printf '\n\n## 追加コメント\n%s' "${additional_comment}"
  fi
}

_build_app_id_section() {
  local app_id="${1:-}"
  [[ -z "${app_id}" ]] && return 0
  printf '\n\n## 対象アプリケーション\n- APP-ID: `%s`\n- この Step では APP-ID `%s` に関連するサービス/エンティティ/画面のみを対象とする\n- `docs/catalog/app-catalog.md` を参照し、対象 APP-ID に紐づく項目を特定する\n- 共有サービス/エンティティ（複数 APP で利用されるもの）も対象に含む' "${app_id}" "${app_id}"
}

_build_rg_section() {
  local resource_group="${1:-}"
  [[ -z "${resource_group}" ]] && return 0
  printf '\n\n## リソースグループ\n`%s`' "${resource_group}"
}

_build_job_section() {
  local batch_job_id="${1:-}"
  [[ -z "${batch_job_id}" ]] && return 0
  printf '\n\n## 対象バッチジョブ ID\n`%s`' "${batch_job_id}"
}

render_template() {
  local template_path="$1"
  local root_issue_num="$2"
  local branch="${3:-main}"
  local resource_group="${4:-}"
  local app_id="${5:-}"
  local batch_job_id="${6:-}"
  local usecase_id="${7:-}"
  local additional_comment="${8:-}"
  local auto_review="${9:-true}"
  local auto_qa="${10:-true}"
  local target_dirs="${11:-}"
  local exclude_patterns="${12:-node_modules/,vendor/,dist/,*.lock,__pycache__/}"
  local doc_purpose="${13:-all}"
  local max_file_lines="${14:-500}"

  local body
  body=$(_load_template "${template_path}") || return 1

  local root_ref
  root_ref=$(_build_root_ref "${root_issue_num}" "${branch}" "${resource_group}" "${app_id}" "${batch_job_id}" "${auto_review}" "${auto_qa}")
  local additional_section
  additional_section=$(_build_additional_section "${additional_comment}")
  local app_id_section
  app_id_section=$(_build_app_id_section "${app_id}")
  local rg_section
  rg_section=$(_build_rg_section "${resource_group}")
  local job_section
  job_section=$(_build_job_section "${batch_job_id}")

  # Perform placeholder substitutions
  body="${body//\{root_ref\}/${root_ref}}"
  body="${body//\{additional_section\}/${additional_section}}"
  body="${body//\{app_id_section\}/${app_id_section}}"
  body="${body//\{resource_group\}/${resource_group}}"
  body="${body//\{usecase_id\}/${usecase_id}}"
  body="${body//\{rg_section\}/${rg_section}}"
  body="${body//\{job_section\}/${job_section}}"
  body="${body//\{s7_subtasks\}/Step.7.1, Step.7.2, Step.7.3}"
  body="${body//\{s5_subtasks\}/Step.5.1, Step.5.2, Step.5.3}"
  body="${body//\{target_dirs\}/${target_dirs}}"
  body="${body//\{exclude_patterns\}/${exclude_patterns}}"
  body="${body//\{doc_purpose\}/${doc_purpose}}"
  body="${body//\{max_file_lines\}/${max_file_lines}}"

  echo "${body}"
}

# ---------------------------------------------------------------------------
# Root Issue body
# ---------------------------------------------------------------------------

_build_root_issue_body() {
  local workflow_id="$1"
  local branch="${2:-main}"
  local resource_group="${3:-}"
  local app_id="${4:-}"
  local batch_job_id="${5:-}"
  local usecase_id="${6:-}"
  local additional_comment="${7:-}"
  local skip_review="${8:-false}"
  local skip_qa="${9:-false}"
  local target_dirs="${10:-}"
  local exclude_patterns="${11:-}"
  local doc_purpose="${12:-}"
  local max_file_lines="${13:-}"

  local prefix="${_WORKFLOW_PREFIX[${workflow_id}]:-}"
  local display_name="${_WORKFLOW_DISPLAY_NAMES[${workflow_id}]:-}"

  local auto_review="true"
  [[ "${skip_review}" == "true" ]] && auto_review="false"
  local auto_qa="true"
  [[ "${skip_qa}" == "true" ]] && auto_qa="false"

  local lines=()
  lines+=("# [${prefix}] ${display_name}")
  lines+=("")
  lines+=("<!-- branch: ${branch} -->")
  [[ -n "${resource_group}" ]] && lines+=("<!-- resource-group: ${resource_group} -->")
  [[ -n "${app_id}" ]]         && lines+=("<!-- app-id: ${app_id} -->")
  [[ -n "${batch_job_id}" ]]   && lines+=("<!-- batch-job-ids: ${batch_job_id} -->")
  lines+=("<!-- auto-review: ${auto_review} -->")
  lines+=("<!-- auto-context-review: true -->")
  lines+=("<!-- auto-qa: ${auto_qa} -->")
  lines+=("")
  lines+=("ワークフロー: **${display_name}**")
  lines+=("ブランチ: \`${branch}\`")

  [[ -n "${app_id}" ]]         && lines+=("APP-ID: \`${app_id}\`")
  [[ -n "${resource_group}" ]] && lines+=("リソースグループ: \`${resource_group}\`")
  [[ -n "${usecase_id}" ]]     && lines+=("ユースケースID: \`${usecase_id}\`")
  [[ -n "${batch_job_id}" ]]   && lines+=("バッチジョブ ID: \`${batch_job_id}\`")
  if [[ "${workflow_id}" == "adoc" ]]; then
    [[ -n "${target_dirs}" ]]      && lines+=("target_dirs: \`${target_dirs}\`")
    [[ -n "${exclude_patterns}" ]] && lines+=("exclude_patterns: \`${exclude_patterns}\`")
    [[ -n "${doc_purpose}" ]]      && lines+=("doc_purpose: \`${doc_purpose}\`")
    [[ -n "${max_file_lines}" ]]   && lines+=("max_file_lines: \`${max_file_lines}\`")
  fi

  if [[ -n "${additional_comment}" ]]; then
    lines+=("")
    lines+=("## 追加コメント")
    lines+=("${additional_comment}")
  fi

  local IFS=$'\n'
  echo "${lines[*]}"
}

# ---------------------------------------------------------------------------
# Step filtering
# ---------------------------------------------------------------------------

_find_parent_container() {
  local step_id="$1"
  shift
  local container_ids=("$@")

  local parts
  IFS='.' read -ra parts <<< "${step_id}"
  if (( ${#parts[@]} > 0 )); then
    local prefix="${parts[0]}"
    for cid in "${container_ids[@]}"; do
      if [[ "${cid}" == "${prefix}" ]]; then
        echo "${prefix}"
        return 0
      fi
    done
  fi
  return 1
}

# ---------------------------------------------------------------------------
# Main orchestrate function
# ---------------------------------------------------------------------------

orchestrate() {
  local workflow_id="$1"
  local branch="${2:-main}"
  local steps_csv="${3:-}"
  local resource_group="${4:-}"
  local app_id="${5:-}"
  local batch_job_id="${6:-}"
  local usecase_id="${7:-}"
  local additional_comment="${8:-}"
  local skip_review="${9:-false}"
  local skip_qa="${10:-false}"
  local model="${11:-${MODEL:-}}"
  local target_dirs="${12:-}"
  local exclude_patterns="${13:-node_modules/,vendor/,dist/,*.lock,__pycache__/}"
  local doc_purpose="${14:-all}"
  local max_file_lines="${15:-500}"
  local repo="${REPO:-}"
  local dry_run="${DRY_RUN:-0}"

  local prefix="${_WORKFLOW_PREFIX[${workflow_id}]:-}"
  local display_name="${_WORKFLOW_DISPLAY_NAMES[${workflow_id}]:-}"

  if [[ -z "${prefix}" ]]; then
    echo "ERROR: 不明なワークフロー: ${workflow_id}" >&2
    return 1
  fi

  local wf_json
  wf_json=$(get_workflow "${workflow_id}") || {
    echo "ERROR: ワークフロー '${workflow_id}' が見つかりません。" >&2
    return 1
  }

  if [[ -z "${repo}" && "${dry_run}" != "1" ]]; then
    echo "ERROR: REPO 環境変数またはリポジトリの指定が必要です。" >&2
    return 1
  fi

  local auto_review="true"
  [[ "${skip_review}" == "true" ]] && auto_review="false"
  local auto_qa="true"
  [[ "${skip_qa}" == "true" ]] && auto_qa="false"

  # Parse selected steps
  local selected_steps=()
  if [[ -n "${steps_csv}" ]]; then
    IFS=',' read -ra selected_steps <<< "${steps_csv}"
  fi

  # Get all step IDs from workflow
  local all_step_ids
  all_step_ids=$(echo "${wf_json}" | jq -r '[.steps[].id] | .[]')

  # Determine active step IDs
  local active_step_ids=()
  if (( ${#selected_steps[@]} == 0 )); then
    while IFS= read -r sid; do
      active_step_ids+=("${sid}")
    done <<< "${all_step_ids}"
  else
    # Validate selected steps and add containers
    for sid in "${selected_steps[@]}"; do
      sid=$(echo "${sid}" | tr -d ' ')
      if echo "${all_step_ids}" | grep -qxF "${sid}"; then
        active_step_ids+=("${sid}")
      else
        echo "  ⚠️ 未知の Step ID: ${sid}（除外します）"
      fi
    done

    if (( ${#active_step_ids[@]} == 0 )); then
      echo "  ⚠️ 有効な Step ID がないため、全ステップを実行します。"
      while IFS= read -r sid; do
        active_step_ids+=("${sid}")
      done <<< "${all_step_ids}"
    fi

    # Add parent containers for selected steps
    local container_ids=()
    while IFS= read -r cid; do
      [[ -n "${cid}" ]] && container_ids+=("${cid}")
    done < <(echo "${wf_json}" | jq -r '.steps[] | select(.is_container == true) | .id')

    for cid in "${container_ids[@]}"; do
      for sid in "${active_step_ids[@]}"; do
        local parts
        IFS='.' read -ra parts <<< "${sid}"
        if (( ${#parts[@]} > 0 )) && [[ "${parts[0]}" == "${cid}" ]]; then
          local found=false
          for a in "${active_step_ids[@]}"; do
            [[ "${a}" == "${cid}" ]] && found=true
          done
          [[ "${found}" == false ]] && active_step_ids+=("${cid}")
          break
        fi
      done
    done
  fi

  # Compute skipped steps (non-container steps not in active set)
  local skipped_step_ids=()
  while IFS= read -r sid; do
    local is_container
    is_container=$(echo "${wf_json}" | jq --arg id "${sid}" '.steps[] | select(.id == $id and .is_container == true) | .id' 2>/dev/null) || true
    [[ -n "${is_container}" ]] && continue

    local in_active=false
    for a in "${active_step_ids[@]}"; do
      [[ "${a}" == "${sid}" ]] && in_active=true
    done
    [[ "${in_active}" == false ]] && skipped_step_ids+=("${sid}")
  done <<< "${all_step_ids}"

  # Display execution plan
  echo ""
  echo "============================================================"
  echo " 実行計画: [${prefix}] ${display_name}"
  echo "============================================================"

  # Count non-container and container active steps
  local active_non_container=0 active_containers=0
  for sid in "${active_step_ids[@]}"; do
    local is_container
    is_container=$(echo "${wf_json}" | jq --arg id "${sid}" '.steps[] | select(.id == $id and .is_container == true) | .id' 2>/dev/null) || true
    if [[ -n "${is_container}" ]]; then
      active_containers=$(( active_containers + 1 ))
    else
      active_non_container=$(( active_non_container + 1 ))
    fi
  done

  echo ""
  echo " 作成するステップ (${active_non_container} 個):"
  for sid in "${active_step_ids[@]}"; do
    local step_json
    step_json=$(echo "${wf_json}" | jq --arg id "${sid}" '.steps[] | select(.id == $id)' 2>/dev/null) || continue
    local is_container
    is_container=$(echo "${step_json}" | jq -r '.is_container' 2>/dev/null)
    [[ "${is_container}" == "true" ]] && continue
    local title agent_name
    title=$(echo "${step_json}" | jq -r '.title')
    agent_name=$(echo "${step_json}" | jq -r '.custom_agent // ""')
    local agent_str=""
    [[ -n "${agent_name}" ]] && agent_str=" [${agent_name}]"
    echo "   ✅ Step.${sid}: ${title}${agent_str}"
  done

  if (( active_containers > 0 )); then
    echo ""
    echo " コンテナ Issue (${active_containers} 個):"
    for sid in "${active_step_ids[@]}"; do
      local step_json
      step_json=$(echo "${wf_json}" | jq --arg id "${sid}" '.steps[] | select(.id == $id)' 2>/dev/null) || continue
      local is_container
      is_container=$(echo "${step_json}" | jq -r '.is_container' 2>/dev/null)
      [[ "${is_container}" != "true" ]] && continue
      local title
      title=$(echo "${step_json}" | jq -r '.title')
      echo "   📦 Step.${sid}: ${title}"
    done
  fi

  if (( ${#skipped_step_ids[@]} > 0 )); then
    echo ""
    echo " スキップされるステップ (${#skipped_step_ids[@]} 個):"
    for sid in "${skipped_step_ids[@]}"; do
      local step_json
      step_json=$(echo "${wf_json}" | jq --arg id "${sid}" '.steps[] | select(.id == $id)' 2>/dev/null) || continue
      local title
      title=$(echo "${step_json}" | jq -r '.title')
      echo "   ⏭️  Step.${sid}: ${title}"
    done
  fi

  if [[ "${dry_run}" == "1" ]]; then
    echo ""
    echo "🔍 ドライラン: GitHub API 呼び出しなし。計画の表示のみ。"
    echo ""
    return 0
  fi

  # --- Live mode: Create Issues ---
  echo ""
  echo "============================================================"
  echo " 実行開始"
  echo "============================================================"
  echo ""

  # 1. Create labels
  echo "📋 ラベル作成..."
  local trigger_label="${_TRIGGER_LABELS[${workflow_id}]}"
  local label_name
  for label_name in $(echo "${wf_json}" | jq -r '.state_labels | to_entries[] | .value'); do
    create_label "${label_name}" "ededed" "" "${repo}" 2>/dev/null || true
  done
  create_label "${trigger_label}" "ededed" "" "${repo}" 2>/dev/null || true
  create_label "auto-context-review" "1D76DB" "" "${repo}" 2>/dev/null || true
  create_label "auto-qa" "BFD4F2" "" "${repo}" 2>/dev/null || true

  # 2. Create Root Issue
  echo ""
  echo "📝 Root Issue 作成..."
  local root_body
  root_body=$(_build_root_issue_body "${workflow_id}" "${branch}" "${resource_group}" "${app_id}" "${batch_job_id}" "${usecase_id}" "${additional_comment}" "${skip_review}" "${skip_qa}" "${target_dirs}" "${exclude_patterns}" "${doc_purpose}" "${max_file_lines}")
  local root_title="[${prefix}] ${display_name}"
  local initialized_label
  initialized_label=$(echo "${wf_json}" | jq -r '.state_labels.initialized // ""')

  local root_labels_json
  root_labels_json=$(printf '%s\n' "${trigger_label}" "${initialized_label}" | jq -R . | jq -s .)

  local root_result
  root_result=$(create_issue "${root_title}" "${root_body}" "${root_labels_json}" "${repo}") || {
    echo "ERROR: Root Issue 作成失敗" >&2
    return 1
  }
  local root_num
  root_num=$(echo "${root_result}" | awk '{print $1}')
  echo "  ✅ Root Issue 作成: #${root_num}"

  # Add auto-context-review / auto-qa labels to Root
  add_label "${root_num}" "auto-context-review" "${repo}" 2>/dev/null || true
  if [[ "${auto_qa}" == "true" ]]; then
    add_label "${root_num}" "auto-qa" "${repo}" 2>/dev/null || true
  fi

  # 3. Create Sub-Issues
  echo ""
  echo "📦 Sub-Issue 一括生成..."

  # Build step labels
  local step_labels=("${trigger_label}")
  step_labels+=("auto-context-review")
  [[ "${auto_qa}" == "true" ]] && step_labels+=("auto-qa")

  local app_id_suffix=""
  [[ -n "${app_id}" ]] && app_id_suffix=" (${app_id})"

  # Associative arrays for created issues: step_id -> number, step_id -> db_id
  declare -A created_nums=()
  declare -A created_ids=()

  # Process steps in workflow order
  local step_count
  step_count=$(echo "${wf_json}" | jq '.steps | length')

  local si
  for (( si=0; si<step_count; si++ )); do
    local step_json
    step_json=$(echo "${wf_json}" | jq ".steps[$si]")
    local sid step_title is_container template_path agent_name
    sid=$(echo "${step_json}" | jq -r '.id')
    step_title=$(echo "${step_json}" | jq -r '.title')
    is_container=$(echo "${step_json}" | jq -r '.is_container')
    template_path=$(echo "${step_json}" | jq -r '.body_template_path // ""')
    agent_name=$(echo "${step_json}" | jq -r '.custom_agent // ""')

    # Skip inactive steps
    local in_active=false
    for a in "${active_step_ids[@]}"; do
      [[ "${a}" == "${sid}" ]] && in_active=true
    done
    [[ "${in_active}" == false ]] && continue

    local issue_title="[${prefix}] Step.${sid}: ${step_title}${app_id_suffix}"
    local issue_body=""

    if [[ -n "${template_path}" ]]; then
      issue_body=$(render_template "${template_path}" "${root_num}" "${branch}" "${resource_group}" "${app_id}" "${batch_job_id}" "${usecase_id}" "${additional_comment}" "${auto_review}" "${auto_qa}" "${target_dirs}" "${exclude_patterns}" "${doc_purpose}" "${max_file_lines}") || true
    fi
    if [[ -z "${issue_body}" ]]; then
      local root_ref
      root_ref=$(_build_root_ref "${root_num}" "${branch}" "${resource_group}" "${app_id}" "${batch_job_id}" "${auto_review}" "${auto_qa}")
      local additional_section
      additional_section=$(_build_additional_section "${additional_comment}")
      issue_body="${root_ref}"$'\n\n'"Step.${sid}: ${step_title}${additional_section}"
    fi

    local issue_labels_json
    issue_labels_json=$(printf '%s\n' "${step_labels[@]}" | jq -R . | jq -s .)

    local result
    result=$(create_issue "${issue_title}" "${issue_body}" "${issue_labels_json}" "${repo}") || {
      echo "  ❌ Step.${sid}: 作成失敗" >&2
      continue
    }

    local num db_id
    num=$(echo "${result}" | awk '{print $1}')
    db_id=$(echo "${result}" | awk '{print $2}')
    created_nums[${sid}]="${num}"
    created_ids[${sid}]="${db_id}"

    local marker="✅"
    [[ "${is_container}" == "true" ]] && marker="📦"
    echo "  ${marker} Step.${sid}: #${num} (${step_title})"

    sleep 1
  done

  # 4. Link parent-child
  echo ""
  echo "🔗 親子紐付け..."

  local container_ids_arr=()
  while IFS= read -r cid; do
    [[ -n "${cid}" ]] && {
      local in_active=false
      for a in "${active_step_ids[@]}"; do
        [[ "${a}" == "${cid}" ]] && in_active=true
      done
      [[ "${in_active}" == true ]] && container_ids_arr+=("${cid}")
    }
  done < <(echo "${wf_json}" | jq -r '.steps[] | select(.is_container == true) | .id')

  for sid in "${!created_ids[@]}"; do
    local num="${created_nums[${sid}]}"
    local db_id="${created_ids[${sid}]}"
    local is_container
    is_container=$(echo "${wf_json}" | jq --arg id "${sid}" '.steps[] | select(.id == $id and .is_container == true) | .id' 2>/dev/null) || true

    if [[ -n "${is_container}" ]]; then
      # Container → Root child
      if link_sub_issue "${root_num}" "${db_id}" "${repo}"; then
        echo "  🔗 Root #${root_num} → Step.${sid} #${num}"
      else
        echo "  ⚠️ 紐付け失敗: Root #${root_num} → Step.${sid} #${num}"
      fi
    else
      # Non-container: find parent container or link to root
      local parent_cid=""
      parent_cid=$(_find_parent_container "${sid}" "${container_ids_arr[@]+"${container_ids_arr[@]}"}" 2>/dev/null) || true

      if [[ -n "${parent_cid}" && -n "${created_nums[${parent_cid}]:-}" ]]; then
        local parent_num="${created_nums[${parent_cid}]}"
        if link_sub_issue "${parent_num}" "${db_id}" "${repo}"; then
          echo "  🔗 Step.${parent_cid} #${parent_num} → Step.${sid} #${num}"
        else
          echo "  ⚠️ 紐付け失敗: Step.${parent_cid} #${parent_num} → Step.${sid} #${num}"
        fi
      else
        if link_sub_issue "${root_num}" "${db_id}" "${repo}"; then
          echo "  🔗 Root #${root_num} → Step.${sid} #${num}"
        else
          echo "  ⚠️ 紐付け失敗: Root #${root_num} → Step.${sid} #${num}"
        fi
      fi
    fi
  done

  # 5. Assign Copilot to first executable step
  echo ""
  echo "🤖 Copilot アサイン..."

  local skipped_json="[]"
  if (( ${#skipped_step_ids[@]} > 0 )); then
    skipped_json=$(printf '%s\n' "${skipped_step_ids[@]}" | jq -R . | jq -s .)
  fi

  local candidates_json
  candidates_json=$(get_next_steps "${workflow_id}" '[]' "${skipped_json}") || true

  local assigned_step_id=""
  local cand_count
  cand_count=$(echo "${candidates_json}" | jq 'length' 2>/dev/null) || true

  local ci
  for (( ci=0; ci<${cand_count:-0}; ci++ )); do
    local cand
    cand=$(echo "${candidates_json}" | jq ".[$ci]")
    local cand_id cand_agent
    cand_id=$(echo "${cand}" | jq -r '.id')
    cand_agent=$(echo "${cand}" | jq -r '.custom_agent // ""')

    [[ -z "${created_nums[${cand_id}]:-}" ]] && continue
    [[ -z "${cand_agent}" ]] && continue

    local cand_num="${created_nums[${cand_id}]}"
    echo "  → Step.${cand_id} (#${cand_num}, agent: ${cand_agent}) にアサイン試行..."

    # Add ready label
    local ready_label
    ready_label=$(echo "${wf_json}" | jq -r '.state_labels.ready // ""')
    if [[ -n "${ready_label}" ]]; then
      add_label "${cand_num}" "${ready_label}" "${repo}" 2>/dev/null || true
    fi

    if assign_copilot "${repo}" "${cand_num}" "${cand_agent}" "${branch}" "" "3" "${model}"; then
      echo "  ✅ Step.${cand_id} にアサイン成功"
      local running_label
      running_label=$(echo "${wf_json}" | jq -r '.state_labels.running // ""')
      if [[ -n "${running_label}" ]]; then
        add_label "${cand_num}" "${running_label}" "${repo}" 2>/dev/null || true
      fi
      assigned_step_id="${cand_id}"
      break
    else
      echo "  ⚠️ Step.${cand_id} アサイン失敗。次のステップを試行..."
    fi
  done

  if [[ -z "${assigned_step_id}" ]]; then
    echo "  ⚠️ アサイン可能なステップがありません。手動アサインが必要です。"
  fi

  # 6. Post summary comment
  local step_list_md=""
  for sid in "${!created_nums[@]}"; do
    step_list_md+="- Step.${sid}: #${created_nums[${sid}]}"$'\n'
  done

  local summary="## ✅ ワークフロー初期化完了

**ワークフロー**: ${display_name}
**作成した Sub-Issue**: ${#created_nums[@]} 件

${step_list_md}"

  if [[ -n "${assigned_step_id}" && -n "${created_nums[${assigned_step_id}]:-}" ]]; then
    summary+="
**Copilot アサイン先**: Step.${assigned_step_id} (#${created_nums[${assigned_step_id}]})"
  fi

  post_comment "${root_num}" "${summary}" "${repo}" 2>/dev/null || true

  echo ""
  echo "============================================================"
  echo " ✅ 完了"
  echo "   Root Issue: #${root_num}"
  echo "   Sub-Issue: ${#created_nums[@]} 件作成"
  [[ -n "${assigned_step_id}" ]] && echo "   Copilot アサイン: Step.${assigned_step_id}"
  echo "============================================================"
  echo ""
}

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

usage() {
  cat <<'EOF'
Usage:
  orchestrate.sh --workflow <id> [options]

Options:
  --workflow, -w <id>      Workflow ID: aas|aad|asdw|abd|abdv|adoc (required)
  --branch <name>          Target branch (default: main)
  --steps <csv>            Comma-separated step IDs (default: all)
  --app-id <id>            ASDW: Application ID
  --resource-group <name>  ASDW/ABDV: Resource group name
  --usecase-id <id>        ASDW: Usecase ID
  --batch-job-id <ids>     ABDV: Batch job IDs (comma-separated)
  --comment <text>         Additional comment
  --skip-review            Skip self-review
  --skip-qa                Skip QA questionnaire
  --repo <owner/repo>      Repository (env: REPO)
  --model <name>           Copilot model（省略時は Auto。GitHub が最適モデルを動的選択）
  --target-dirs <dirs>     ADOC: Target directories (comma-separated)
  --exclude-patterns <p>   ADOC: Exclude patterns (comma-separated, default: node_modules/,vendor/,dist/,*.lock,__pycache__/)
  --doc-purpose <value>    ADOC: all|onboarding|refactoring|migration (default: all)
  --max-file-lines <n>     ADOC: Large file split threshold (default: 500)
  --dry-run                Preview without API calls
  -h, --help               Show this help
EOF
}

main() {
  local workflow="" branch="main" steps="" app_id="" resource_group="" usecase_id="" model=""
  local batch_job_id="" comment="" skip_review="false" skip_qa="false"
  local target_dirs="" exclude_patterns="node_modules/,vendor/,dist/,*.lock,__pycache__/" doc_purpose="all" max_file_lines="500"

  while (( $# > 0 )); do
    case "$1" in
      --workflow|-w)     workflow="${2:?--workflow requires an argument}"; shift 2 ;;
      --branch)          branch="${2:?--branch requires an argument}"; shift 2 ;;
      --steps)           steps="${2:?--steps requires an argument}"; shift 2 ;;
      --app-id)          app_id="${2:?--app-id requires an argument}"; shift 2 ;;
      --resource-group)  resource_group="${2:?--resource-group requires an argument}"; shift 2 ;;
      --usecase-id)      usecase_id="${2:?--usecase-id requires an argument}"; shift 2 ;;
      --batch-job-id)    batch_job_id="${2:?--batch-job-id requires an argument}"; shift 2 ;;
      --comment)         comment="${2:?--comment requires an argument}"; shift 2 ;;
      --skip-review)     skip_review="true"; shift ;;
      --skip-qa)         skip_qa="true"; shift ;;
      --repo)            export REPO="${2:?--repo requires an argument}"; shift 2 ;;
      --model)           model="${2:?--model requires an argument}"; shift 2 ;;
      --target-dirs)     target_dirs="${2:?--target-dirs requires an argument}"; shift 2 ;;
      --exclude-patterns) exclude_patterns="${2:?--exclude-patterns requires an argument}"; shift 2 ;;
      --doc-purpose)     doc_purpose="${2:?--doc-purpose requires an argument}"; shift 2 ;;
      --max-file-lines)  max_file_lines="${2:?--max-file-lines requires an argument}"; shift 2 ;;
      --dry-run)         export DRY_RUN=1; shift ;;
      -h|--help)         usage; exit 0 ;;
      *)                 echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
    esac
  done

  if [[ -z "${workflow}" ]]; then
    echo "Error: --workflow is required" >&2
    usage >&2
    exit 1
  fi

  if [[ "${workflow}" == "adoc" ]]; then
    case "${doc_purpose}" in
      all|onboarding|refactoring|migration) ;;
      *)
        echo "Error: --doc-purpose must be one of: all|onboarding|refactoring|migration" >&2
        usage >&2
        exit 1
        ;;
    esac

    if ! [[ "${max_file_lines}" =~ ^[1-9][0-9]*$ ]]; then
      echo "Error: --max-file-lines must be a positive integer" >&2
      usage >&2
      exit 1
    fi
  fi

  orchestrate "${workflow}" "${branch}" "${steps}" "${resource_group}" "${app_id}" \
    "${batch_job_id}" "${usecase_id}" "${comment}" "${skip_review}" "${skip_qa}" "${model}" \
    "${target_dirs}" "${exclude_patterns}" "${doc_purpose}" "${max_file_lines}"
}

main "$@"
