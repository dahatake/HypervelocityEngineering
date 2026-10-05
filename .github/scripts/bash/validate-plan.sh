#!/usr/bin/env bash
# validate-plan.sh — plan.md 完了条件検証
#
# Validates:
#   1. ## 完了条件 section presence and non-placeholder content (FR-DOD-02)
#
# Usage:
#   ./validate-plan.sh --path work/Issue-123/plan.md
#   ./validate-plan.sh --directory work/

set -euo pipefail

# FR-DOD-02: `## 完了条件` の「空とみなす文字」クラス（ブラケット式の中身のみ）。
# glibc の C.UTF-8 では `[[:space:]]` が NO-BREAK SPACE (U+00A0) を空白と見なさず、
# .NET / Python の `\s` とは判定が割れる。両者を一致させるため明示的に追加する。
_BLANK_CLASS="[:space:]$(printf '\u00a0')"

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

  echo "Checking: ${plan_path}"

  # FR-DOD-02: 完了条件 section should exist and have non-placeholder content.
  if ! echo "${content}" | grep -q "## 完了条件"; then
    errors+=("${plan_path}: missing required section '## 完了条件'. See .github/skills/_hve-plan-artifacts/plan-template.md for the required section format")
  else
    local dod_lines
    dod_lines=$(echo "${content}" | awk '
      /^[[:space:]]*##[[:space:]]+完了条件/ { inside = 1; next }
      inside && /^[[:space:]]*##[[:space:]]/ { inside = 0 }
      inside { print }
    ' | grep -vE "^[${_BLANK_CLASS}]*(-{3,})?[${_BLANK_CLASS}]*$" | grep -viE 'REPLACE_ME' || true)
    if [[ -z "${dod_lines}" ]]; then
      errors+=("${plan_path}: section '## 完了条件' has no non-placeholder content. Add at least one verifiable completion condition")
    fi
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
