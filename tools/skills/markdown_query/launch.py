"""launch.py — Standalone entry point for the Markdown-Query GUI.

Unlike ``python -m tools.skills.markdown_query.gui`` (which requires the
``tools/skills/markdown_query/`` path structure to exist), this launcher
works no matter what directory name the Skill is copied into, because it
resolves its own location and injects the right paths into ``sys.path``.

Used by ``launch-gui.{cmd,ps1,sh}``.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    here = Path(__file__).resolve().parent
    vendor = here / "vendor"

    # 1) Make the vendored ``mdq`` package importable.
    if vendor.is_dir() and str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))

    # 2) Make ``gui`` (sibling directory) importable as a top-level package.
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))

    try:
        # Now ``import gui`` and ``from gui.<...>`` work regardless of the
        # outer directory name.
        from gui.__main__ import main as gui_main  # type: ignore
    except ImportError as e:
        print(f"[launch] failed to import gui: {e}", file=sys.stderr)
        return 2

    return gui_main()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
