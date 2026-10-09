#!/usr/bin/env sh
# Usage: ./EABK-Studio/start.sh [repo-path] [port]
here="$(cd "$(dirname "$0")" && pwd)"
py="$(command -v python3 || command -v python)" || { echo "Python 3 is required." >&2; exit 1; }
exec "$py" "$here/studio.py" --repo "${1:-.}" --port "${2:-8765}"
