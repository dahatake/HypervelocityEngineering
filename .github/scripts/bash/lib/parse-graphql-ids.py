#!/usr/bin/env python3
"""stdin から GraphQL レスポンスを読み取り、bot_id, issue_node_id, repo_node_id をTSV出力する。"""
import sys, json
try:
    d = json.load(sys.stdin)
    repo = d.get('data', {}).get('repository', {})
    bot = ''
    for a in repo.get('suggestedActors', {}).get('nodes', []):
        if a.get('login') == 'copilot-swe-agent':
            bot = a.get('id', '')
            break
    issue = repo.get('issue', {}).get('id', '')
    print(bot + '\t' + issue + '\t' + repo.get('id', ''))
except Exception as e:
    print(f'Python parse error: {e}', file=sys.stderr)
    print('\t\t')
