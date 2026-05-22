"""Entry point for ``python -m gui`` (used by launch.py).

When the launcher scripts (launch-gui.{cmd,ps1,sh}) execute ``launch.py``,
that helper inserts the Skill's vendor and root directories into
``sys.path`` and then imports ``gui.__main__:main``. The first positional
argument (optional) is the repository root to operate on; default is the
current working directory.

Direct invocation as ``python -m gui`` is supported when the Skill
directory itself is on ``sys.path``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

__version__ = "0.1.0"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="markdown-query-gui",
        description=(
            "Standalone PySide6 settings panel for the markdown-query Skill."
        ),
    )
    parser.add_argument(
        "repo_root",
        nargs="?",
        default=None,
        help="Repository root to operate on (default: current working dir).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"markdown-query-gui {__version__}",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path.cwd().resolve()
    if not repo_root.is_dir():
        print(f"[markdown-query gui] repo_root is not a directory: {repo_root}",
              file=sys.stderr)
        return 2

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "[markdown-query gui] PySide6 is not installed.\n"
            "  Run setup.ps1 (Windows) or setup.sh (Linux/macOS) to install.",
            file=sys.stderr,
        )
        return 2

    from .standalone_window import StandaloneWindow

    app = QApplication.instance() or QApplication(sys.argv[:1])
    win = StandaloneWindow(repo_root=repo_root)
    win.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
