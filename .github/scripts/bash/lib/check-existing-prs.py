#!/usr/bin/env python3
"""stdin から Issue timeline JSON を読み取り、Open な PR が存在するか判定する。"""
import sys, json
try:
    events = json.load(sys.stdin)
    if not isinstance(events, list):
        print('false')
        sys.exit(0)
except Exception:
    print('false')
    sys.exit(0)
for e in events:
    if e.get('event') == 'cross-referenced':
        source = e.get('source', {}).get('issue', {})
        pr = source.get('pull_request', {})
        if pr and source.get('state') == 'open':
            print('true')
            sys.exit(0)
print('false')
