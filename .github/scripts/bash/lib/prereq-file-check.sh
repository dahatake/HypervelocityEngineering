#!/usr/bin/env bash
# prereq-file-check.sh — GitHub Contents API を使った前提ファイル確認ヘルパー

# NOTE: sourced library. Do not change caller shell options here.

if [[ -n "${_PREREQ_FILE_CHECK_SH_LOADED:-}" ]]; then
  return 0 2>/dev/null || true
fi
readonly _PREREQ_FILE_CHECK_SH_LOADED=1

# check_prereq_file_status "$repo" "$ref" "$path"
#
# Returns:
#   0: path が存在し、Contents API の .type が "file"
#   1: HTTP 404（本当に不足）
#   2: 404 以外の確認失敗（API/通信/権限/レート制限/JSON不正/型不一致等）
#
# Globals (result):
#   PREREQ_CHECK_LAST_HTTP_STATUS
#   PREREQ_CHECK_LAST_TYPE
#   PREREQ_CHECK_LAST_REASON
#   PREREQ_CHECK_LAST_ERROR
#
# Env:
#   GH_TOKEN            (required)
#   CURL_BIN            (optional, default: curl)
#   PREREQ_MAX_RETRY    (optional, default: 3)
#   PREREQ_RETRY_DELAYS (optional, default: "1 2 4")
check_prereq_file_status() {
  local repo="$1"
  local ref="$2"
  local file_path="$3"
  local curl_bin="${CURL_BIN:-curl}"
  local max_retry="${PREREQ_MAX_RETRY:-3}"
  local retry_delays_raw="${PREREQ_RETRY_DELAYS:-1 2 4}"
  local -a retry_delays=()
  local ref_encoded=""
  local api_url=""
  local response_file=""
  local stderr_file=""
  local response_excerpt=""
  local http_status=""
  local curl_exit=0
  local attempt=1
  local content_type=""
  local parse_exit=0
  local error_summary=""
  local sleep_seconds=1

  read -r -a retry_delays <<< "${retry_delays_raw}"

  PREREQ_CHECK_LAST_HTTP_STATUS="unknown"
  PREREQ_CHECK_LAST_TYPE=""
  PREREQ_CHECK_LAST_REASON="unknown"
  PREREQ_CHECK_LAST_ERROR=""

  if [[ -z "${GH_TOKEN:-}" ]]; then
    PREREQ_CHECK_LAST_REASON="missing_gh_token"
    PREREQ_CHECK_LAST_ERROR="GH_TOKEN is not set"
    echo "::error::前提ファイル確認エラー repo=${repo} ref=${ref} path=${file_path} http_status=unknown reason=${PREREQ_CHECK_LAST_REASON}" >&2
    return 2
  fi

  ref_encoded=$(python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "${ref}")
  api_url="https://api.github.com/repos/${repo}/contents/${file_path}?ref=${ref_encoded}"

  while (( attempt <= max_retry )); do
    response_file="$(mktemp)"
    stderr_file="$(mktemp)"
    http_status="$("${curl_bin}" -sS -L -o "${response_file}" -w "%{http_code}" \
      -H "Authorization: Bearer ${GH_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      "${api_url}" 2>"${stderr_file}")" || curl_exit=$?
    response_excerpt="$(head -c 240 "${response_file}" 2>/dev/null || true)"
    error_summary="$(tr '\n' ' ' < "${stderr_file}" | sed 's/[[:space:]]\+/ /g' | cut -c1-240)"
    if (( curl_exit != 0 )); then
      PREREQ_CHECK_LAST_HTTP_STATUS="curl_exit_${curl_exit}"
      PREREQ_CHECK_LAST_REASON="curl_failure"
      PREREQ_CHECK_LAST_ERROR="${error_summary:-curl command failed}"
      if (( attempt < max_retry )); then
        sleep_seconds="${retry_delays[$((attempt - 1))]:-1}"
        echo "::warning::前提ファイル確認リトライ repo=${repo} ref=${ref} path=${file_path} http_status=${PREREQ_CHECK_LAST_HTTP_STATUS} reason=${PREREQ_CHECK_LAST_REASON} attempt=${attempt}/${max_retry} wait=${sleep_seconds}s" >&2
        sleep "${sleep_seconds}"
        rm -f "${response_file}" "${stderr_file}"
        curl_exit=0
        attempt=$((attempt + 1))
        continue
      fi
      echo "::error::前提ファイル確認エラー repo=${repo} ref=${ref} path=${file_path} http_status=${PREREQ_CHECK_LAST_HTTP_STATUS} reason=${PREREQ_CHECK_LAST_REASON} error=${PREREQ_CHECK_LAST_ERROR}" >&2
      rm -f "${response_file}" "${stderr_file}"
      return 2
    fi

    PREREQ_CHECK_LAST_HTTP_STATUS="${http_status}"

    case "${http_status}" in
      200)
        content_type=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("type",""))' < "${response_file}" 2>/dev/null) || parse_exit=$?
        if (( parse_exit != 0 )); then
          PREREQ_CHECK_LAST_REASON="json_parse_failure"
          PREREQ_CHECK_LAST_ERROR="failed to parse contents api response body"
          parse_exit=0
          if (( attempt < max_retry )); then
            sleep_seconds="${retry_delays[$((attempt - 1))]:-1}"
            echo "::warning::前提ファイル確認リトライ repo=${repo} ref=${ref} path=${file_path} http_status=${http_status} reason=${PREREQ_CHECK_LAST_REASON} attempt=${attempt}/${max_retry} wait=${sleep_seconds}s" >&2
            sleep "${sleep_seconds}"
            rm -f "${response_file}" "${stderr_file}"
            attempt=$((attempt + 1))
            continue
          fi
          echo "::error::前提ファイル確認エラー repo=${repo} ref=${ref} path=${file_path} http_status=${http_status} reason=${PREREQ_CHECK_LAST_REASON}" >&2
          rm -f "${response_file}" "${stderr_file}"
          return 2
        fi

        # shellcheck disable=SC2034 # Exposed for caller/workflow logging
        PREREQ_CHECK_LAST_TYPE="${content_type}"
        if [[ "${content_type}" == "file" ]]; then
          PREREQ_CHECK_LAST_REASON="ok"
          PREREQ_CHECK_LAST_ERROR=""
          rm -f "${response_file}" "${stderr_file}"
          return 0
        fi
        PREREQ_CHECK_LAST_REASON="contents_api_type_not_file"
        echo "::error::前提ファイル確認エラー repo=${repo} ref=${ref} path=${file_path} http_status=${http_status} type=${content_type:-unknown} reason=${PREREQ_CHECK_LAST_REASON}" >&2
        rm -f "${response_file}" "${stderr_file}"
        return 2
        ;;
      404)
        PREREQ_CHECK_LAST_REASON="contents_api_http_404"
        rm -f "${response_file}" "${stderr_file}"
        return 1
        ;;
      *)
        PREREQ_CHECK_LAST_REASON="contents_api_http_${http_status}"
        PREREQ_CHECK_LAST_ERROR="${response_excerpt}"
        if (( attempt < max_retry )); then
          sleep_seconds="${retry_delays[$((attempt - 1))]:-1}"
          echo "::warning::前提ファイル確認リトライ repo=${repo} ref=${ref} path=${file_path} http_status=${http_status} reason=${PREREQ_CHECK_LAST_REASON} attempt=${attempt}/${max_retry} wait=${sleep_seconds}s" >&2
          sleep "${sleep_seconds}"
          rm -f "${response_file}" "${stderr_file}"
          attempt=$((attempt + 1))
          continue
        fi
        echo "::error::前提ファイル確認エラー repo=${repo} ref=${ref} path=${file_path} http_status=${http_status} reason=${PREREQ_CHECK_LAST_REASON}" >&2
        rm -f "${response_file}" "${stderr_file}"
        return 2
        ;;
    esac
  done

  PREREQ_CHECK_LAST_REASON="unexpected_loop_exit"
  echo "::error::前提ファイル確認エラー repo=${repo} ref=${ref} path=${file_path} http_status=${PREREQ_CHECK_LAST_HTTP_STATUS} reason=${PREREQ_CHECK_LAST_REASON}" >&2
  return 2
}
