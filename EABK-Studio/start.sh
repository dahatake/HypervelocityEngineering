#!/usr/bin/env sh
python3 "$(dirname "$0")/studio.py" --repo "${1:-.}" --no-open
