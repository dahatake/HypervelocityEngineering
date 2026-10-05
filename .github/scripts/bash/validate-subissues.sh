#!/usr/bin/env bash
# validate-subissues.sh — subissues.md メタデータ検証
#
# Validates:
#   1. Each <!-- subissue --> block has <!-- title: ... -->
#   2. title value is not empty
# Error format:
#   Validation errors are emitted as "::error::<message>" for GitHub Actions
#   workflow compatibility (.github/workflows/validate-subissues.yml).
#
# Usage:
#   ./validate-subissues.sh --path work/Issue-123/subissues.md
#   ./validate-subissues.sh --directory work/

set -euo pipefail

# FR-DOD-01: `## 完了条件` の「空とみなす文字」クラス（ブラケット式の中身のみ）。
# glibc の C.UTF-8 では `[[:space:]]` が NO-BREAK SPACE (U+00A0) を空白と見なさず、
# .NET / Python の `\s` とは判定が割れる。両者を一致させるため明示的に追加する。
_BLANK_CLASS="[:space:]$(printf '\u00a0')"

validate() {
  local subissues_path="$1"
  local errors=()

  if [[ ! -f "${subissues_path}" ]]; then
    echo "Error: ${subissues_path} not found" >&2
    return 1
  fi
  echo "Checking: ${subissues_path}"

  local tmp_dir
  if ! tmp_dir=$(mktemp -d 2>/dev/null); then
    tmp_dir=$(mktemp -d -t validate_subissue_block 2>/dev/null) || {
      echo "Error: failed to create temporary directory (mktemp)" >&2
      return 1
    }
  fi
  trap '[[ -n "${tmp_dir:-}" ]] && rm -rf "${tmp_dir}"' RETURN
  local tmp_prefix="${tmp_dir}/block_"

  awk -v prefix="${tmp_prefix}" '
    /^<!-- subissue -->/ {
      blocknum++
      outfile = prefix blocknum ".txt"
      next
    }
    blocknum > 0 {
      print > outfile
    }
  ' "${subissues_path}"

  shopt -s nullglob
  local block_files=("${tmp_prefix}"*.txt)
  shopt -u nullglob
  local block_count=${#block_files[@]}

  if [[ "${block_count}" -eq 0 ]]; then
    # P-C: Markdown テーブル形式で書かれた subissues.md を検知してエラー化する。
    # 連続する 3 行以上の `^\s*\|.*\|\s*$` パターンを検出した場合、Agent が
    # `task-dag-planning` Skill を読まずにテーブル形式で生成した可能性が高い。
    if awk '
      /^[[:space:]]*\|.*\|[[:space:]]*$/ {
        consecutive++
        if (consecutive >= 3) { found = 1; exit }
        next
      }
      { consecutive = 0 }
      END { exit (found ? 0 : 1) }
    ' "${subissues_path}"; then
      echo "::error::${subissues_path}: \`<!-- subissue -->\` ブロックが 0 件 だが Markdown テーブル形式が検出されました。テーブル形式は禁止です。各行を \`<!-- subissue -->\` ブロックに展開してください。規約: .github/skills/_hve-plan-artifacts/subissues-template.md" >&2
      return 1
    fi
    echo "  ⚠️ No <!-- subissue --> blocks found"
    return 0
  fi

  local missing_blocks=""
  local empty_title_blocks=""
  local missing_dod_blocks=""
  local empty_dod_blocks=""
  local block_file block_idx title_line title_value dod_lines
  while IFS= read -r block_file; do
    [[ -f "${block_file}" ]] || continue
    block_idx=$(basename "${block_file}" .txt | grep -oE '[0-9]+$')
    title_line=$(grep -m1 -E '<!--[[:space:]]*title:[[:space:]]*.*-->' "${block_file}" || true)
    if [[ -z "${title_line}" ]]; then
      missing_blocks="${missing_blocks}${missing_blocks:+,}${block_idx}"
    else
      title_value=$(printf '%s' "${title_line}" \
        | sed -E 's/^[[:space:]]*<!--[[:space:]]*title:[[:space:]]*//; s/[[:space:]]*-->[[:space:]]*$//')
      title_value=$(printf '%s' "${title_value}" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')
      if [[ -z "${title_value}" ]]; then
        empty_title_blocks="${empty_title_blocks}${empty_title_blocks:+,}${block_idx}"
      fi
    fi

    # FR-DOD-01: `## 完了条件` セクションと、その配下の非空・非プレースホルダ記述を検査する。
    if ! grep -qE '^[[:space:]]*##[[:space:]]+完了条件' "${block_file}"; then
      missing_dod_blocks="${missing_dod_blocks}${missing_dod_blocks:+,}${block_idx}"
      continue
    fi
    dod_lines=$(awk '
      /^[[:space:]]*##[[:space:]]+完了条件/ { inside = 1; next }
      inside && /^[[:space:]]*##[[:space:]]/ { inside = 0 }
      inside { print }
    ' "${block_file}" | grep -vE "^[${_BLANK_CLASS}]*(-{3,})?[${_BLANK_CLASS}]*$" | grep -viE 'REPLACE_ME' || true)
    if [[ -z "${dod_lines}" ]]; then
      empty_dod_blocks="${empty_dod_blocks}${empty_dod_blocks:+,}${block_idx}"
    fi
  done < <(printf '%s\n' "${block_files[@]}" | sort -V)

  if [[ -n "${missing_blocks}" ]]; then
    errors+=("${subissues_path}: <!-- title: ... --> 欠落ブロック = [${missing_blocks}]")
  fi
  if [[ -n "${empty_title_blocks}" ]]; then
    errors+=("${subissues_path}: <!-- title: ... --> 空値ブロック = [${empty_title_blocks}]")
  fi
  if [[ -n "${missing_dod_blocks}" ]]; then
    errors+=("${subissues_path}: '## 完了条件' 欠落ブロック = [${missing_dod_blocks}]")
  fi
  if [[ -n "${empty_dod_blocks}" ]]; then
    errors+=("${subissues_path}: '## 完了条件' 空値・プレースホルダブロック = [${empty_dod_blocks}]")
  fi

  if (( ${#errors[@]} > 0 )); then
    local err
    for err in "${errors[@]}"; do
      echo "::error::${err}" >&2
    done
    return 1
  fi

  echo "  ✅ PASS"
  return 0
}

validate_directory() {
  local directory="$1"
  local subissues_files
  subissues_files=$(find "${directory}" -name "subissues.md" -type f | sort) || true

  if [[ -z "${subissues_files}" ]]; then
    echo "No subissues.md files found under ${directory}"
    return 0
  fi

  local all_ok=0
  local subissues_path
  while IFS= read -r subissues_path; do
    if ! validate "${subissues_path}"; then
      all_ok=1
    fi
  done <<< "${subissues_files}"

  return "${all_ok}"
}

usage() {
  cat <<'EOF'
Usage:
  validate-subissues.sh --path <subissues.md>
  validate-subissues.sh --directory <dir>

Options:
  --path <path>       Validate a single subissues.md file
  --directory <dir>   Recursively find and validate all subissues.md files
  -h, --help          Show this help
EOF
}

main() {
  local mode="" target=""

  while (( $# > 0 )); do
    case "$1" in
      --path)
        mode="path"
        target="${2:?--path requires an argument}"
        shift 2
        ;;
      --directory)
        mode="directory"
        target="${2:?--directory requires an argument}"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "Unknown option: $1" >&2
        usage >&2
        exit 1
        ;;
    esac
  done

  if [[ -z "${mode}" ]]; then
    echo "Error: --path or --directory is required" >&2
    usage >&2
    exit 1
  fi

  if [[ "${mode}" == "path" ]]; then
    validate "${target}"
  else
    validate_directory "${target}"
  fi
}

main "$@"
