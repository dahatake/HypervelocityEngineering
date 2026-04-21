#!/usr/bin/env python3
"""stdin から GraphQL mutation レスポンスを読み取り、エラーの有無を判定する。"""
import sys, json
try:
    d = json.load(sys.stdin)
    print('true' if d.get('errors') else 'false')
except Exception:
    print('true')
