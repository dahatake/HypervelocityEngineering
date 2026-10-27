#!/usr/bin/env sh
# Double-click to start EABK Studio (macOS). Repo = the folder containing this file.
here="$(cd "$(dirname "$0")" && pwd)"
py="$(command -v python3 || command -v python)" || {
  echo "Python 3 is required. Install it from https://www.python.org/downloads/" >&2
  printf 'Press Enter to close...'; read -r _
  exit 1
}
"$py" "$here/EABK-Studio/studio.py" --repo "$here" --port 8765 "$@"
status=$?
[ $status -ne 0 ] && { printf 'Press Enter to close...'; read -r _; }
exit $status
