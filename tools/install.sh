#!/usr/bin/env bash
# Install / update the Enterprise App Build Kit into the current (or given) git repository with one command.
#
#   curl -fsSL https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/install.sh | bash
#   curl -fsSL .../tools/install.sh | bash -s -- --dry-run          # options are passed to install.py
#   ./tools/install.sh --target ~/src/my-app                        # from a local clone
#
# Environment: HVE_REPO (default dahatake/HypervelocityEngineering), HVE_REF (default main)
set -euo pipefail
REPO="${HVE_REPO:-dahatake/HypervelocityEngineering}"
REF="${HVE_REF:-main}"

if command -v python3 >/dev/null 2>&1; then PY=python3; elif command -v python >/dev/null 2>&1; then PY=python; else
  echo "install: Python 3.9 以上が必要です" >&2; exit 2; fi
command -v git >/dev/null 2>&1 || { echo "install: git が必要です" >&2; exit 2; }

SRC=""
TMP=""
SELF="${BASH_SOURCE[0]:-}"
if [ -n "$SELF" ] && [ -f "$SELF" ] && [ -f "$(cd "$(dirname "$SELF")" && pwd)/install.py" ]; then
  SRC="$(cd "$(dirname "$SELF")/.." && pwd)"
else
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  URL="https://codeload.github.com/${REPO}/tar.gz/${REF}"
  echo "download: $URL"
  curl -fsSL "$URL" | tar -xz -C "$TMP"
  SRC="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  export HVE_SOURCE_LABEL="${REPO}@${REF}"
fi

has_target=0
for a in "$@"; do [ "$a" = "--target" ] && has_target=1; done
if [ "$has_target" -eq 0 ]; then set -- --target "$(pwd)" "$@"; fi
"$PY" "$SRC/tools/install.py" --source "$SRC" "$@"
