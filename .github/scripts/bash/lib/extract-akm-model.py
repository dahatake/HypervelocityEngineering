#!/usr/bin/env python3
"""stdin から Issue body を読み取り、「AKM 用モデル」セクションの値を抽出する。"""
import sys, re

body = sys.stdin.read()
# 見出しは Issue Form の label（"AKM 用モデル（任意）"）と完全一致させる。
# `.*?` で前方一致にすると `### AKM 用モデル<別語>` にも当たるため使わない。
m = re.search(r'###\s*AKM 用モデル（任意）\s*\n+([^\n#]+)', body)
if not m:
    print("")
    sys.exit(0)
val = m.group(1).strip()
allowed = {"Auto", "claude-opus-4.7", "claude-opus-4.6", "gpt-5.5", "gpt-5.4"}
if val == "GPT-5.5":
    val = "gpt-5.5"
print(val if val in allowed else "")
