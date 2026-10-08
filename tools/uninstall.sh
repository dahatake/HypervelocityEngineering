#!/usr/bin/env bash
# Uninstall the Enterprise App Build Kit from the current (or given) git repository with one command.
#
#   curl -fsSL https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/uninstall.sh | bash
#   curl -fsSL .../tools/uninstall.sh | bash -s -- --purge --dry-run   # options are passed to install.py
#   ./tools/uninstall.sh --target ~/src/my-app                         # from a local clone
#
# Runs install.sh --uninstall. Add --purge to also remove docs, the ledger, the config, /work,
# the lines added to .gitignore / .gitattributes and *.ebak-backup-* files.
# Environment: EBAK_REPO (default dahatake/HypervelocityEngineering), EBAK_REF (default main)
set -euo pipefail
export EBAK_REPO="${EBAK_REPO:-dahatake/HypervelocityEngineering}"
export EBAK_REF="${EBAK_REF:-main}"

SELF="${BASH_SOURCE[0]:-}"
if [ -n "$SELF" ] && [ -f "$SELF" ] && [ -f "$(cd "$(dirname "$SELF")" && pwd)/install.sh" ]; then
  exec bash "$(cd "$(dirname "$SELF")" && pwd)/install.sh" --uninstall "$@"
fi
command -v curl >/dev/null 2>&1 || { echo "uninstall: curl が必要です" >&2; exit 2; }
curl -fsSL "https://raw.githubusercontent.com/${EBAK_REPO}/${EBAK_REF}/tools/install.sh" | bash -s -- --uninstall "$@"
