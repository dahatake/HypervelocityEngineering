#!/usr/bin/env bash
# L1 deterministic verification (plan §10). Exit 0 = pass. Options are passed to verify.py.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3 >/dev/null 2>&1; then PY=python3; elif command -v python >/dev/null 2>&1; then PY=python; else
  echo "verify: Python 3.9+ が見つかりません" >&2; exit 2; fi
exec "$PY" "$DIR/verify.py" "$@"
