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
TMP_ROOT="${SCRIPT_DIR}/.tmp"
tmpdir="${TMP_ROOT}/test-bash-$$"
rm -rf "${tmpdir}"
mkdir -p "${tmpdir}"
trap 'rm -rf "${tmpdir}"' EXIT

if ! command -v jq >/dev/null 2>&1 && command -v jq.exe >/dev/null 2>&1; then
  jq() {
    jq.exe "$@" | tr -d '\r'
    return "${PIPESTATUS[0]}"
  }
  export -f jq
fi

if ! command -v shellcheck >/dev/null 2>&1 && command -v shellcheck.exe >/dev/null 2>&1; then
  shellcheck() {
    local converted=()
    local arg
    for arg in "$@"; do
      if [[ -e "$arg" ]]; then
        converted+=("$(wslpath -w "$arg")")
      else
        converted+=("$arg")
      fi
    done
    shellcheck.exe "${converted[@]}"
  }
  export -f shellcheck
fi

pass() { PASS=$((PASS + 1)); echo "  ✅ PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); ERRORS+=("$1"); echo "  ❌ FAIL: $1"; }

# ===========================================================================
# 1. shellcheck — 静的解析
# ===========================================================================
echo "=== shellcheck ==="

if command -v shellcheck &>/dev/null; then
  shellcheck_ok=true
  for f in "${BASH_DIR}"/*.sh "${BASH_DIR}"/lib/*.sh; do
    if ! case "$(basename "$f")" in
      orchestrate.sh) shellcheck -S warning -e SC2221,SC2222 "$f" ;;
      validate-plan.sh) shellcheck -S warning -e SC2034 "$f" ;;
      *) shellcheck -S warning "$f" ;;
    esac; then
      fail "shellcheck: $(basename "$f")"
      shellcheck_ok=false
    fi
  done
  if ! shellcheck -S warning "${SCRIPT_DIR}/../preflight-cloud-setup.sh"; then
    fail "shellcheck: preflight-cloud-setup.sh"
    shellcheck_ok=false
  fi
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

# 2a. Valid fixture
output=$(bash "${BASH_DIR}/validate-plan.sh" --path "${FIXTURES}/sample-plan.md" 2>&1) || true
if echo "${output}" | grep -q "PASS"; then
  pass "validate-plan: valid fixture"
else
  fail "validate-plan: valid fixture — expected PASS, got: ${output}"
fi

# 2b. Metadata-free plan without 分割判定 passes when 完了条件 has content (FR-PLAN-01 / FR-DOD-02)
cat > "${tmpdir}/plan-metadata-free.md" <<'PLAN'
# Test Plan

## 概要

No metadata comments are required.

## 完了条件

- [ ] validate-plan accepts this plan.
PLAN

output=$(bash "${BASH_DIR}/validate-plan.sh" --path "${tmpdir}/plan-metadata-free.md" 2>&1) || true
if echo "${output}" | grep -q "PASS"; then
  pass "validate-plan: metadata-free plan without 分割判定 passes"
else
  fail "validate-plan: metadata-free plan without 分割判定 passes — expected PASS, got: ${output}"
fi

# 2c. Missing '## 完了条件' section (FR-DOD-02)
cat > "${tmpdir}/plan-missing-dod.md" <<'PLAN'
# Test Plan

## 概要

No completion criteria are present.
PLAN

output=$(bash "${BASH_DIR}/validate-plan.sh" --path "${tmpdir}/plan-missing-dod.md" 2>&1) || true
if echo "${output}" | grep -q "missing required section '## 完了条件'"; then
  pass "validate-plan: detects missing 完了条件 section"
else
  fail "validate-plan: detects missing 完了条件 section — got: ${output}"
fi

# 2d. Empty '## 完了条件' section (FR-DOD-02)
cat > "${tmpdir}/plan-empty-dod.md" <<'PLAN'
# Test Plan

## 完了条件
PLAN

output=$(bash "${BASH_DIR}/validate-plan.sh" --path "${tmpdir}/plan-empty-dod.md" 2>&1) || true
if echo "${output}" | grep -q "section '## 完了条件' has no non-placeholder content"; then
  pass "validate-plan: detects empty 完了条件 section"
else
  fail "validate-plan: detects empty 完了条件 section — got: ${output}"
fi

# 2e. '## 完了条件' followed only by a horizontal rule or a NO-BREAK SPACE (FR-DOD-02)
# NBSP は glibc の C.UTF-8 で [[:space:]] に含まれないため、ロケール差で
# PowerShell / Python と判定が割れないことをここで固定する。
printf '%s\n' \
  '# Test Plan' '' '## 完了条件' '' '---' \
  > "${tmpdir}/plan-hr-dod.md"

output=$(bash "${BASH_DIR}/validate-plan.sh" --path "${tmpdir}/plan-hr-dod.md" 2>&1) || true
if echo "${output}" | grep -q "section '## 完了条件' has no non-placeholder content"; then
  pass "validate-plan: horizontal rule alone is not 完了条件 content"
else
  fail "validate-plan: horizontal rule alone is not 完了条件 content — got: ${output}"
fi

printf '%s\n' \
  '# Test Plan' '' '## 完了条件' "$(printf '\u00a0')" \
  > "${tmpdir}/plan-nbsp-dod.md"

output=$(bash "${BASH_DIR}/validate-plan.sh" --path "${tmpdir}/plan-nbsp-dod.md" 2>&1) || true
if echo "${output}" | grep -q "section '## 完了条件' has no non-placeholder content"; then
  pass "validate-plan: NO-BREAK SPACE alone is not 完了条件 content"
else
  fail "validate-plan: NO-BREAK SPACE alone is not 完了条件 content — got: ${output}"
fi

# ===========================================================================
# 3. validate-subissues.sh — dry-run テスト
# ===========================================================================
echo ""
echo "=== validate-subissues.sh ==="

# 3a. Valid subissues fixture
output=$(bash "${BASH_DIR}/validate-subissues.sh" --path "${FIXTURES}/sample-subissues.md" 2>&1) || true
if echo "${output}" | grep -q "PASS"; then
  pass "validate-subissues: valid fixture"
else
  fail "validate-subissues: valid fixture — expected PASS, got: ${output}"
fi

# 3b. Missing title metadata
cat > "${tmpdir}/subissues-missing-title.md" <<'SUBS'
<!-- subissue -->
## Sub-001
- Title: Missing metadata
SUBS

output=$(bash "${BASH_DIR}/validate-subissues.sh" --path "${tmpdir}/subissues-missing-title.md" 2>&1) || true
if echo "${output}" | grep -q "欠落ブロック"; then
  pass "validate-subissues: detects missing title metadata"
else
  fail "validate-subissues: detects missing title metadata — got: ${output}"
fi

# 3c. Missing '## 完了条件' section (FR-DOD-01)
cat > "${tmpdir}/subissues-missing-dod.md" <<'SUBS'
<!-- subissue -->
<!-- title: Sub 1 -->
## Sub-001
- 対象: X
SUBS

output=$(bash "${BASH_DIR}/validate-subissues.sh" --path "${tmpdir}/subissues-missing-dod.md" 2>&1) || true
if echo "${output}" | grep -q "'## 完了条件' 欠落ブロック"; then
  pass "validate-subissues: detects missing 完了条件 section"
else
  fail "validate-subissues: detects missing 完了条件 section — got: ${output}"
fi

# 3d. Empty '## 完了条件' section (FR-DOD-01)
cat > "${tmpdir}/subissues-empty-dod.md" <<'SUBS'
<!-- subissue -->
<!-- title: Sub 1 -->
## Sub-001
- 対象: X

## 完了条件
SUBS

output=$(bash "${BASH_DIR}/validate-subissues.sh" --path "${tmpdir}/subissues-empty-dod.md" 2>&1) || true
if echo "${output}" | grep -q "'## 完了条件' 空値・プレースホルダブロック"; then
  pass "validate-subissues: detects empty 完了条件 section"
else
  fail "validate-subissues: detects empty 完了条件 section — got: ${output}"
fi

# 3e. '## 完了条件' contains only a REPLACE_ME placeholder (FR-DOD-01)
cat > "${tmpdir}/subissues-placeholder-dod.md" <<'SUBS'
<!-- subissue -->
<!-- title: Sub 1 -->
## Sub-001
- 対象: X

## 完了条件
- [ ] {REPLACE_ME_DOD}
SUBS

output=$(bash "${BASH_DIR}/validate-subissues.sh" --path "${tmpdir}/subissues-placeholder-dod.md" 2>&1) || true
if echo "${output}" | grep -q "'## 完了条件' 空値・プレースホルダブロック"; then
  pass "validate-subissues: detects REPLACE_ME placeholder in 完了条件"
else
  fail "validate-subissues: detects REPLACE_ME placeholder in 完了条件 — got: ${output}"
fi

# 3f. '## 完了条件' followed only by a horizontal rule (FR-DOD-01)
cat > "${tmpdir}/subissues-hr-only-dod.md" <<'SUBS'
<!-- subissue -->
<!-- title: Sub 1 -->
## Sub-001
- 対象: X

## 完了条件

---
SUBS

output=$(bash "${BASH_DIR}/validate-subissues.sh" --path "${tmpdir}/subissues-hr-only-dod.md" 2>&1) || true
if echo "${output}" | grep -q "'## 完了条件' 空値・プレースホルダブロック"; then
  pass "validate-subissues: horizontal rule alone is not 完了条件 content"
else
  fail "validate-subissues: horizontal rule alone is not 完了条件 content — got: ${output}"
fi

# 3g. '## 完了条件' followed only by a NO-BREAK SPACE (FR-DOD-01)
printf '%s\n' \
  '<!-- subissue -->' '<!-- title: Sub 1 -->' '## Sub-001' '- 対象: X' \
  '' '## 完了条件' "$(printf '\u00a0')" \
  > "${tmpdir}/subissues-nbsp-dod.md"

output=$(bash "${BASH_DIR}/validate-subissues.sh" --path "${tmpdir}/subissues-nbsp-dod.md" 2>&1) || true
if echo "${output}" | grep -q "'## 完了条件' 空値・プレースホルダブロック"; then
  pass "validate-subissues: NO-BREAK SPACE alone is not 完了条件 content"
else
  fail "validate-subissues: NO-BREAK SPACE alone is not 完了条件 content — got: ${output}"
fi

# ===========================================================================
# 4. orchestrate.sh — dry-run テスト
# ===========================================================================
echo ""
echo "=== orchestrate.sh ==="

# 4a. AAS workflow dry-run
output=$(bash "${BASH_DIR}/orchestrate.sh" --workflow aas --dry-run 2>&1) || true
if echo "${output}" | grep -q "AAS" && echo "${output}" | grep -q "ドライラン"; then
  pass "orchestrate: AAS dry-run"
else
  fail "orchestrate: AAS dry-run — got: ${output}"
fi

# 4b. Unknown workflow — must show user-facing error message
output=$(bash "${BASH_DIR}/orchestrate.sh" --workflow invalid_wf --dry-run 2>&1) || true
if echo "${output}" | grep -q "不明なワークフロー"; then
  pass "orchestrate: rejects unknown workflow"
else
  fail "orchestrate: rejects unknown workflow — expected '不明なワークフロー', got: ${output}"
fi

# 4c. --model option help
output=$(bash "${BASH_DIR}/orchestrate.sh" --help 2>&1) || true
if echo "${output}" | grep -q -- "--model"; then
  pass "orchestrate: supports --model option"
else
  fail "orchestrate: supports --model option — got: ${output}"
fi

# ===========================================================================
# 5. create-subissues.sh — dry-run テスト
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
# 6. run-workflow.sh — ヘルプテスト
# ===========================================================================
echo ""
echo "=== run-workflow.sh ==="

output=$(bash "${BASH_DIR}/run-workflow.sh" help 2>&1) || true
missing_cmds=()
for cmd in "Orchestrate a workflow" advance create-subissues validate-plan validate-subissues; do
  if ! echo "${output}" | grep -q "${cmd}"; then
    missing_cmds+=("${cmd}")
  fi
done
if (( ${#missing_cmds[@]} == 0 )); then
  pass "run-workflow: help shows subcommands"
else
  fail "run-workflow: help missing subcommands [$(printf '%s, ' "${missing_cmds[@]}" | sed 's/, $//')] — got: ${output}"
fi

# ===========================================================================
# 7. auto-close.sh — 判定ロジックテスト
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
# 8. yaml-safe-helpers.sh — YAML安全ヘルパー判定テスト
# ===========================================================================
echo ""
echo "=== yaml-safe-helpers.sh ==="

output=$(bash -c '
  set -euo pipefail
  export GITHUB_WORKSPACE="'"$(cd "${SCRIPT_DIR}/../../.." && pwd)"'"
  source "'"${BASH_DIR}"'/lib/yaml-safe-helpers.sh"
  # ASCII の JSON Unicode escape に固定し、Windows Git Bash から native
  # Python へ pipe するときのコードページ変換にテスト結果を依存させない。
  json="{\"labels\":[],\"body\":\"### PR\u5b8c\u5168\u81ea\u52d5\u5316\u8a2d\u5b9a\n- [x] PR \u306e\u81ea\u52d5 Approve & Auto-merge \u3092\u6709\u52b9\u306b\u3059\u308b\"}"
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
# Windows native Python の print は Git Bash pipe 上でも CRLF を返すため、
# 行内容と順序の契約を比較する前に CR だけを正規化する。
output="${output//$'\r'/}"
if [[ "${output}" == $'12\n34' ]]; then
  pass "yaml-safe-helpers: parse closing issues unique order"
else
  fail "yaml-safe-helpers: parse closing issues unique order — got: ${output}"
fi

# ===========================================================================
# 9. prereq-file-check.sh — 前提ファイル確認ヘルパー
# ===========================================================================
echo ""
echo "=== prereq-file-check.sh ==="

if output=$(bash "${SCRIPT_DIR}/test-prereq-file-check.sh" 2>&1); then
  pass "prereq-file-check: helper return contract"
else
  fail "prereq-file-check: helper return contract — got: ${output}"
fi

# ===========================================================================
# 10. preflight-cloud-setup.sh — 基本スモークテスト
# ===========================================================================
echo ""
echo "=== preflight-cloud-setup.sh ==="

output=$(bash "${SCRIPT_DIR}/../preflight-cloud-setup.sh" --help 2>&1) || true
if echo "${output}" | grep -q "Cloud setup preflight"; then
  pass "preflight: help output"
else
  fail "preflight: help output — got: ${output}"
fi

output=$(bash "${SCRIPT_DIR}/../preflight-cloud-setup.sh" --unknown-option 2>&1) || true
if echo "${output}" | grep -q "不明なオプション"; then
  pass "preflight: rejects unknown option"
else
  fail "preflight: rejects unknown option — got: ${output}"
fi

output=$(bash "${SCRIPT_DIR}/../preflight-cloud-setup.sh" owner/repo --self-hosted-runner-label 2>&1) || true
if echo "${output}" | grep -q "オプション引数不足"; then
  pass "preflight: validates --self-hosted-runner-label argument"
else
  fail "preflight: validates --self-hosted-runner-label argument — got: ${output}"
fi

# NOTE: 認証の成否は評価せず、OWNER/REPO 引数の受理と表示のみを確認する。
output=$(GH_TOKEN=invalid GITHUB_TOKEN=invalid bash "${SCRIPT_DIR}/../preflight-cloud-setup.sh" owner/repo 2>&1) || true
if echo "${output}" | grep -q "Target repository: owner/repo"; then
  if ! echo "${output}" | grep -q "GH_TOKEN=invalid\|GITHUB_TOKEN=invalid"; then
    pass "preflight: parses OWNER/REPO argument"
  else
    fail "preflight: masks token values in output — got: ${output}"
  fi
else
  fail "preflight: parses OWNER/REPO argument — got: ${output}"
fi

if grep -q "Read and write permissions" "${SCRIPT_DIR}/../preflight-cloud-setup.sh"; then
  fail "preflight: must not require repository-wide write permissions"
elif grep -q "Read repository contents and packages" "${SCRIPT_DIR}/../preflight-cloud-setup.sh"; then
  pass "preflight: recommends read-only repository default permissions"
else
  fail "preflight: read-only default permission guidance is missing"
fi

# ===========================================================================
# 11. workflow prerequisite check safety
# ===========================================================================
echo ""
echo "=== workflow prerequisite check safety ==="

if output=$(bash "${SCRIPT_DIR}/test-workflow-prereq-checks.sh" 2>&1); then
  pass "workflow prereq checks: no dangerous contents API patterns"
else
  fail "workflow prereq checks: no dangerous contents API patterns — got: ${output}"
fi

# ===========================================================================
# 12. pr-common.sh — PR Issue 解決の回帰テスト
# ===========================================================================
echo ""
echo "=== pr-common.sh parsing ==="

output=$(printf '%s' '<!-- parent-issue: #2666 -->
body text' \
  | grep -oP '<!--\s*parent-issue:\s*#\K[0-9]+' \
  | head -1) || true
if [ "${output}" = "2666" ]; then
  pass "pr-common: Method 2.5 extracts parent-issue marker"
else
  fail "pr-common: Method 2.5 extracts parent-issue marker — got: ${output}"
fi

comments_json='[
  {
    "user": {"login": "dahatake", "type": "User"},
    "author_association": "OWNER",
    "body": "<!-- sync-issue-labels-done -->\nsource: sync-issue-labels-to-pr.yml\nIssue #2666 のラベルを同期"
  },
  {
    "user": {"login": "someone", "type": "User"},
    "body": "noise comment"
  }
]'

legacy_output=$(printf '%s' "${comments_json}" \
  | jq -rs '[.[] | .[] | select(.user.type == "Bot") | select((.user.login == "github-actions[bot]") or (.user.login == "copilot-swe-agent[bot]")) | select(.body | contains("<!-- sync-issue-labels-done -->")) | select(.body | contains("sync-issue-labels-to-pr.yml")) | .body] | .[0] // ""' \
  | grep -oP 'Issue #\K[0-9]+' \
  | head -1) || true
if [ -z "${legacy_output}" ]; then
  pass "pr-common: legacy Method 2.6 filter misses non-Bot sync comment"
else
  fail "pr-common: legacy Method 2.6 filter misses non-Bot sync comment — got: ${legacy_output}"
fi

output=$(printf '%s' "${comments_json}" \
  | jq -rs '[.[] | .[]
      | select(.body | contains("<!-- sync-issue-labels-done -->"))
      | select(.body | contains("sync-issue-labels-to-pr.yml"))
      | .body] | .[-1] // ""' \
  | grep -oP 'Issue #\K[0-9]+' \
  | head -1) || true
if [ "${output}" = "2666" ]; then
  pass "pr-common: Method 2.6 extracts issue from sync comment"
else
  fail "pr-common: Method 2.6 extracts issue from sync comment — got: ${output}"
fi

noise_comments_json='[
  {
    "user": {"login": "dahatake", "type": "User"},
    "body": "<!-- sync-issue-labels-done -->\nIssue #2666 のラベルを同期"
  },
  {
    "user": {"login": "github-actions[bot]", "type": "Bot"},
    "body": "sync-issue-labels-to-pr.yml only"
  },
  {
    "user": {"login": "someone", "type": "User"},
    "body": "plain noise"
  }
]'

output=$(printf '%s' "${noise_comments_json}" \
  | jq -rs '[.[] | .[]
      | select(.body | contains("<!-- sync-issue-labels-done -->"))
      | select(.body | contains("sync-issue-labels-to-pr.yml"))
      | .body] | .[-1] // ""' \
  | grep -oP 'Issue #\K[0-9]+' \
  | head -1) || true
if [ -z "${output}" ]; then
  pass "pr-common: Method 2.6 ignores comments missing required markers"
else
  fail "pr-common: Method 2.6 ignores comments missing required markers — got: ${output}"
fi

# 投稿者種別 / login 制限を撤廃したため、非 Bot（author_association: NONE）が投稿した
# sync-issue-labels コメントからも本文マーカーのみで Issue #N を抽出できる。
nonbot_comments_json='[
  {
    "user": {"login": "someone", "type": "User"},
    "author_association": "NONE",
    "body": "<!-- sync-issue-labels-done -->\nsource: sync-issue-labels-to-pr.yml\nIssue #2666 のラベルを同期"
  }
]'

output=$(printf '%s' "${nonbot_comments_json}" \
  | jq -rs '[.[] | .[]
      | select(.body | contains("<!-- sync-issue-labels-done -->"))
      | select(.body | contains("sync-issue-labels-to-pr.yml"))
      | .body] | .[-1] // ""' \
  | grep -oP 'Issue #\K[0-9]+' \
  | head -1) || true
if [ "${output}" = "2666" ]; then
  pass "pr-common: Method 2.6 extracts issue from non-Bot sync comment"
else
  fail "pr-common: Method 2.6 extracts issue from non-Bot sync comment — got: ${output}"
fi

done_marker_comments_json='[
  {
    "user": {"login": "attacker", "type": "User"},
    "author_association": "NONE",
    "body": "<!-- link-copilot-pr-to-issue-done -->"
  },
  {
    "user": {"login": "github-actions[bot]", "type": "Bot"},
    "author_association": "NONE",
    "body": "<!-- link-copilot-pr-to-issue-done -->"
  }
]'

output=$(printf '%s' "${done_marker_comments_json}" \
  | jq -s --arg marker "<!-- link-copilot-pr-to-issue-done -->" --arg failure "元 Issue を特定できませんでした" '[
      .[] | .[]
      | select(.body | contains($marker))
      | select((.body | contains($failure)) | not)
      | select(
          ((.user.type // "") == "Bot")
          or ((.author_association // "") == "OWNER")
          or ((.author_association // "") == "MEMBER")
          or ((.author_association // "") == "COLLABORATOR")
        )
    ] | length' 2>/dev/null) || true
if [ "${output}" = "1" ]; then
  pass "link-copilot-pr-to-issue: idempotency marker counts only trusted comments"
else
  fail "link-copilot-pr-to-issue: idempotency marker counts only trusted comments — got: ${output}"
fi

# done マーカーがあっても PR body に closing keyword が無ければ再試行（done=false）
existing="${output}"
existing_closing=""
done_flag="false"
if [ -n "${existing_closing}" ]; then
  done_flag="true"
elif [ "${existing:-0}" -gt 0 ]; then
  done_flag="false"
else
  done_flag="false"
fi
if [ "${done_flag}" = "false" ]; then
  pass "link-copilot-pr-to-issue: done marker only without closing keyword keeps done=false"
else
  fail "link-copilot-pr-to-issue: done marker only without closing keyword keeps done=false — got: ${done_flag}"
fi

# PR body に closing keyword があれば done=true（マーカー有無に依存しない）
existing_closing="2807"
done_flag="false"
if [ -n "${existing_closing}" ]; then
  done_flag="true"
elif [ "${existing:-0}" -gt 0 ]; then
  done_flag="false"
else
  done_flag="false"
fi
if [ "${done_flag}" = "true" ]; then
  pass "link-copilot-pr-to-issue: closing keyword in body sets done=true"
else
  fail "link-copilot-pr-to-issue: closing keyword in body sets done=true — got: ${done_flag}"
fi

# ===========================================================================
# 13. auto-draft-to-ready.yml — コミット活動デバウンス判定の回帰テスト
# ===========================================================================
echo ""
echo "=== auto-draft-to-ready commit debounce ==="

# カットオフを「現在から180秒前」に固定
CUTOFF_EPOCH=$(( $(date +%s) - 180 ))

# 窓内コミット（now）→ 見送り
commit_iso=$(date -u +%Y-%m-%dT%H:%M:%SZ)
commit_epoch=$(date -u -d "${commit_iso}" +%s 2>/dev/null || date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "${commit_iso}" +%s 2>/dev/null || echo "")
if [ -n "${commit_epoch}" ] && [ "${commit_epoch}" -ge "${CUTOFF_EPOCH}" ]; then
  pass "auto-draft-to-ready: recent commit within debounce window defers ready"
else
  fail "auto-draft-to-ready: recent commit within debounce window defers ready"
fi

# 窓外コミット（10分前）→ 続行
old_epoch=$(( $(date +%s) - 600 ))
if [ "${old_epoch}" -lt "${CUTOFF_EPOCH}" ]; then
  pass "auto-draft-to-ready: old commit outside debounce window proceeds"
else
  fail "auto-draft-to-ready: old commit outside debounce window proceeds"
fi

# パース失敗 → epoch 空 → 安全側（見送り）
bad_epoch=$(date -u -d "not-a-date" +%s 2>/dev/null || date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "not-a-date" +%s 2>/dev/null || echo "")
if [ -z "${bad_epoch}" ]; then
  pass "auto-draft-to-ready: unparseable commit date defers ready (fail-safe)"
else
  fail "auto-draft-to-ready: unparseable commit date defers ready (fail-safe)"
fi

# ===========================================================================
# 14. auto-draft-to-ready.yml — Initial plan ガード判定の回帰テスト
# ===========================================================================
echo ""
echo "=== auto-draft-to-ready Initial plan guard ==="

# HEAD subject == "Initial plan" → 見送り
head_subject="Initial plan"
if [ "${head_subject}" = "Initial plan" ]; then
  pass "auto-draft-to-ready: Initial plan subject defers ready"
else
  fail "auto-draft-to-ready: Initial plan subject defers ready"
fi

# HEAD subject != "Initial plan" かつ窓外コミット → 続行
head_subject_other="APP-009 データストア選定を更新"
CUTOFF_EPOCH2=$(( $(date +%s) - 180 ))
old_epoch2=$(( $(date +%s) - 600 ))
if [ "${head_subject_other}" != "Initial plan" ] && [ "${old_epoch2}" -lt "${CUTOFF_EPOCH2}" ]; then
  pass "auto-draft-to-ready: non-Initial-plan subject with old commit proceeds"
else
  fail "auto-draft-to-ready: non-Initial-plan subject with old commit proceeds"
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
