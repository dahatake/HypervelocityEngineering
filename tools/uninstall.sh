#!/usr/bin/env bash
# Remove the Enterprise App Build Kit (EABK), installed by any version, from the current (or given) git repository.
#
#   curl -fsSL https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/uninstall.sh | bash -s -- --purge --dry-run
#   curl -fsSL https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/uninstall.sh | bash -s -- --purge
#   ./tools/uninstall.sh --target ~/src/my-app --purge                 # from a local clone
#
# Runs tools/uninstall.py with tools/uninstall-catalog.json (the content of every file every version shipped); only
# these two files are downloaded. Options are passed to uninstall.py: --dry-run, --force, --purge (also docs, the
# ledger, the config, /work, the toolkit's lines in .gitignore / .gitattributes, backups), --runs (also the old
# conductor's worktrees and merged run/* branches), --allow-non-git.
# Exit code: 0 = nothing remains in the chosen scope, 1 = something remains (RESIDUE), 2 = error.
# Environment: EBAK_REPO (default dahatake/HypervelocityEngineering), EBAK_REF (default main)
set -euo pipefail
REPO="${EBAK_REPO:-dahatake/HypervelocityEngineering}"
REF="${EBAK_REF:-main}"

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "uninstall: Python 3.9 以上が必要です" >&2; exit 2; }

DIR=""
SELF="${BASH_SOURCE[0]:-}"
if [ -n "$SELF" ] && [ -f "$SELF" ] && [ -f "$(cd "$(dirname "$SELF")" && pwd)/uninstall.py" ] \
   && [ -f "$(cd "$(dirname "$SELF")" && pwd)/uninstall-catalog.json" ]; then
  DIR="$(cd "$(dirname "$SELF")" && pwd)"
else
  command -v curl >/dev/null 2>&1 || { echo "uninstall: curl が必要です" >&2; exit 2; }
  DIR="$(mktemp -d)"
  trap 'rm -rf "$DIR"' EXIT
  for f in uninstall.py uninstall-catalog.json; do
    URL="https://raw.githubusercontent.com/${REPO}/${REF}/tools/${f}"
    echo "download: $URL"
    curl -fsSL "$URL" -o "$DIR/$f"
  done
fi

has_target=0
for a in "$@"; do [ "$a" = "--target" ] && has_target=1; done
if [ "$has_target" -eq 0 ]; then set -- --target "$(pwd)" "$@"; fi
"$PY" "$DIR/uninstall.py" "$@"
