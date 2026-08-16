#!/usr/bin/env python3
"""stdin から Issue body を読み取り、Knowledge Management マージ設定の可否を出力する。

FR-CLOUD-26: チェックが確認できない場合・節が無い場合・解釈できない場合はいずれも
`false` を出力し、非ゼロ終了しない。
"""
import re
import sys

# Issue body は常に UTF-8。locale に左右されないよう buffer から直接デコードする。
body = sys.stdin.buffer.read().decode("utf-8", errors="replace")
# 見出しは Issue Form の label（"Knowledge Management マージ設定"）と完全一致させる。
m = re.search(
    r"###\s*Knowledge Management マージ設定\s*\n(.*?)(?=\n###|\Z)", body, re.S,
)
section = m.group(1) if m else ""
print("true" if re.search(r"-\s*\[[xX]\]", section) else "false")
