#!/usr/bin/env python3
"""stdin から Issue body を読み取り、「使用するモデル」セクションの値を抽出する。"""
import sys, re

body = sys.stdin.read()
m = re.search(r'###\s*使用するモデル\s*\n+([^\n#]+)', body)
if not m:
    print("")
    sys.exit(0)
val = m.group(1).strip()
allowed = {"Auto", "gpt-5.5", "claude-opus-4.7", "claude-opus-4-7", "claude-opus-4.6", "claude-sonnet-4.6", "gpt-5.4", "gpt-5.3-codex", "gemini-2.5-pro"}
if val == "claude-opus-4-7":
    val = "claude-opus-4.7"
elif val == "GPT-5.5":
    val = "gpt-5.5"
print(val if val in allowed else "")
