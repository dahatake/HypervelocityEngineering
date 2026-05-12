#!/usr/bin/env python3
"""app-arch filter の JSON 出力から error フィールドを抽出する。

stdin: app_arch_filter が出力した JSON 文字列（または不正な文字列）
stdout: error フィールドの値（存在しない・パース失敗時は空文字列）
exit code: 常に 0（呼び出し側の bash がエラー判定に使うため非ゼロを返さない）

呼び出し側との契約:
- auto-batch-design-reusable.yml / auto-batch-dev-reusable.yml などの
  _post_app_arch_filter_error() から
  `python3 .github/scripts/python/parse_filter_error.py` として呼び出される。
- 旧インライン実装（python3 -c "...") の挙動を完全に踏襲する。
"""

import json
import sys


def main() -> int:
    try:
        data = json.load(sys.stdin)
        print(data.get("error", ""))
    except Exception:
        print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
