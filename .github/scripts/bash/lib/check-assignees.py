#!/usr/bin/env python3
"""stdin から Issue JSON を読み取り、copilot-swe-agent がアサイン済みか判定する。"""
import sys, json
try:
    d = json.load(sys.stdin)
    if not isinstance(d, dict):
        print('false')
        sys.exit(0)
    assignees = [a.get('login', '') for a in d.get('assignees', [])]
    print('true' if 'copilot-swe-agent' in assignees or 'Copilot' in assignees else 'false')
except Exception:
    print('false')
