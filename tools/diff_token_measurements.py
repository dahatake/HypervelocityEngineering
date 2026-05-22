#!/usr/bin/env python3
"""before / after の起動時トークン比較レポート生成。"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    tools_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(tools_dir))
    from compare_startup_tokens import main as compare_main

    return compare_main()


if __name__ == "__main__":
    raise SystemExit(main())
