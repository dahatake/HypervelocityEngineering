#!/usr/bin/env bash
set -euo pipefail

LIB_DIR="$(cd "$(dirname "$0")/../../scripts/bash/lib" && pwd)"
source "${LIB_DIR}/prereq-file-check.sh"

PASS=0
FAIL=0

assert_eq() {
  local actual="$1"
  local expected="$2"
  local msg="$3"
  if [[ "${actual}" == "${expected}" ]]; then
    echo "  ✅ PASS: ${msg}"
    PASS=$((PASS + 1))
  else
    echo "  ❌ FAIL: ${msg} (expected=${expected}, actual=${actual})"
    FAIL=$((FAIL + 1))
  fi
}

run_case() {
  local scenario="$1"
  local expected_rc="$2"
  local expected_status="$3"
  local expected_reason="$4"
  local expected_calls="$5"
  local rc=0
  local state_file

  state_file="$(mktemp)"
  MOCK_SCENARIO="${scenario}" \
  MOCK_STATE_FILE="${state_file}" \
  CURL_BIN="${MOCK_CURL_BIN}" \
  GH_TOKEN="dummy-token" \
  PREREQ_MAX_RETRY=3 \
  PREREQ_RETRY_DELAYS="0 0 0" \
  check_prereq_file_status "owner/repo" "main" "docs/catalog/app-catalog.md" || rc=$?

  assert_eq "${rc}" "${expected_rc}" "${scenario}: return code"
  assert_eq "${PREREQ_CHECK_LAST_HTTP_STATUS}" "${expected_status}" "${scenario}: http status"
  assert_eq "${PREREQ_CHECK_LAST_REASON}" "${expected_reason}" "${scenario}: reason"
  assert_eq "$(cat "${state_file}")" "${expected_calls}" "${scenario}: retry count"
  rm -f "${state_file}"
}

tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT

MOCK_CURL_BIN="${tmpdir}/mock-curl.sh"
cat > "${MOCK_CURL_BIN}" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail

scenario="${MOCK_SCENARIO:?}"
state_file="${MOCK_STATE_FILE:?}"
count=0
if [[ -f "${state_file}" ]]; then
  count="$(cat "${state_file}")"
fi
count=$((count + 1))
printf '%s' "${count}" > "${state_file}"

output_file=""
while (($# > 0)); do
  case "$1" in
    -o)
      output_file="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

body='{"type":"file"}'
status="200"

case "${scenario}" in
  200_file)
    body='{"type":"file"}'
    status="200"
    ;;
  404_missing)
    body='{"message":"Not Found"}'
    status="404"
    ;;
  200_dir)
    body='{"type":"dir"}'
    status="200"
    ;;
  500_error)
    body='{"message":"Server Error"}'
    status="500"
    ;;
  curl_failure)
    echo "curl: (28) Operation timed out" >&2
    exit 28
    ;;
  retry_then_200)
    if [[ "${count}" -lt 2 ]]; then
      body='{"message":"Server Error"}'
      status="500"
    else
      body='{"type":"file"}'
      status="200"
    fi
    ;;
  200_file_large)
    body="$(python3 -c 'import json; print(json.dumps({"type":"file","content":"A"*300000}))')"
    status="200"
    ;;
  *)
    echo "unknown scenario: ${scenario}" >&2
    exit 64
    ;;
esac

printf '%s' "${body}" > "${output_file}"
printf '%s' "${status}"
MOCK
chmod +x "${MOCK_CURL_BIN}"

echo "=== prereq-file-check.sh tests ==="
run_case "200_file" "0" "200" "ok" "1"
run_case "404_missing" "1" "404" "contents_api_http_404" "1"
run_case "200_dir" "2" "200" "contents_api_type_not_file" "1"
run_case "500_error" "2" "500" "contents_api_http_500" "3"
run_case "curl_failure" "2" "curl_exit_28" "curl_failure" "3"
run_case "retry_then_200" "0" "200" "ok" "2"
run_case "200_file_large" "0" "200" "ok" "1"

echo ""
echo "=== Summary: ${PASS} passed, ${FAIL} failed ==="
if [[ "${FAIL}" -gt 0 ]]; then
  exit 1
fi
