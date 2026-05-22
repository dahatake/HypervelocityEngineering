"""GUI font helpers.

Centralizes font selection to avoid platform-specific fallback warnings and
keep a consistent look across windows.
"""

from __future__ import annotations

import sys
from typing import Sequence

from PySide6.QtGui import QFont, QFontDatabase


def _first_available_font(candidates: Sequence[str]) -> str:
    families = set(QFontDatabase().families())
    for family in candidates:
        if family in families:
            return family
    return ""


def preferred_ui_font(point_size: int = 10) -> QFont:
    """Return the preferred application UI font for the current platform."""
    if sys.platform == "win32":
        family = _first_available_font(("Yu Gothic UI", "Segoe UI", "Meiryo", "Arial"))
    elif sys.platform == "darwin":
        family = _first_available_font(("SF Pro Text", "Helvetica Neue", "Helvetica"))
    else:
        family = _first_available_font(("Noto Sans", "DejaVu Sans", "Ubuntu"))

    if family:
        return QFont(family, point_size)

    font = QFont()
    font.setPointSize(point_size)
    return font


def preferred_log_font(point_size: int = 10) -> QFont:
    """Return a readable log font that avoids generic monospace fallback."""
    if sys.platform == "win32":
        family = _first_available_font(("Yu Gothic UI", "Segoe UI", "Meiryo", "Arial"))
    elif sys.platform == "darwin":
        family = _first_available_font(("Menlo", "SF Mono", "Monaco"))
    else:
        family = _first_available_font(("DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono"))

    if family:
        return QFont(family, point_size)

    font = QFont()
    font.setPointSize(point_size)
    return font
