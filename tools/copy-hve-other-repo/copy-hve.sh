#!/usr/bin/env bash
# macOS launcher for copy_hve.py. All selection and deletion logic is shared.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENTRY="${SCRIPT_DIR}/copy_hve.py"

if [[ ! -f "${ENTRY}" ]]; then
  printf 'copy_hve.py not found: %s\n' "${ENTRY}" >&2
  exit 2
fi

if [[ $# -lt 1 ]]; then
  printf 'Usage: bash copy-hve.sh DESTINATION [--dry-run] [--yes]\n' >&2
  exit 2
fi

if [[ -n "${PYTHON:-}" ]]; then
  PYTHON_BIN="${PYTHON}"
elif [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  printf 'Python 3.11+ was not found. Run hve/setup-hve.sh first.\n' >&2
  exit 2
fi

exec "${PYTHON_BIN}" "${ENTRY}" "$@"