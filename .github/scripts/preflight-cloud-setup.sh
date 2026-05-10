#!/usr/bin/env bash
set -euo pipefail

PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

REPO=""
SELF_HOSTED_RUNNER_LABEL=""

usage() {
  cat <<'USAGE'
Cloud setup preflight (GitHub CLI)

Usage:
  bash .github/scripts/preflight-cloud-setup.sh OWNER/REPO [--self-hosted-runner-label <label>]

Options:
  --self-hosted-runner-label <label>  Optional. When set, checks self-hosted runner visibility/label.
  -h, --help                          Show this help.
USAGE
}

print_status() {
  local level="$1"
  local message="$2"
  local detail="${3:-}"
  printf '[%s] %s\n' "${level}" "${message}"
  if [[ -n "${detail}" ]]; then
    printf '       %s\n' "${detail}"
  fi
}

mark_pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  print_status "PASS" "$1" "${2:-}"
}

mark_warn() {
  WARN_COUNT=$((WARN_COUNT + 1))
  print_status "WARN" "$1" "${2:-}"
}

mark_fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  print_status "FAIL" "$1" "${2:-}"
}

first_column_contains() {
  local table_text="$1"
  local target="$2"
  awk '{print $1}' <<< "${table_text}" | grep -Fxq "${target}"
}

sum_paginated_counts() {
  local endpoint="$1"
  local jq_filter="$2"
  local page_count=""
  local total=0
  while IFS= read -r page_count; do
    [[ -z "${page_count}" ]] && continue
    total=$((total + page_count))
  done < <(gh api --paginate "${endpoint}" --jq "${jq_filter}" 2>/dev/null || true)
  echo "${total}"
}

sum_paginated_counts_with_target() {
  local endpoint="$1"
  local jq_filter="$2"
  local target="$3"
  local page_count=""
  local total=0
  while IFS= read -r page_count; do
    [[ -z "${page_count}" ]] && continue
    total=$((total + page_count))
  done < <(gh api --paginate "${endpoint}" --jq "${jq_filter}" --arg target "${target}" 2>/dev/null || true)
  echo "${total}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --self-hosted-runner-label)
      if [[ $# -lt 2 || -z "${2:-}" ]]; then
        mark_fail "オプション引数不足: --self-hosted-runner-label には値が必要です。"
        usage
        exit 2
      fi
      SELF_HOSTED_RUNNER_LABEL="$2"
      shift 2
      ;;
    -*)
      mark_fail "不明なオプションです: $1"
      usage
      exit 2
      ;;
    *)
      if [[ -z "${REPO}" ]]; then
        REPO="$1"
      else
        mark_fail "リポジトリは 1 つだけ指定してください。余分な引数: $1"
        usage
        exit 2
      fi
      shift
      ;;
  esac
done

echo "=== Cloud setup preflight ==="
echo "Target repository: ${REPO:-<not-specified>}"
if [[ -n "${SELF_HOSTED_RUNNER_LABEL}" ]]; then
  echo "Self-hosted runner label check: ${SELF_HOSTED_RUNNER_LABEL}"
else
  echo "Self-hosted runner label check: (skip / option not specified)"
fi
echo

if command -v gh >/dev/null 2>&1; then
  mark_pass "GitHub CLI (gh) がインストールされています。"
else
  mark_fail "GitHub CLI (gh) が見つかりません。"
fi

if [[ -z "${REPO}" ]]; then
  mark_fail "OWNER/REPO 引数が指定されていません。"
fi

GH_READY=true
if ! command -v gh >/dev/null 2>&1; then
  GH_READY=false
fi
if ! gh auth status >/dev/null 2>&1; then
  mark_fail "gh auth status が失敗しました。"
  GH_READY=false
else
  mark_pass "gh auth status に成功しました。"
fi

REPO_ACCESSIBLE=false
if [[ "${GH_READY}" == true && -n "${REPO}" ]]; then
  if gh repo view "${REPO}" >/dev/null 2>&1; then
    mark_pass "対象リポジトリにアクセスできます。"
    REPO_ACCESSIBLE=true
  else
    mark_fail "対象リポジトリにアクセスできません。"
  fi
else
  mark_warn "前提不足のため、リポジトリアクセス確認をスキップしました。"
fi

WORKFLOW_ACCESSIBLE=false
if [[ "${REPO_ACCESSIBLE}" == true ]]; then
  if gh workflow list --repo "${REPO}" >/dev/null 2>&1; then
    mark_pass "Actions workflows を参照できます。"
    WORKFLOW_ACCESSIBLE=true
  else
    mark_fail "Actions workflows を参照できません。"
  fi
fi

if [[ "${WORKFLOW_ACCESSIBLE}" == true ]]; then
  setup_labels_found=false
  setup_labels_check_attempted=false
  setup_labels_api_succeeded=false

  if workflow_list_output="$(gh workflow list --repo "${REPO}" 2>/dev/null)"; then
    setup_labels_check_attempted=true
    if grep -Fq "Setup Labels" <<< "${workflow_list_output}"; then
      setup_labels_found=true
    fi
  fi

  if [[ "${setup_labels_found}" == false ]]; then
    if workflow_entries="$(gh api "repos/${REPO}/actions/workflows" --jq '.workflows[] | [.name, .path] | @tsv' 2>/dev/null)"; then
      setup_labels_check_attempted=true
      setup_labels_api_succeeded=true
      while IFS=$'\t' read -r workflow_name workflow_path; do
        workflow_filename="$(basename "${workflow_path}")"
        if [[ "${workflow_name}" == "Setup Labels" || "${workflow_filename}" == "setup-labels.yml" || "${workflow_filename}" == "setup-labels.yaml" ]]; then
          setup_labels_found=true
          break
        fi
      done <<< "${workflow_entries}"
    else
      mark_warn "Setup Labels workflow の存在を API で確認できませんでした。"
      print_status "INFO" "権限不足または API 制約の可能性があります。" "未配置と断定できません。Actions 一覧または `.github/workflows/setup-labels.yml` を手動確認してください。"
    fi
  fi

  if [[ "${setup_labels_found}" == true ]]; then
    mark_pass "Setup Labels workflow が存在します。"
  # NOTE: workflow list/API の照会に成功したうえで未検出の場合のみ「不存在」を確定する。
  elif [[ "${setup_labels_check_attempted}" == true && "${setup_labels_api_succeeded}" == true ]]; then
    mark_fail "Setup Labels workflow が見つかりません。"
    print_status "INFO" "テンプレートファイルのコピー漏れの可能性があります。" "`.github/workflows/setup-labels.yml` の存在を確認してください。"
  fi
fi

if [[ "${REPO_ACCESSIBLE}" == true ]]; then
  if labels_output="$(gh label list --repo "${REPO}" --limit 500 2>/dev/null)"; then
    required_labels=("setup-labels" "auto-app-selection" "auto-app-detail-design-web")
    missing_labels=()
    while IFS= read -r required_label; do
      if ! first_column_contains "${labels_output}" "${required_label}"; then
        missing_labels+=("${required_label}")
      fi
    done < <(printf '%s\n' "${required_labels[@]}")

    if [[ ${#missing_labels[@]} -eq 0 ]]; then
      mark_pass "主要ラベル（setup-labels / auto-app-selection / auto-app-detail-design-web）が存在します。"
    else
      mark_warn "主要ラベルが未作成です。初回セットアップ前なら正常です。"
      print_status "INFO" "不足ラベル: ${missing_labels[*]}" "Setup Labels workflow を Actions タブから手動実行してください。"
      print_status "INFO" "補足" "実行前に Settings → Actions → Workflow permissions が Read and write permissions であることを確認してください。"
    fi
  else
    mark_warn "ラベル一覧を取得できませんでした。"
    print_status "INFO" "権限不足または API 制約の可能性があります。" "未設定とは断定できません。GitHub UI で手動確認してください。"
  fi
fi

if [[ "${REPO_ACCESSIBLE}" == true ]]; then
  if secrets_output="$(gh secret list --repo "${REPO}" 2>/dev/null)"; then
    mark_pass "repository secrets 一覧にアクセスできました（値は表示しません）。"
    required_secrets=("COPILOT_PAT" "AZURE_CLIENT_ID" "AZURE_TENANT_ID" "AZURE_SUBSCRIPTION_ID")
    missing_secrets=()
    while IFS= read -r secret_name; do
      if ! first_column_contains "${secrets_output}" "${secret_name}"; then
        missing_secrets+=("${secret_name}")
      fi
    done < <(printf '%s\n' "${required_secrets[@]}")

    if [[ ${#missing_secrets[@]} -eq 0 ]]; then
      mark_pass "確認対象 secret 名がすべて存在します。"
    else
      mark_warn "一部 secret 名が見つかりません（値は未表示）。"
      print_status "INFO" "不足 secret: ${missing_secrets[*]}" "用途に応じて必要です。未設定を断定せず、必要性を確認してください。"
      print_status "INFO" "補足" "COPILOT_PAT は Cloud Orchestrator の Copilot 自動アサイン時に必要です。"
      print_status "INFO" "補足" "AZURE_* は Azure deploy を使う場合に必要です（全利用者の必須ではありません）。"
    fi
  else
    mark_warn "repository secrets 一覧を取得できませんでした。"
    print_status "INFO" "権限不足の可能性があります。" "未設定とは断定できません。Settings → Secrets and variables で手動確認してください。"
  fi
fi

if [[ -n "${SELF_HOSTED_RUNNER_LABEL}" && "${REPO_ACCESSIBLE}" == true ]]; then
  if runner_total="$(gh api "repos/${REPO}/actions/runners" --jq '.total_count' 2>/dev/null)"; then
    if [[ "${runner_total}" == "0" ]]; then
      mark_warn "self-hosted runner が登録されていません。"
      print_status "INFO" "GitHub-hosted runner を使う場合は問題ありません。" "self-hosted runner 利用時は users-guide/setup-self-hosted-runner.md を参照してください。"
    else
      online_count="$(sum_paginated_counts "repos/${REPO}/actions/runners?per_page=100" '[.runners[] | select(.status=="online")] | length')"
      label_match_count="$(sum_paginated_counts_with_target "repos/${REPO}/actions/runners?per_page=100" '[.runners[] | select(any(.labels[]?; .name==$target))] | length' "${SELF_HOSTED_RUNNER_LABEL}")"

      if [[ -n "${online_count}" && "${online_count}" != "0" ]]; then
        mark_pass "self-hosted runner の online 状態を確認できました。"
      else
        mark_warn "self-hosted runner の online runner が見つかりませんでした。"
      fi
      if [[ -n "${label_match_count}" && "${label_match_count}" != "0" ]]; then
        mark_pass "runner label '${SELF_HOSTED_RUNNER_LABEL}' を持つ runner を確認できました。"
      else
        mark_warn "runner label '${SELF_HOSTED_RUNNER_LABEL}' を持つ runner を確認できませんでした。"
      fi
    fi
  else
    mark_warn "self-hosted runner 情報を取得できませんでした。"
    print_status "INFO" "管理者権限が必要な場合があります。" "未設定とは断定できません。Settings → Actions → Runners で手動確認してください。"
  fi
elif [[ -z "${SELF_HOSTED_RUNNER_LABEL}" ]]; then
  mark_warn "self-hosted runner の自動確認は未実施です（オプション）。"
  print_status "INFO" "GitHub-hosted runner を使う場合はスキップ可能です。" "self-hosted runner を使う場合は --self-hosted-runner-label を指定して再実行してください。"
fi

echo
echo "=== 手動確認項目（API で断定しない） ==="
echo "- GitHub Copilot ライセンスが有効であること"
echo "- 対象リポジトリで GitHub Copilot Cloud agent が有効であること"
echo "- Settings → Copilot → Cloud agent → MCP Servers に MCP Servers が設定済みであること"
echo "- GitHub Copilot Skills が必要に応じて設定済みであること"
echo "- Settings → Actions → General → Workflow permissions が Read and write permissions であること"
echo "- self-hosted runner を使う場合、runner が online で Issue Template / workflow の runner label と一致していること"

echo
echo "=== Summary ==="
echo "PASS: ${PASS_COUNT}"
echo "WARN: ${WARN_COUNT}"
echo "FAIL: ${FAIL_COUNT}"

if (( FAIL_COUNT > 0 )); then
  echo
  echo "Preflight result: FAILED（必須チェックに失敗）"
  exit 1
fi

echo
echo "Preflight result: OK（必須チェックは成功）"
exit 0
