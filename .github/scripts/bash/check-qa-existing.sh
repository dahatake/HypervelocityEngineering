#!/usr/bin/env bash
set -euo pipefail

ROOT_ISSUE=""
DELIVERABLE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root-issue)
      ROOT_ISSUE="${2:-}"
      shift 2
      ;;
    --deliverable)
      DELIVERABLE="${2:-}"
      shift 2
      ;;
    *)
      echo "[check-qa-existing] Unknown argument: $1" >&2
      shift
      ;;
  esac
done

if [[ -z "${ROOT_ISSUE}" ]]; then
  echo "[check-qa-existing] --root-issue is required" >&2
  echo "qa_exists=false"
  echo "matched_files="
  exit 0
fi

REPO="${GITHUB_REPOSITORY:-}"
HEAD_SHA="${GITHUB_SHA:-}"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "${TMP_DIR}"' EXIT

if [[ -z "${REPO}" || -z "${HEAD_SHA}" ]]; then
  echo "[check-qa-existing] GITHUB_REPOSITORY or GITHUB_SHA is empty" >&2
  echo "qa_exists=false"
  echo "matched_files="
  exit 0
fi

matched_files_csv=""
a_matched=false
b_matched=false

echo "[check-qa-existing] repo=${REPO} head_sha=${HEAD_SHA} root_issue=${ROOT_ISSUE} deliverable=${DELIVERABLE:-<none>}" >&2

if tree_json=$(gh api "/repos/${REPO}/git/trees/${HEAD_SHA}?recursive=1" 2>"${TMP_DIR}/check_qa_existing_tree.err"); then
  mapfile -t matched_files < <(
    printf '%s' "${tree_json}" \
      | jq -r --arg root "${ROOT_ISSUE}" '.tree[]?.path | select(test("^qa/([^/]+-)?Issue-" + $root + "-questionnaire-.*\\.md$"))'
  )
  if [[ ${#matched_files[@]} -eq 0 ]]; then
    default_branch=$(gh api "/repos/${REPO}" --jq '.default_branch' 2>"${TMP_DIR}/check_qa_existing_repo.err" || true)
    if [[ -n "${default_branch}" ]]; then
      default_sha=$(gh api "/repos/${REPO}/branches/${default_branch}" --jq '.commit.sha' 2>"${TMP_DIR}/check_qa_existing_branch.err" || true)
      if [[ -n "${default_sha}" && "${default_sha}" != "${HEAD_SHA}" ]]; then
        if default_tree_json=$(gh api "/repos/${REPO}/git/trees/${default_sha}?recursive=1" 2>"${TMP_DIR}/check_qa_existing_tree_default.err"); then
          mapfile -t matched_files < <(
            printf '%s' "${default_tree_json}" \
              | jq -r --arg root "${ROOT_ISSUE}" '.tree[]?.path | select(test("^qa/([^/]+-)?Issue-" + $root + "-questionnaire-.*\\.md$"))'
          )
        fi
      fi
    fi
  fi
  if [[ ${#matched_files[@]} -gt 0 ]]; then
    a_matched=true
    matched_files_csv=$(printf '%s\n' "${matched_files[@]}" | paste -sd ',' -)
  fi
  echo "[check-qa-existing] condition-A matched_count=${#matched_files[@]}" >&2
else
  echo "[check-qa-existing] condition-A tree API failed: $(cat "${TMP_DIR}/check_qa_existing_tree.err" 2>/dev/null || true)" >&2
fi

if [[ -n "${DELIVERABLE}" ]]; then
  encoded=$(python3 - "${DELIVERABLE}" <<'PY'
import sys, urllib.parse
print(urllib.parse.quote(sys.argv[1], safe='/'))
PY
)
  if content_json=$(gh api "/repos/${REPO}/contents/${encoded}" 2>"${TMP_DIR}/check_qa_existing_content.err"); then
    content_b64=$(printf '%s' "${content_json}" | jq -r '.content // empty' | tr -d '\n')
    if [[ -n "${content_b64}" ]]; then
      content_md=$(printf '%s' "${content_b64}" | base64 -d 2>"${TMP_DIR}/check_qa_existing_decode.err" || true)
      if [[ -n "${content_md}" ]]; then
        qa_ref_count=0
        if grep -q '<!-- qa-reference-start -->' <<<"${content_md}" && grep -q '<!-- qa-reference-end -->' <<<"${content_md}"; then
          qa_ref_section=$(printf '%s' "${content_md}" | sed -n '/<!-- qa-reference-start -->/,/<!-- qa-reference-end -->/p' | sed '1d;$d')
          if printf '%s' "${qa_ref_section}" | grep -Eq '^[[:space:]]*qa/'; then
            b_matched=true
          fi
          qa_ref_count=$(printf '%s' "${qa_ref_section}" | grep -Ec '^[[:space:]]*qa/' || true)
        fi
        echo "[check-qa-existing] condition-B qa_reference_count=${qa_ref_count}" >&2
      else
        echo "[check-qa-existing] condition-B decode produced empty markdown" >&2
      fi
    else
      echo "[check-qa-existing] condition-B deliverable content is empty or not text" >&2
    fi
  else
    echo "[check-qa-existing] condition-B contents API failed: $(cat "${TMP_DIR}/check_qa_existing_content.err" 2>/dev/null || true)" >&2
  fi
fi

qa_exists=false
if [[ "${a_matched}" == "true" || "${b_matched}" == "true" ]]; then
  qa_exists=true
fi

echo "[check-qa-existing] result qa_exists=${qa_exists} conditionA=${a_matched} conditionB=${b_matched}" >&2

echo "qa_exists=${qa_exists}"
echo "matched_files=${matched_files_csv}"
