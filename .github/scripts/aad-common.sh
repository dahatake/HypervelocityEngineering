#!/usr/bin/env bash
# aad-common.sh — AAD ワークフロー共通ユーティリティ関数
#
# 前提環境変数:
#   GH_TOKEN    — GitHub API 認証トークン
#   COPILOT_PAT — Copilot アサイン用 PAT
#   REPO        — リポジトリ名（owner/repo 形式）
#
# 使い方:
#   source "${GITHUB_WORKSPACE}/.github/scripts/aad-common.sh"

# リトライ付き curl
api_call() {
  local method="$1"; shift
  local url="$1"; shift
  local data="${1:-}"
  local max_retry=5
  local wait=1
  local http_code response body

  for i in $(seq 1 "${max_retry}"); do
    if [[ -n "${data}" ]]; then
      response=$(curl -s -w "\n%{http_code}" \
        -X "${method}" \
        -H "Authorization: Bearer ${GH_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        -H "Content-Type: application/json" \
        "${url}" \
        -d "${data}")
    else
      response=$(curl -s -w "\n%{http_code}" \
        -X "${method}" \
        -H "Authorization: Bearer ${GH_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "${url}")
    fi
    http_code=$(echo "${response}" | tail -1)
    body=$(echo "${response}" | head -n -1)
    if [[ "${http_code}" =~ ^2 ]]; then
      echo "${body}"
      return 0
    fi
    echo "API エラー: HTTP ${http_code}、${wait}秒後にリトライ (${i}/${max_retry})" >&2
    sleep "${wait}"
    wait=$((wait * 2))
  done
  echo "API 呼び出し失敗: ${method} ${url}" >&2
  return 1
}

# ラベル付与
add_label() {
  local issue_num="$1"
  local label="$2"
  api_call POST \
    "https://api.github.com/repos/${REPO}/issues/${issue_num}/labels" \
    "{\"labels\":[\"${label}\"]}" > /dev/null
  sleep 1
}

# コメント投稿
post_comment() {
  local issue_num="$1"
  local comment_body="$2"
  local data
  data=$(python3 -c "import sys,json; print(json.dumps({'body': sys.argv[1]}))" "${comment_body}")
  api_call POST \
    "https://api.github.com/repos/${REPO}/issues/${issue_num}/comments" \
    "${data}" > /dev/null
  sleep 1
}

# Copilot アサイン
assign_copilot() {
  local issue_num="$1"
  local custom_agent="${2:-}"
  local base_branch="${3:-main}"
  local custom_instructions="${4:-}"

  echo "=== Copilot アサイン開始: Issue #${issue_num} ==="
  echo "  custom_agent: ${custom_agent}"
  echo "  base_branch: ${base_branch}"

  # 冪等化ガード: 既に copilot-swe-agent がアサインされている場合はスキップ
  local current_assignees
  current_assignees=$(curl -s \
    -H "Authorization: Bearer ${GH_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${REPO}/issues/${issue_num}" \
    | python3 /dev/fd/3 3<<'PY'
import sys, json
try:
    d = json.load(sys.stdin)
    if not isinstance(d, dict):
        print('false')
        sys.exit(0)
    assignees = [a.get('login', '') for a in d.get('assignees', [])]
    print('true' if 'copilot-swe-agent' in assignees or 'Copilot' in assignees else 'false')
except Exception:
    print('false')
PY
  ) || true

  if [[ "${current_assignees}" == "true" ]]; then
    echo "  copilot-swe-agent は既にアサイン済みです。スキップします。"
    return 0
  fi

  # 冪等化ガード: 対象 Issue に紐づく Open な PR が既に存在する場合はスキップ
  local existing_prs
  existing_prs=$(curl -s \
    -H "Authorization: Bearer ${GH_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${REPO}/issues/${issue_num}/timeline?per_page=100" \
    | python3 /dev/fd/3 3<<'PY'
import sys, json
try:
    events = json.load(sys.stdin)
    if not isinstance(events, list):
        print('false')
        sys.exit(0)
except Exception:
    print('false')
    sys.exit(0)
for e in events:
    if e.get('event') == 'cross-referenced':
        source = e.get('source', {}).get('issue', {})
        pr = source.get('pull_request', {})
        if pr and source.get('state') == 'open':
            print('true')
            sys.exit(0)
print('false')
PY
  ) || true

  if [[ "${existing_prs}" == "true" ]]; then
    echo "  Issue #${issue_num} に紐づく Open な PR が既に存在します。スキップします。"
    return 0
  fi

  # 冪等化ガード(フォールバック): cross-referenced が存在しない場合でも Copilot 作成の Open PR を検索
  if [[ "${existing_prs}" == "false" ]]; then
    local issue_title
    issue_title=$(curl -s \
      -H "Authorization: Bearer ${GH_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      "https://api.github.com/repos/${REPO}/issues/${issue_num}" \
      | python3 /dev/fd/3 3<<'PY'
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('title', ''))
except Exception:
    print('')
PY
    ) || issue_title=""

    if [[ -n "${issue_title}" ]]; then
      local fallback_pr_found
      fallback_pr_found=$(curl -s \
        -H "Authorization: Bearer ${GH_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "https://api.github.com/repos/${REPO}/pulls?state=open&per_page=100" \
        | ISSUE_TITLE="${issue_title}" python3 /dev/fd/3 3<<'PY'
import sys, json, os
try:
    prs = json.load(sys.stdin)
    if not isinstance(prs, list):
        print('false')
        sys.exit(0)
    issue_title = os.environ.get('ISSUE_TITLE', '')
    prefix = issue_title[:30].lower()
    for pr in prs:
        author = pr.get('user', {}).get('login', '')
        if author not in ('copilot-swe-agent', 'Copilot', 'copilot[bot]'):
            continue
        pr_title = pr.get('title', '').lower()
        if pr_title == issue_title.lower() or (prefix and pr_title.startswith(prefix)):
            print('true')
            sys.exit(0)
    print('false')
except Exception:
    print('false')
PY
      ) || fallback_pr_found="false"

      if [[ "${fallback_pr_found}" == "true" ]]; then
        echo "  Issue #${issue_num} に対応する Copilot 作成の Open PR が見つかりました（フォールバック検索）。スキップします。"
        return 0
      fi
    fi
  fi

  if [[ -z "${COPILOT_PAT:-}" ]]; then
    echo "WARNING: COPILOT_PAT が設定されていません。Copilot アサインをスキップします。" >&2
    return 1
  fi

  local OWNER="${REPO%/*}"
  local REPO_NAME="${REPO#*/}"

  local max_assign_retry=3
  local assign_wait=5
  local assign_success=false

  for assign_attempt in $(seq 1 "${max_assign_retry}"); do
    echo "  アサイン試行 ${assign_attempt}/${max_assign_retry}..."

    # 1回のクエリで bot_id / issue_node_id / repo_node_id をまとめて取得
    local query_result
    query_result=$(GH_TOKEN="${COPILOT_PAT}" gh api graphql \
      -f query="
query(\$issueNumber: Int!) {
  repository(owner: \"${OWNER}\", name: \"${REPO_NAME}\") {
    id
    issue(number: \$issueNumber) { id }
    suggestedActors(capabilities: [CAN_BE_ASSIGNED], first: 100) {
      nodes {
        login
        ... on Bot { id databaseId }
      }
    }
  }
}
      " \
      -F issueNumber="${issue_num}" \
      2>&1) || true

    echo "  GraphQL クエリ結果: ${query_result}"

    if [[ -z "${query_result}" ]]; then
      echo "WARNING: GraphQL クエリの実行に失敗しました。試行 ${assign_attempt}/${max_assign_retry}" >&2
      sleep "${assign_wait}"
      assign_wait=$((assign_wait * 2))
      continue
    fi

    local bot_id issue_node_id repo_node_id
    IFS=$'\t' read -r bot_id issue_node_id repo_node_id < <(echo "${query_result}" | python3 /dev/fd/3 3<<'PY'
import sys, json
d = json.load(sys.stdin)
repo = d.get('data', {}).get('repository', {})
bot = ''
for a in repo.get('suggestedActors', {}).get('nodes', []):
    if a.get('login') == 'copilot-swe-agent':
        bot = a.get('id', '')
        break
issue = repo.get('issue', {}).get('id', '')
print(bot + '\t' + issue + '\t' + repo.get('id', ''))
PY
    ) || true

    if [[ -z "${bot_id}" ]]; then
      echo "WARNING: copilot-swe-agent の Bot ID を取得できませんでした。試行 ${assign_attempt}/${max_assign_retry}" >&2
      sleep "${assign_wait}"
      assign_wait=$((assign_wait * 2))
      continue
    fi
    if [[ -z "${issue_node_id}" ]]; then
      echo "WARNING: Issue #${issue_num} の Node ID を取得できませんでした。試行 ${assign_attempt}/${max_assign_retry}" >&2
      sleep "${assign_wait}"
      assign_wait=$((assign_wait * 2))
      continue
    fi
    if [[ -z "${repo_node_id}" ]]; then
      echo "WARNING: Repository の Node ID を取得できませんでした。試行 ${assign_attempt}/${max_assign_retry}" >&2
      sleep "${assign_wait}"
      assign_wait=$((assign_wait * 2))
      continue
    fi
    echo "  Bot ID: ${bot_id}, Issue Node ID: ${issue_node_id}, Repo Node ID: ${repo_node_id}"

    # addAssigneesToAssignable mutation（全変数を -f/-f フラグで渡す・インジェクション防止）
    local result
    result=$(GH_TOKEN="${COPILOT_PAT}" gh api graphql \
      -H 'GraphQL-Features: issues_copilot_assignment_api_support,coding_agent_model_selection' \
      -f query="
mutation(\$assignableId: ID!, \$botId: ID!, \$targetRepositoryId: ID!, \$baseRef: String!, \$customInstructions: String!, \$customAgent: String!) {
  addAssigneesToAssignable(input: {
    assignableId: \$assignableId,
    assigneeIds: [\$botId],
    agentAssignment: {
      targetRepositoryId: \$targetRepositoryId,
      baseRef: \$baseRef,
      customInstructions: \$customInstructions,
      customAgent: \$customAgent,
      model: \"\"
    }
  }) {
    assignable {
      ... on Issue {
        id
        title
        assignees(first: 10) {
          nodes { login }
        }
      }
    }
  }
}
      " \
      -f assignableId="${issue_node_id}" \
      -f botId="${bot_id}" \
      -f targetRepositoryId="${repo_node_id}" \
      -f baseRef="${base_branch}" \
      -f customInstructions="${custom_instructions}" \
      -f customAgent="${custom_agent}" \
      2>&1) || true

    echo "  GraphQL mutation レスポンス: ${result}"

    # mutation レスポンスのエラーチェック
    local has_errors
    has_errors=$(echo "${result}" | python3 /dev/fd/3 3<<'PY'
import sys, json
try:
    d = json.load(sys.stdin)
    print('true' if d.get('errors') else 'false')
except Exception:
    print('true')
PY
    ) || true

    if [[ "${has_errors}" == "true" ]]; then
      echo "WARNING: GraphQL mutation にエラーが含まれています。試行 ${assign_attempt}/${max_assign_retry}" >&2
      sleep "${assign_wait}"
      assign_wait=$((assign_wait * 2))
      continue
    fi

    # copilot-swe-agent が assignees に含まれるか検証
    local is_assigned
    is_assigned=$(echo "${result}" | python3 /dev/fd/3 3<<'PY'
import sys, json
try:
    d = json.load(sys.stdin)
    nodes = d.get('data', {}).get('addAssigneesToAssignable', {}).get('assignable', {}).get('assignees', {}).get('nodes', [])
    print('true' if any(a.get('login') in ('copilot-swe-agent', 'Copilot') for a in nodes) else 'false')
except Exception:
    print('false')
PY
    ) || true

    if [[ "${is_assigned}" == "true" ]]; then
      echo "  copilot-swe-agent のアサインを確認しました。"
      assign_success=true
      break
    fi

    echo "WARNING: copilot-swe-agent が assignees に含まれていません。試行 ${assign_attempt}/${max_assign_retry}" >&2
    sleep "${assign_wait}"
    assign_wait=$((assign_wait * 2))
  done

  if [[ "${assign_success}" != "true" ]]; then
    local fail_msg
    fail_msg=$(printf '⚠️ Copilot cloud agent (copilot-swe-agent) を Issue #%s にアサインできませんでした。\n\n手動でアサインする手順:\n1. Issue #%s を開く\n2. 右サイドバーの「Assignees」から `copilot-swe-agent` を選択する\n\n失敗原因として考えられるもの:\n- `COPILOT_PAT` の権限不足または失効\n- Copilot cloud agent が有効化されていない\n- GraphQL API の一時的な障害' "${issue_num}" "${issue_num}")
    post_comment "${issue_num}" "${fail_msg}" || true
    echo "WARNING: Issue #${issue_num} へのアサイン失敗通知を投稿しました。" >&2
    return 1
  fi

  echo "=== Copilot アサイン完了: Issue #${issue_num} ==="
  sleep 2
}

# Issue body から Custom Agent 名を抽出
extract_custom_agent() {
  local body="$1"
  echo "${body}" | python3 /dev/fd/3 3<<'PY'
import sys, re
body = sys.stdin.read()
m = re.search(r'## Custom Agent\s*\n\s*`([^`]+)`', body)
print(m.group(1) if m else '')
PY
}
