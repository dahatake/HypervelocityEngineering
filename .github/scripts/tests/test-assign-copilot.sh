#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/../../scripts/bash/lib" && pwd)"
export GITHUB_WORKSPACE="$(cd "$(dirname "$0")/../../.." && pwd)"
export _SCRIPT_DIR="${SCRIPT_DIR}"

# テストヘルパー
PASS=0
FAIL=0
assert_eq() {
  local actual="$1" expected="$2" msg="$3"
  if [[ "${actual}" == "${expected}" ]]; then
    echo "  ✅ PASS: ${msg}"
    PASS=$((PASS + 1))
  else
    echo "  ❌ FAIL: ${msg} (expected='${expected}', actual='${actual}')"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== resolve_model tests ==="
source "${SCRIPT_DIR}/assign-copilot.sh"
assert_eq "$(resolve_model '')" "claude-opus-4.7" "empty → default"
assert_eq "$(resolve_model 'Auto')" "claude-opus-4.7" "Auto → default"
assert_eq "$(resolve_model 'claude-opus-4-7')" "claude-opus-4.7" "old format → new"
assert_eq "$(resolve_model 'gpt-5.4')" "gpt-5.4" "passthrough"
assert_eq "$(resolve_model 'claude-opus-4.6')" "claude-opus-4.6" "passthrough 4.6"

echo "=== extract-model.py tests ==="
result=$(echo '### 使用するモデル

claude-opus-4.7

### 他' | python3 "${SCRIPT_DIR}/extract-model.py")
assert_eq "${result}" "claude-opus-4.7" "extract claude-opus-4.7"

result=$(echo '### 使用するモデル

Auto

### 他' | python3 "${SCRIPT_DIR}/extract-model.py")
assert_eq "${result}" "Auto" "extract Auto"

result=$(echo 'no model section here' | python3 "${SCRIPT_DIR}/extract-model.py")
assert_eq "${result}" "" "no section → empty"

echo "=== check-assignees.py tests ==="
result=$(echo '{"assignees":[{"login":"copilot-swe-agent"}]}' | python3 "${SCRIPT_DIR}/check-assignees.py")
assert_eq "${result}" "true" "copilot assigned"

result=$(echo '{"assignees":[{"login":"someone-else"}]}' | python3 "${SCRIPT_DIR}/check-assignees.py")
assert_eq "${result}" "false" "copilot not assigned"

result=$(echo '{"assignees":[]}' | python3 "${SCRIPT_DIR}/check-assignees.py")
assert_eq "${result}" "false" "empty assignees"

echo "=== check-mutation-errors.py tests ==="
result=$(echo '{"data":{"addAssigneesToAssignable":{}}}' | python3 "${SCRIPT_DIR}/check-mutation-errors.py")
assert_eq "${result}" "false" "no errors"

result=$(echo '{"errors":[{"message":"fail"}]}' | python3 "${SCRIPT_DIR}/check-mutation-errors.py")
assert_eq "${result}" "true" "has errors"

echo ""
echo "=== Summary: ${PASS} passed, ${FAIL} failed ==="
if [[ "${FAIL}" -gt 0 ]]; then
  exit 1
fi
