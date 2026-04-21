#!/usr/bin/env python3
"""stdin から addAssigneesToAssignable mutation レスポンスを読み取り、アサイン成功を判定する。"""
import sys, json
try:
    d = json.load(sys.stdin)
    nodes = d.get('data', {}).get('addAssigneesToAssignable', {}).get('assignable', {}).get('assignees', {}).get('nodes', [])
    print('true' if any(a.get('login') in ('copilot-swe-agent', 'Copilot') for a in nodes) else 'false')
except Exception:
    print('false')
