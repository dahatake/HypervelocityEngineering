#!/usr/bin/env bash
# pr-common.sh — PR ワークフロー共通ユーティリティ関数
#
# 前提環境変数:
#   GH_TOKEN    — GitHub API 認証トークン
#   REPO        — リポジトリ名（owner/repo 形式）
#   OWNER       — リポジトリオーナー
#   REPO_NAME   — リポジトリ名（owner なし）
#   PR_NUMBER   — PR 番号
#   PR_BODY     — PR body テキスト（Method 2 フォールバック用）
#
# 使い方:
#   source "${GITHUB_WORKSPACE}/.github/scripts/pr-common.sh"

# PR に紐づく Issue 番号を特定する。
# 特定できた場合は ISSUE_NUMBER 変数をセットし、標準出力に出力する。
# 特定できなかった場合は ISSUE_NUMBER を空文字列のままにして 0 を返す。
#
# 前提: GH_TOKEN / OWNER / REPO_NAME / PR_NUMBER / PR_BODY が環境変数でセットされていること
#
# 戻り値:
#   0 — 常に成功（ISSUE_NUMBER が空の場合は特定失敗）
find_issue_number() {
  ISSUE_NUMBER=""

  # --- Method 1: GraphQL closingIssuesReferences ---
  echo "=== Method 1: closingIssuesReferences で Issue を検索 ==="
  local gql_result=""
  gql_result=$(gh api graphql -f query='
    query($owner: String!, $repo: String!, $pr: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $pr) {
          closingIssuesReferences(first: 10) {
            nodes {
              number
            }
          }
        }
      }
    }
  ' -f owner="${OWNER}" -f repo="${REPO_NAME}" -F pr="${PR_NUMBER}" \
    --jq '.data.repository.pullRequest.closingIssuesReferences.nodes[0].number' \
    2>/dev/null) || gql_result=""

  if [ -n "${gql_result}" ] && [ "${gql_result}" != "null" ]; then
    ISSUE_NUMBER="${gql_result}"
    echo "✅ Method 1 成功: Issue #${ISSUE_NUMBER}"
  else
    echo "Method 1 失敗: closingIssuesReferences に Issue が見つかりませんでした。"
    echo "=== Method 2: PR body から Fixes/Closes/Resolves #NNN をパース ==="
    # PR body から Fixes/Closes/Resolves #NNN を抽出
    # owner/repo#NNN 形式（例: Fixes dahatake/RepoName#123）にも対応
    ISSUE_NUMBER=$(echo "${PR_BODY}" \
      | grep -oiP '(?:fix(?:es)?|close[sd]?|resolve[sd]?)\s+(?:[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+)?#\K[0-9]+' \
      | head -1) || ISSUE_NUMBER=""

    if [ -n "${ISSUE_NUMBER}" ]; then
      echo "✅ Method 2 成功: Issue #${ISSUE_NUMBER}"
    else
      echo "Method 2 失敗: Closes/Fixes/Resolves パターンが見つかりませんでした。"
    fi
  fi

  # --- Method 2.5: PR body の <!-- parent-issue: #N --> を確認 ---
  if [ -z "${ISSUE_NUMBER}" ]; then
    echo "=== Method 2.5: PR body の <!-- parent-issue: #N --> を確認 ==="
    PARENT_ISSUE=$(echo "${PR_BODY}" \
      | grep -oP '<!--\s*parent-issue:\s*#\K[0-9]+' \
      | head -1) || PARENT_ISSUE=""
    if [ -n "${PARENT_ISSUE}" ]; then
      ISSUE_NUMBER="${PARENT_ISSUE}"
      echo "✅ Method 2.5 成功: parent-issue #${ISSUE_NUMBER}"
    else
      echo "Method 2.5 失敗: <!-- parent-issue: #N --> が見つかりませんでした。"
    fi
  fi

  # --- Method 2.7: PR body の Issue-NNN パスパターンから Issue 番号を推定 ---
  if [ -z "${ISSUE_NUMBER}" ]; then
    echo "=== Method 2.7: PR body の Issue-NNN パスパターンを確認 ==="
    PATH_ISSUE=$(echo "${PR_BODY}" \
      | grep -oP '/Issue-\K[0-9]+(?=/)' \
      | head -1) || PATH_ISSUE=""
    if [ -n "${PATH_ISSUE}" ]; then
      # Issue が実在するか API で検証（PR ではなく Issue であることも確認）
      ISSUE_STATE=$(gh api "/repos/${REPO}/issues/${PATH_ISSUE}" \
        --jq 'select(.pull_request == null) | .state' 2>/dev/null) || ISSUE_STATE=""
      if [ -n "${ISSUE_STATE}" ]; then
        ISSUE_NUMBER="${PATH_ISSUE}"
        echo "✅ Method 2.7 成功: パスパターンから Issue #${ISSUE_NUMBER}（state: ${ISSUE_STATE}）"
      else
        echo "⚠️ Method 2.7: Issue #${PATH_ISSUE} は存在しないか、削除/移動済みです（API応答なし）"
      fi
    else
      echo "Method 2.7 失敗: Issue-NNN パスパターンが見つかりませんでした。"
    fi
  fi

  # --- Method 3: Copilot アサイン元 Issue の逆引き ---
  if [ -z "${ISSUE_NUMBER}" ]; then
    echo "=== Method 3: Copilot アサイン元 Issue を検索 ==="

    PR_AUTHOR=$(gh api "/repos/${REPO}/pulls/${PR_NUMBER}" --jq '.user.login' 2>/dev/null) || PR_AUTHOR=""
    if [ "${PR_AUTHOR}" = "Copilot" ] \
      || [ "${PR_AUTHOR}" = "Copilot[bot]" ] \
      || [ "${PR_AUTHOR}" = "copilot-swe-agent" ] \
      || [ "${PR_AUTHOR}" = "copilot-swe-agent[bot]" ] \
      || [ "${PR_AUTHOR}" = "copilot[bot]" ]; then
      PR_TITLE=$(gh api "/repos/${REPO}/pulls/${PR_NUMBER}" --jq '.title' 2>/dev/null) || PR_TITLE=""

      # Copilot がアサインされている Open な Issue を検索し、タイトル一致で特定
      # copilot-swe-agent を優先して検索し、見つからなければ Copilot も検索する
      local jq_filter='[.[] | select(.pull_request == null) | ($title | .[0:30] | ascii_downcase) as $prefix | select(.title == $title or ((.title | ascii_downcase) | contains($prefix)))] | .[0].number // empty'
      CANDIDATE=$(gh api "/repos/${REPO}/issues?assignee=copilot-swe-agent&state=open&per_page=100" \
        --jq --arg title "${PR_TITLE}" \
        "${jq_filter}" \
        2>/dev/null) || CANDIDATE=""

      if [ -z "${CANDIDATE}" ] || [ "${CANDIDATE}" = "null" ]; then
        CANDIDATE=$(gh api "/repos/${REPO}/issues?assignee=Copilot&state=open&per_page=100" \
          --jq --arg title "${PR_TITLE}" \
          "${jq_filter}" \
          2>/dev/null) || CANDIDATE=""
      fi

      if [ -n "${CANDIDATE}" ] && [ "${CANDIDATE}" != "null" ]; then
        ISSUE_NUMBER="${CANDIDATE}"
        echo "✅ Method 3 成功: Issue #${ISSUE_NUMBER}（Copilot アサイン元 Issue 逆引き）"
      else
        echo "Method 3 失敗: Copilot アサイン元の一致する Issue が見つかりませんでした。"
        echo "⚠️ Issue 番号が特定できませんでした。"
      fi
    else
      echo "Method 3 スキップ: PR 作成者（${PR_AUTHOR}）は Copilot ではありません。"
      echo "⚠️ Issue 番号が特定できませんでした。"
    fi
  fi

  return 0
}
