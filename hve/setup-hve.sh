#!/usr/bin/env bash
set -u

CHECK_ONLY=false
WITH_WORKIQ=false
INSTALL_EXTERNAL_COPILOT_CLI=false
FORCE_RECREATE_VENV=false
WARNING_COUNT=0

usage() {
  cat <<'USAGE'
Usage: ./hve/setup-hve.sh [options]

Options:
  --check-only                    Report current state without changing files.
  --with-workiq                   Check Node.js/npm/npx prerequisites for Work IQ.
  --install-external-copilot-cli  Install/check external copilot CLI via Homebrew when needed.
  --force-recreate-venv           Recreate .venv if it exists with an unsupported Python.
  -h, --help                      Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check-only) CHECK_ONLY=true ;;
    --with-workiq) WITH_WORKIQ=true ;;
    --install-external-copilot-cli) INSTALL_EXTERNAL_COPILOT_CLI=true ;;
    --force-recreate-venv) FORCE_RECREATE_VENV=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

step() { printf '\n==> %s\n' "$1"; }
warn() { WARNING_COUNT=$((WARNING_COUNT + 1)); printf 'WARNING: %s\n' "$1" >&2; }
die() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }

run() {
  printf '> '
  printf '%q ' "$@"
  printf '\n'
  "$@" || die "Command failed: $*"
}

python_info() {
  "$1" -c 'import sys; print(sys.executable); print(f"{sys.version_info.major} {sys.version_info.minor} {sys.version_info.micro}")' 2>/dev/null
}

python_is_311_or_newer() {
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null
}

find_python311() {
  local candidate
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && python_is_311_or_newer "$candidate"; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python"

cd "$REPO_ROOT" || exit 1

step "Checking required tools"
if command -v git >/dev/null 2>&1; then
  printf 'Git: %s\n' "$(command -v git)"
else
  warn "Git was not found. Install Git before cloning or updating the repository."
fi

if command -v gh >/dev/null 2>&1; then
  printf 'GitHub CLI: %s\n' "$(command -v gh)"
else
  warn "GitHub CLI was not found. Install it from https://cli.github.com/."
fi

PYTHON_BIN=""
if PYTHON_BIN="$(find_python311)"; then
  readarray -t PY_INFO < <(python_info "$PYTHON_BIN")
  printf 'Python: %s (%s)\n' "${PY_INFO[0]}" "${PY_INFO[1]}"
else
  warn "Python 3.11+ was not found. Install Python 3.11 or newer and rerun this script."
  if [[ "$CHECK_ONLY" != true ]]; then exit 1; fi
fi

if [[ "$WITH_WORKIQ" == true ]]; then
  step "Checking Work IQ prerequisites"
  for tool in node npm npx; do
    if command -v "$tool" >/dev/null 2>&1; then
      printf '%s: %s\n' "$tool" "$(command -v "$tool")"
    else
      warn "$tool was not found. Work IQ requires Node.js/npm/npx."
    fi
  done
  printf 'Work IQ may require Microsoft 365 sign-in, EULA acceptance, and Entra ID admin consent.\n'
fi

if [[ "$INSTALL_EXTERNAL_COPILOT_CLI" == true ]]; then
  step "Checking external Copilot CLI"
  if command -v copilot >/dev/null 2>&1; then
    printf 'External Copilot CLI: %s\n' "$(command -v copilot)"
  elif [[ "$CHECK_ONLY" == true ]]; then
    warn "External Copilot CLI was not found. It is optional unless COPILOT_CLI_PATH or --cli-path is used."
  elif command -v brew >/dev/null 2>&1; then
    run brew install copilot-cli
  else
    warn "Homebrew was not found. Install Copilot CLI manually from GitHub Docs."
  fi
fi

step "Checking Python virtual environment"
if [[ -x "$VENV_PYTHON" ]]; then
  if python_is_311_or_newer "$VENV_PYTHON"; then
    readarray -t VENV_INFO < <(python_info "$VENV_PYTHON")
    printf 'Existing .venv Python: %s\n' "${VENV_INFO[1]}"
  elif [[ "$FORCE_RECREATE_VENV" == true && "$CHECK_ONLY" != true ]]; then
    warn "Existing .venv is older than Python 3.11. Recreating because --force-recreate-venv was specified."
    rm -rf "$VENV_DIR"
  else
    warn "Existing .venv is older than Python 3.11. Rerun with --force-recreate-venv to recreate it."
    if [[ "$CHECK_ONLY" != true ]]; then exit 1; fi
  fi
elif [[ "$CHECK_ONLY" == true ]]; then
  warn ".venv does not exist. Run without --check-only to create it."
fi

if [[ "$CHECK_ONLY" != true && ! -x "$VENV_PYTHON" ]]; then
  [[ -n "$PYTHON_BIN" ]] || die "Python 3.11+ is required to create .venv."
  run "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

if [[ -x "$VENV_PYTHON" ]]; then
  if [[ "$CHECK_ONLY" != true ]]; then
    step "Installing Python dependencies"
    run "$VENV_PYTHON" -m pip install --upgrade pip
    run "$VENV_PYTHON" -m pip install --upgrade github-copilot-sdk
  fi

  step "Verifying HVE runtime"
  if "$VENV_PYTHON" -c 'import copilot' >/dev/null 2>&1; then
    printf 'github-copilot-sdk import: OK\n'
  else
    warn "github-copilot-sdk import failed. Run without --check-only to install dependencies."
  fi
  if "$VENV_PYTHON" -m hve --help >/dev/null 2>&1; then
    printf 'python -m hve --help: OK\n'
  else
    warn "python -m hve --help failed."
  fi
fi

if command -v gh >/dev/null 2>&1; then
  step "Checking GitHub authentication"
  if gh auth status >/dev/null 2>&1; then
    printf 'gh auth status: OK\n'
  else
    warn "gh auth status failed. Run 'gh auth login' before using GitHub operations."
  fi
fi

if [[ "$CHECK_ONLY" == true ]]; then
  printf '\nCheck-only completed with %s warning(s).\n' "$WARNING_COUNT"
else
  printf '\nHVE setup completed with %s warning(s).\n' "$WARNING_COUNT"
fi
