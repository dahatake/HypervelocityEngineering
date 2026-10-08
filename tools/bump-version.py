#!/usr/bin/env python3
"""toolkit の版を確認・更新する。版の正本は scripts/ebaklib.py の TOOLKIT_VERSION（Semantic Versioning）。

  python tools/bump-version.py             # 現在の版を表示
  python tools/bump-version.py patch       # 0.1.0 -> 0.1.1
  python tools/bump-version.py minor       # 0.1.0 -> 0.2.0
  python tools/bump-version.py major       # 0.1.0 -> 1.0.0
  python tools/bump-version.py 0.3.0       # 版を直接指定
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "scripts" / "ebaklib.py"
CHANGELOG = ROOT / "CHANGELOG.md"
PATTERN = re.compile(r'^(TOOLKIT_VERSION\s*=\s*)"([^"]+)"', re.M)
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def current() -> str:
    m = PATTERN.search(LIB.read_text(encoding="utf-8"))
    if not m:
        raise SystemExit("ERROR bump-version: TOOLKIT_VERSION が見つかりません")
    return m.group(2)


def bump(version: str, how: str) -> str:
    if SEMVER.match(how):
        return how
    major, minor, patch = (int(x) for x in version.split("."))
    if how == "major":
        return f"{major + 1}.0.0"
    if how == "minor":
        return f"{major}.{minor + 1}.0"
    if how == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise SystemExit(f"ERROR bump-version: major / minor / patch / X.Y.Z のどれかを指定します: {how}")


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    old = current()
    if not args:
        print(old)
        return 0
    new = bump(old, args[0])
    LIB.write_text(PATTERN.sub(lambda m: f'{m.group(1)}"{new}"', LIB.read_text(encoding="utf-8"), count=1), encoding="utf-8")
    if CHANGELOG.exists():
        text = CHANGELOG.read_text(encoding="utf-8")
        marker = "## [Unreleased]\n"
        if marker in text:
            CHANGELOG.write_text(text.replace(marker, f"{marker}\n## [{new}]\n", 1), encoding="utf-8")
    print(f"{old} -> {new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
