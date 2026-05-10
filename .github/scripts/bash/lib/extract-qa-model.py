#!/usr/bin/env python3
"""stdin から Issue body を読み取り、「QA 用モデル」セクションの値を抽出する。"""
import sys, re

body = sys.stdin.read()
m = re.search(r'###\s*QA 用モデル.*?\n+([^\n#]+)', body)
if not m:
    print("")
    sys.exit(0)
val = m.group(1).strip()
allowed = {"Auto", "claude-opus-4.7", "claude-opus-4.6", "gpt-5.5", "gpt-5.4"}
if val == "GPT-5.5":
    val = "gpt-5.5"
print(val if val in allowed else "")
