#!/usr/bin/env bash
# run-workflow.sh — ユーザーエントリポイント
#
# 設計ワークフロー全体実行、ステップ遷移、Copilot CLI 連携など
# すべてのコマンドを1つのスクリプトから実行できるエントリポイント。
#
# Usage:
#   # 設計ワークフロー全体実行
#   REPO=owner/repo WORKFLOW=abd BRANCH=main ./run-workflow.sh
#
#   # dry-run + ステップ限定
#   REPO=owner/repo WORKFLOW=abd STEPS=1.1,1.2 DRY_RUN=1 ./run-workflow.sh
#
#   # 完了 → 次ステップ遷移
#   REPO=owner/repo ISSUE_NO=123 ./run-workflow.sh advance
#
#   # Sub-Issue 一括作成
#   REPO=owner/repo ./run-workflow.sh create-subissues --file work/subissues.md --parent-issue 100
#
#   # Plan 検証
#   ./run-workflow.sh validate-plan --path work/Issue-123/plan.md
#
#   # Subissues 検証
#   ./run-workflow.sh validate-subissues --path work/Issue-123/subissues.md
#
#   # Copilot CLI プロンプト駆動
#   REPO=owner/repo ./run-workflow.sh copilot "仕様を整理して"
#
# Environment:
#   REPO        — Repository in "owner/repo" format
#   GH_TOKEN    — GitHub API token
#   COPILOT_PAT — Copilot assignment PAT
#   DRY_RUN     — Set to "1" for dry-run mode
#   WORKFLOW    — Workflow ID for default (orchestrate) subcommand
#   BRANCH      — Target branch (default: main)
#   STEPS       — Comma-separated step IDs
#   ISSUE_NO    — Issue number for advance subcommand

set -euo pipefail

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Copilot CLI dispatch
# ---------------------------------------------------------------------------

_dispatch_copilot() {
  local prompt="$*"

  if [[ -z "${prompt}" ]]; then
    echo "Error: copilot subcommand requires a prompt string" >&2
    echo "Usage: ./run-workflow.sh copilot \"your prompt\"" >&2
    return 1
  fi

  # Strategy 1: Try standalone `copilot` CLI
  if command -v copilot &>/dev/null; then
    echo "Using standalone copilot CLI..." >&2
    copilot "${prompt}"
    return $?
  fi

  # Strategy 2: Fallback to `gh copilot -p`
  if command -v gh &>/dev/null; then
    echo "Falling back to gh copilot..." >&2
    gh copilot -p "${prompt}"
    return $?
  fi

  echo "Error: Neither 'copilot' nor 'gh' CLI is available." >&2
  echo "Install GitHub CLI (gh) with Copilot extension:" >&2
  echo "  gh extension install github/gh-copilot" >&2
  return 1
}

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

usage() {
  cat <<'EOF'
Usage:
  run-workflow.sh [subcommand] [options]

Subcommands:
  (default)         Orchestrate a workflow (create Root + Sub-Issues)
  advance           Mark issue done and activate next steps
  create-subissues  Parse subissues.md and create GitHub Issues
  validate-plan     Validate plan.md metadata consistency
  validate-subissues Validate subissues.md metadata consistency
  copilot           Copilot CLI prompt (standalone → gh copilot fallback)
  help              Show this help

Environment Variables (for default/advance):
  REPO        Repository (owner/repo)
  WORKFLOW    Workflow ID (aas|abd|abdv)
  BRANCH      Target branch (default: main)
  STEPS       Comma-separated step IDs
  ISSUE_NO    Completed issue number (for advance)
  DRY_RUN     Set to "1" for dry-run mode

Examples:
  # Full workflow execution
  REPO=owner/repo WORKFLOW=abd BRANCH=main ./run-workflow.sh

  # Dry-run with step filter
  REPO=owner/repo WORKFLOW=abd STEPS=1.1,1.2 DRY_RUN=1 ./run-workflow.sh

  # Advance to next steps
  REPO=owner/repo ISSUE_NO=123 ./run-workflow.sh advance

  # Copilot prompt
  REPO=owner/repo ./run-workflow.sh copilot "仕様を整理して"
EOF
}

# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

main() {
  local subcommand="${1:-}"

  # Check for help first
  case "${subcommand}" in
    -h|--help|help)
      usage
      exit 0
      ;;
  esac

  # If first arg is not a known subcommand, treat as default (orchestrate)
  case "${subcommand}" in
    advance)
      shift
      # Support env-var driven mode or CLI args
      if [[ -n "${ISSUE_NO:-}" && $# -eq 0 ]]; then
        local args=(--issue "${ISSUE_NO}")
        [[ -n "${REPO:-}" ]] && args+=(--repo "${REPO}")
        [[ "${DRY_RUN:-0}" == "1" ]] && args+=(--dry-run)
        exec "${_SCRIPT_DIR}/advance.sh" "${args[@]}"
      else
        exec "${_SCRIPT_DIR}/advance.sh" "$@"
      fi
      ;;

    create-subissues)
      shift
      exec "${_SCRIPT_DIR}/create-subissues.sh" "$@"
      ;;

    validate-plan)
      shift
      exec "${_SCRIPT_DIR}/validate-plan.sh" "$@"
      ;;

    validate-subissues)
      shift
      exec "${_SCRIPT_DIR}/validate-subissues.sh" "$@"
      ;;

    copilot)
      shift
      _dispatch_copilot "$@"
      exit $?
      ;;

    *)
      # Default: orchestrate
      # If subcommand looks like an option (starts with -), pass all args to orchestrate
      if [[ -n "${subcommand}" && "${subcommand}" != -* ]]; then
        echo "Unknown subcommand: ${subcommand}" >&2
        echo "Run './run-workflow.sh help' for usage." >&2
        exit 1
      fi

      # Build orchestrate args from env vars or pass through CLI args
      local args=()
      if [[ -n "${WORKFLOW:-}" ]]; then
        args+=(--workflow "${WORKFLOW}")
        [[ -n "${BRANCH:-}" ]]   && args+=(--branch "${BRANCH}")
        [[ -n "${STEPS:-}" ]]    && args+=(--steps "${STEPS}")
        [[ -n "${REPO:-}" ]]     && args+=(--repo "${REPO}")
        [[ "${DRY_RUN:-0}" == "1" ]] && args+=(--dry-run)
        exec "${_SCRIPT_DIR}/orchestrate.sh" "${args[@]}"
      elif (( $# > 0 )); then
        # Pass all CLI args directly (including --workflow etc.)
        exec "${_SCRIPT_DIR}/orchestrate.sh" "$@"
      else
        echo "Error: WORKFLOW environment variable or --workflow option is required" >&2
        echo ""
        usage >&2
        exit 1
      fi
      ;;
  esac
}

main "$@"
