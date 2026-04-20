#!/usr/bin/env bash
# test-bash.sh — Bash CLI dry-run テスト
#
# Static analysis (shellcheck) + dry-run output verification for all commands.
#
# Usage:
#   bash .github/scripts/tests/test-bash.sh
#
# Exit code:
#   0 = all tests pass
#   1 = one or more tests failed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASH_DIR="${SCRIPT_DIR}/../bash"
FIXTURES="${SCRIPT_DIR}/fixtures"

PASS=0
FAIL=0
ERRORS=()

pass() { PASS=$((PASS + 1)); echo "  ✅ PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); ERRORS+=("$1"); echo "  ❌ FAIL: $1"; }

# ===========================================================================
# 1. shellcheck — 静的解析
# ===========================================================================
echo "=== shellcheck ==="

if command -v shellcheck &>/dev/null; then
  shellcheck_ok=true
  for f in "${BASH_DIR}"/*.sh "${BASH_DIR}"/lib/*.sh; do
    if ! shellcheck -S warning "$f"; then
      fail "shellcheck: $(basename "$f")"
      shellcheck_ok=false
    fi
  done
  if $shellcheck_ok; then
    pass "shellcheck: all scripts clean"
  fi
else
  fail "shellcheck not installed"
fi

# ===========================================================================
# 2. validate-plan — dry-run テスト
# ===========================================================================
echo ""
echo "=== validate-plan.sh ==="

# 2a. Valid PROCEED plan
output=$(bash "${BASH_DIR}/validate-plan.sh" --path "${FIXTURES}/sample-plan.md" 2>&1) || true
if echo "${output}" | grep -q "PASS"; then
  pass "validate-plan: valid PROCEED plan"
else
  fail "validate-plan: valid PROCEED plan — expected PASS, got: ${output}"
fi

# 2b. Invalid plan (missing split_decision)
tmpdir=$(mktemp -d)
trap 'rm -rf "${tmpdir}"' EXIT

cat > "${tmpdir}/plan-missing.md" <<'PLAN'
<!-- estimate_total: 10 -->
<!-- subissues_count: 0 -->
<!-- implementation_files: false -->

# Test Plan

## 分割判定
PLAN

output=$(bash "${BASH_DIR}/validate-plan.sh" --path "${tmpdir}/plan-missing.md" 2>&1) || true
if echo "${output}" | grep -q "missing required metadata.*split_decision"; then
  pass "validate-plan: detects missing split_decision"
else
  fail "validate-plan: detects missing split_decision — got: ${output}"
fi

# 2c. Estimate > 15 but PROCEED
cat > "${tmpdir}/plan-over15.md" <<'PLAN'
<!-- estimate_total: 20 -->
<!-- split_decision: PROCEED -->
<!-- subissues_count: 0 -->
<!-- implementation_files: false -->

# Test Plan

## 分割判定
PLAN

output=$(bash "${BASH_DIR}/validate-plan.sh" --path "${tmpdir}/plan-over15.md" 2>&1) || true
if echo "${output}" | grep -q "estimate=20min.*PROCEED.*SPLIT_REQUIRED"; then
  pass "validate-plan: rejects estimate>15 + PROCEED"
else
  fail "validate-plan: rejects estimate>15 + PROCEED — got: ${output}"
fi

# ===========================================================================
# 3. orchestrate.sh — dry-run テスト
# ===========================================================================
echo ""
echo "=== orchestrate.sh ==="

# 3a. AAS workflow dry-run
output=$(bash "${BASH_DIR}/orchestrate.sh" --workflow aas --dry-run 2>&1) || true
if echo "${output}" | grep -q "AAS" && echo "${output}" | grep -q "ドライラン"; then
  pass "orchestrate: AAS dry-run"
else
  fail "orchestrate: AAS dry-run — got: ${output}"
fi

# 3b. Unknown workflow — must show user-facing error message
output=$(bash "${BASH_DIR}/orchestrate.sh" --workflow invalid_wf --dry-run 2>&1) || true
if echo "${output}" | grep -q "不明なワークフロー"; then
  pass "orchestrate: rejects unknown workflow"
else
  fail "orchestrate: rejects unknown workflow — expected '不明なワークフロー', got: ${output}"
fi

# 3c. --model option help
output=$(bash "${BASH_DIR}/orchestrate.sh" --help 2>&1) || true
if echo "${output}" | grep -q -- "--model"; then
  pass "orchestrate: supports --model option"
else
  fail "orchestrate: supports --model option — got: ${output}"
fi

# ===========================================================================
# 4. create-subissues.sh — dry-run テスト
# ===========================================================================
echo ""
echo "=== create-subissues.sh ==="

# 4a. Parse sample subissues
output=$(DRY_RUN=1 bash "${BASH_DIR}/create-subissues.sh" \
  --file "${FIXTURES}/sample-subissues.md" \
  --parent-issue 99 2>&1) || true
if echo "${output}" | grep -q "3.*sub-issue" || echo "${output}" | grep -q "Found 3"; then
  pass "create-subissues: parses 3 blocks"
else
  fail "create-subissues: parses 3 blocks — got: ${output}"
fi

# 4b. Empty file
cat > "${tmpdir}/empty-subs.md" <<'EOF'
# No subissues here
EOF

output=$(DRY_RUN=1 bash "${BASH_DIR}/create-subissues.sh" \
  --file "${tmpdir}/empty-subs.md" 2>&1) || true
if echo "${output}" | grep -qi "no.*subissue.*block\|0.*block"; then
  pass "create-subissues: 0 blocks for empty file"
else
  fail "create-subissues: 0 blocks for empty file — got: ${output}"
fi

# ===========================================================================
# 5. run-workflow.sh — ヘルプテスト
# ===========================================================================
echo ""
echo "=== run-workflow.sh ==="

output=$(bash "${BASH_DIR}/run-workflow.sh" help 2>&1) || true
if echo "${output}" | grep -q "orchestrate\|advance\|create-subissues\|validate-plan"; then
  pass "run-workflow: help shows subcommands"
else
  fail "run-workflow: help shows subcommands — got: ${output}"
fi

# ===========================================================================
# 6. auto-close.sh — 判定ロジックテスト
# ===========================================================================
echo ""
echo "=== auto-close.sh ==="

output=$(bash -c '
  set -euo pipefail
  source "'"${BASH_DIR}"'/lib/auto-close.sh"
  json="{\"labels\":[{\"name\":\"auto-approve-ready\"}],\"body\":\"\"}"
  _is_auto_merge_enabled "${json}"
' 2>&1) || true
if echo "${output}" | grep -q "true"; then
  pass "auto-close: label-based auto-merge detection"
else
  fail "auto-close: label-based auto-merge detection — got: ${output}"
fi

output=$(bash -c '
  set -euo pipefail
  source "'"${BASH_DIR}"'/lib/auto-close.sh"
  json="{\"labels\":[],\"body\":\"<!-- auto-merge: true -->\"}"
  _is_auto_merge_enabled "${json}"
' 2>&1) || true
if echo "${output}" | grep -q "true"; then
  pass "auto-close: metadata-based auto-merge detection"
else
  fail "auto-close: metadata-based auto-merge detection — got: ${output}"
fi

# ===========================================================================
# 7. yaml-safe-helpers.sh — YAML安全ヘルパー判定テスト
# ===========================================================================
echo ""
echo "=== yaml-safe-helpers.sh ==="

output=$(bash -c '
  set -euo pipefail
  export GITHUB_WORKSPACE="'"$(cd "${SCRIPT_DIR}/../../.." && pwd)"'"
  source "'"${BASH_DIR}"'/lib/yaml-safe-helpers.sh"
  json="{\"labels\":[],\"body\":\"### PR完全自動化設定\n- [x] PR の自動 Approve & Auto-merge を有効にする\"}"
  echo "${json}" | wh_check_auto_merge
' 2>&1) || true
if echo "${output}" | grep -q "true"; then
  pass "yaml-safe-helpers: checkbox-based auto-merge detection"
else
  fail "yaml-safe-helpers: checkbox-based auto-merge detection — got: ${output}"
fi

output=$(bash -c '
  set -euo pipefail
  export GITHUB_WORKSPACE="'"$(cd "${SCRIPT_DIR}/../../.." && pwd)"'"
  source "'"${BASH_DIR}"'/lib/yaml-safe-helpers.sh"
  body="Fixes #12\nCloses owner/repo#34\nresolves #12"
  printf "%s" "${body}" | wh_parse_closing_issues
' 2>&1) || true
if [[ "${output}" == $'12\n34' ]]; then
  pass "yaml-safe-helpers: parse closing issues unique order"
else
  fail "yaml-safe-helpers: parse closing issues unique order — got: ${output}"
fi

# ===========================================================================
# Summary
# ===========================================================================
echo ""
echo "==========================================="
echo "  Results: ${PASS} passed, ${FAIL} failed"
echo "==========================================="

if (( FAIL > 0 )); then
  echo ""
  echo "Failures:"
  for e in "${ERRORS[@]}"; do
    echo "  - ${e}"
  done
  exit 1
fi

exit 0
