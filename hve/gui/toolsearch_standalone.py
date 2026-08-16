"""Standalone entry point for the Tool Search settings panel (`python -m hve.gui.toolsearch_standalone`)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

__version__ = "0.1.0"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tool-search-gui",
        description="Standalone settings GUI for Tool Search in any repository.",
    )
    parser.add_argument(
        "repo_root",
        nargs="?",
        default=None,
        help="Repository root to manage (default: current working directory).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"tool-search-gui {__version__}",
    )
    args = parser.parse_args(argv)

    repo_root = (
        Path(args.repo_root).resolve() if args.repo_root else Path.cwd().resolve()
    )
    if not repo_root.is_dir():
        print(
            f"[tool-search gui] repo_root is not a directory: {repo_root}",
            file=sys.stderr,
        )
        return 2

    try:
        from PySide6.QtWidgets import QApplication, QMainWindow
    except ImportError:
        print(
            "[tool-search gui] PySide6 is not installed.\n"
            "  Install the GUI extra before launching this window.",
            file=sys.stderr,
        )
        return 2

    from .toolsearch_settings_section import ToolSearchSection

    application = QApplication.instance() or QApplication(sys.argv[:1])
    window = QMainWindow()
    window.setWindowTitle(f"Tool-Search 設定 — {repo_root}")
    window.resize(960, 760)
    window.setCentralWidget(ToolSearchSection(repo_root=repo_root, parent=window))
    window.show()
    return application.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
