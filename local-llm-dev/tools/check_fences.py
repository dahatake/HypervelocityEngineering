"""Markdown のコードフェンス整合性を検証する。

`local-llm-dev/` 配下の Markdown で、フェンスの開閉が対応していることを確認する。
ネストしたフェンス（```markdown の中に ``` を書く）による破損を検出する目的。

    python check_fences.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FENCE = re.compile(r"^(?P<indent> *)(?P<ticks>`{3,})(?P<info>[^`]*)$")


def check_file(path: Path) -> list[str]:
    """フェンスの開閉が対応しているかを見る。開いたフェンスは同じ長さ以上の ``` で閉じる。"""
    errors: list[str] = []
    stack: list[tuple[int, int, str]] = []  # (line_no, tick_len, info)
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        m = FENCE.match(line)
        if not m:
            continue
        ticks = len(m.group("ticks"))
        info = m.group("info").strip()
        if stack and ticks >= stack[-1][1] and not info:
            stack.pop()
        elif not stack or ticks > stack[-1][1]:
            stack.append((i, ticks, info))
        # 開いているフェンスより短い ``` は、その中身の一部として扱う。
    for line_no, ticks, info in stack:
        errors.append(f"{path.relative_to(ROOT)}:{line_no}: 閉じられていないフェンス "
                      f"({'`' * ticks}{info})")
    return errors


def main() -> int:
    files = sorted(ROOT.rglob("*.md"))
    all_errors: list[str] = []
    for f in files:
        all_errors += check_file(f)
    for e in all_errors:
        print("  " + e)
    print(f"\n検査した Markdown: {len(files)} 件 / 問題: {len(all_errors)} 件")
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
