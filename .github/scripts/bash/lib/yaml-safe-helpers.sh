#!/usr/bin/env bash
# yaml-safe-helpers.sh — workflow YAML-safe helper wrappers

if [[ -n "${_YAML_SAFE_HELPERS_SH_LOADED:-}" ]]; then
  return 0 2>/dev/null || true
fi
readonly _YAML_SAFE_HELPERS_SH_LOADED=1

_WH_PY="${_WH_PY:-${GITHUB_WORKSPACE:-.}/.github/scripts/python/workflow_helpers.py}"

wh_has_marker() {
  python3 "${_WH_PY}" has_marker "${1:-<!-- auto-close-done -->}" 2>/dev/null || echo "false"
}

wh_count_items() {
  python3 "${_WH_PY}" count_items 2>/dev/null || echo "0"
}

wh_all_closed() {
  python3 "${_WH_PY}" all_closed 2>/dev/null || echo "false"
}

wh_has_label() {
  python3 "${_WH_PY}" has_label "${1:-}" 2>/dev/null || echo "false"
}

wh_check_auto_merge() {
  python3 "${_WH_PY}" check_auto_merge 2>/dev/null || echo "false"
}

wh_parse_closing_issues() {
  python3 "${_WH_PY}" parse_closing_issues 2>/dev/null || true
}

wh_check_assignees() {
  python3 "${_WH_PY}" check_assignees 2>/dev/null || echo "false"
}

wh_check_open_prs() {
  python3 "${_WH_PY}" check_open_prs 2>/dev/null || echo "false"
}

wh_parse_graphql_ids() {
  python3 "${_WH_PY}" parse_graphql_ids 2>/dev/null || printf '\t\t\n'
}

wh_check_mutation_errors() {
  python3 "${_WH_PY}" check_mutation_errors 2>/dev/null || echo "true"
}

wh_check_assigned() {
  python3 "${_WH_PY}" check_assigned 2>/dev/null || echo "false"
}

wh_extract_deps() {
  python3 "${_WH_PY}" extract_deps 2>/dev/null || echo ""
}

wh_extract_agent() {
  python3 "${_WH_PY}" extract_agent 2>/dev/null || echo ""
}

wh_parse_sub_issues() {
  python3 "${_WH_PY}" parse_sub_issues 2>/dev/null || true
}

wh_extract_model() {
  python3 "${_WH_PY}" extract_model 2>/dev/null || echo ""
}

wh_char_count() {
  python3 "${_WH_PY}" char_count 2>/dev/null || echo "0"
}

wh_truncate() {
  python3 "${_WH_PY}" truncate 2>/dev/null || echo ""
}
