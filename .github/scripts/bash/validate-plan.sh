#!/usr/bin/env bash
# validate-plan.sh — plan.md 分割判定メタデータ検証
#
# Ported from: .github/cli/validate_plan.py
#
# Validates:
#   1. Required metadata presence (estimate_total, split_decision, implementation_files)
#   2. estimate_total vs split_decision consistency
#   3. SPLIT_REQUIRED + implementation_files incompatibility
#   4. SPLIT_REQUIRED → subissues.md existence
#   5. subissues_count vs actual <!-- subissue --> block count
#   6. ## 分割判定 section presence
#
# Usage:
#   ./validate-plan.sh --path work/Issue-123/plan.md
#   ./validate-plan.sh --directory work/

set -euo pipefail

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_extract_int() {
  local content="$1" key="$2"
  local val
  val=$(echo "${content}" | grep -oP "<!--\s*${key}:\s*\K\d+(?=\s*-->)" | head -1) || true
  echo "${val:-0}"
}

_extract_str() {
  local content="$1" key="$2"
  local val
  val=$(echo "${content}" | grep -oP "<!--\s*${key}:\s*\K\S+(?=\s*-->)" | head -1) || true
  echo "${val:-}"
}

_count_subissue_blocks() {
  local file="$1"
  grep -cP '<!--\s*subissue\s*-->' "${file}" 2>/dev/null || echo "0"
}

# ---------------------------------------------------------------------------
# validate — validate a single plan.md
# ---------------------------------------------------------------------------

validate() {
  local plan_path="$1"
  local errors=()

  if [[ ! -f "${plan_path}" ]]; then
    echo "Error: ${plan_path} not found" >&2
    return 1
  fi

  local content
  content=$(cat "${plan_path}")

  local estimate decision impl_files subissues_count
  estimate=$(_extract_int "${content}" "estimate_total")
  decision=$(_extract_str "${content}" "split_decision")
  impl_files=$(_extract_str "${content}" "implementation_files")
  subissues_count=$(_extract_int "${content}" "subissues_count")

  # Default decision to MISSING if empty
  if [[ -z "${decision}" ]]; then
    decision="MISSING"
  fi
  # Default impl_files to MISSING if empty
  if [[ -z "${impl_files}" ]]; then
    impl_files="MISSING"
  fi

  echo "Checking: ${plan_path}"
  echo "  Estimate: ${estimate}min | Decision: ${decision} | Impl files: ${impl_files} | Subissues count: ${subissues_count}"

  # Rule 0: required metadata must exist and have valid values
  if [[ "${decision}" == "MISSING" ]]; then
    errors+=("${plan_path}: missing required metadata <!-- split_decision: ... -->. See Skill task-dag-planning §2.1.2 for required plan.md metadata format")
  elif [[ "${decision}" != "PROCEED" && "${decision}" != "SPLIT_REQUIRED" ]]; then
    errors+=("${plan_path}: invalid split_decision='${decision}'. Must be PROCEED or SPLIT_REQUIRED")
  fi

  if [[ "${estimate}" == "0" ]] && ! echo "${content}" | grep -qP '<!--\s*estimate_total:'; then
    errors+=("${plan_path}: missing required metadata <!-- estimate_total: ... -->. See Skill task-dag-planning §2.1.2 for required plan.md metadata format")
  fi

  if [[ "${impl_files}" == "MISSING" ]]; then
    errors+=("${plan_path}: missing required metadata <!-- implementation_files: ... -->. See Skill task-dag-planning §2.1.2 for required plan.md metadata format")
  elif [[ "${impl_files}" != "true" && "${impl_files}" != "false" ]]; then
    errors+=("${plan_path}: invalid implementation_files='${impl_files}'. Must be true or false")
  fi

  # Rule 1: estimate > 15 must be SPLIT_REQUIRED
  if (( estimate > 15 )) && [[ "${decision}" == "PROCEED" ]]; then
    errors+=("${plan_path}: estimate=${estimate}min > 15min but decision=PROCEED. Must be SPLIT_REQUIRED per Skill task-dag-planning §2.2")
  fi

  # Rule 2: SPLIT_REQUIRED must not have implementation files
  if [[ "${decision}" == "SPLIT_REQUIRED" && "${impl_files}" == "true" ]]; then
    errors+=("${plan_path}: split_decision=SPLIT_REQUIRED but implementation_files=true. Per Skill task-dag-planning §2.3, implementation files are prohibited in split mode.")
  fi

  # Rule 3: SPLIT_REQUIRED must have subissues.md in same directory
  if [[ "${decision}" == "SPLIT_REQUIRED" ]]; then
    local plan_dir
    plan_dir=$(dirname "${plan_path}")
    local subissues_path="${plan_dir}/subissues.md"
    if [[ ! -f "${subissues_path}" ]]; then
      errors+=("${plan_path}: split_decision=SPLIT_REQUIRED but subissues.md not found in ${plan_dir}")
    else
      # Rule 4: subissues_count should match actual block count
      local actual_count
      actual_count=$(_count_subissue_blocks "${subissues_path}")
      if [[ "${subissues_count}" != "${actual_count}" ]]; then
        errors+=("${plan_path}: subissues_count=${subissues_count} but subissues.md has ${actual_count} <!-- subissue --> blocks")
      fi
    fi
  fi

  # Rule 5: 分割判定 section should exist
  if ! echo "${content}" | grep -q "## 分割判定"; then
    errors+=("${plan_path}: missing required section '## 分割判定'. See Skill task-dag-planning §2.1.2 for the required plan.md metadata/section format")
  fi

  if (( ${#errors[@]} > 0 )); then
    for err in "${errors[@]}"; do
      echo "::error::${err}" >&2
    done
    return 1
  fi

  echo "  ✅ PASS"
  return 0
}

# ---------------------------------------------------------------------------
# validate_directory — find and validate all plan.md files
# ---------------------------------------------------------------------------

validate_directory() {
  local directory="$1"
  local plans
  plans=$(find "${directory}" -name "plan.md" -type f | sort) || true

  if [[ -z "${plans}" ]]; then
    echo "No plan.md files found under ${directory}"
    return 0
  fi

  local all_ok=0
  while IFS= read -r plan; do
    if ! validate "${plan}"; then
      all_ok=1
    fi
  done <<< "${plans}"

  return "${all_ok}"
}

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

usage() {
  cat <<'EOF'
Usage:
  validate-plan.sh --path <plan.md>
  validate-plan.sh --directory <dir>

Options:
  --path <path>       Validate a single plan.md file
  --directory <dir>   Recursively find and validate all plan.md files
  -h, --help          Show this help
EOF
}

main() {
  local mode="" target=""

  while (( $# > 0 )); do
    case "$1" in
      --path)
        mode="path"
        target="${2:?--path requires an argument}"
        shift 2
        ;;
      --directory)
        mode="directory"
        target="${2:?--directory requires an argument}"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "Unknown option: $1" >&2
        usage >&2
        exit 1
        ;;
    esac
  done

  if [[ -z "${mode}" ]]; then
    echo "Error: --path or --directory is required" >&2
    usage >&2
    exit 1
  fi

  if [[ "${mode}" == "path" ]]; then
    validate "${target}"
  else
    validate_directory "${target}"
  fi
}

main "$@"
