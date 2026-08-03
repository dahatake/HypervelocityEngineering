"""Expose the single validation-marker decision to the cloud surface (FR-MAINT-06).

`hve/split_fork.py` owns the decision. This entrypoint only adapts it to a shell
caller, so GitHub Actions workflows never re-implement the marker patterns.

Exit code 0 when a marker is present, 1 when it is absent, 2 on usage errors.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Callable

_DECISION_MODULE = Path(__file__).resolve().parents[2] / "hve" / "split_fork.py"


def _load_decision() -> Callable[..., bool]:
    # パッケージ初期化（SDK 依存を含む hve/__init__.py）を避けて単体ロードする。
    spec = importlib.util.spec_from_file_location("hve_validation_marker_decision", _DECISION_MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load validation marker decision: {_DECISION_MODULE}")
    module = importlib.util.module_from_spec(spec)
    # dataclass の解決が sys.modules を参照するため、実行前に登録する。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.has_validation_marker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text-file", required=True, type=Path)
    parser.add_argument("--html-comment-only", action="store_true")
    args = parser.parse_args(argv)

    try:
        text = args.text_file.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"cannot read subject text: {exc}", file=sys.stderr)
        return 2

    try:
        has_validation_marker = _load_decision()
    except (OSError, RuntimeError, AttributeError) as exc:
        print(f"cannot load validation marker decision: {exc}", file=sys.stderr)
        return 2

    return 0 if has_validation_marker(text, html_comment_only=args.html_comment_only) else 1


if __name__ == "__main__":
    raise SystemExit(main())
