#!/usr/bin/env sh
# Usage: ./EABK-Studio/start.sh [repo-path] [port] [studio.py options...]   e.g. ./EABK-Studio/start.sh . 8765 --role pm
here="$(cd "$(dirname "$0")" && pwd)"
py="$(command -v python3 || command -v python)" || { echo "Python 3 is required." >&2; exit 1; }
repo="${1:-.}"
port="${2:-8765}"
[ $# -ge 2 ] && shift 2 || shift $#
exec "$py" "$here/studio.py" --repo "$repo" --port "$port" "$@"
