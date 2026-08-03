"""HVE adapter for the shared Code Query management section."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from PySide6.QtWidgets import QWidget

from cq.gui.settings_section import CqIndexSection as _SharedCqIndexSection

from . import settings_store


class _HveSettingsBackend:
    """Adapt HVE's process-wide settings API to the repository-aware GUI API."""

    @staticmethod
    def load(_repo_root: Path) -> dict[str, dict[str, Any]]:
        return settings_store.load()

    @staticmethod
    def save(
        _repo_root: Path, settings: dict[str, dict[str, Any]]
    ) -> None:
        settings_store.save(settings)

    parse_semicolon_list = staticmethod(settings_store.parse_semicolon_list)
    serialize_semicolon_list = staticmethod(settings_store.serialize_semicolon_list)


_HVE_SETTINGS = _HveSettingsBackend()


class CqIndexSection(_SharedCqIndexSection):
    """Shared panel with HVE's existing settings store injected."""

    def __init__(
        self, *, repo_root: Path, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(
            repo_root=repo_root,
            parent=parent,
            settings_backend=_HVE_SETTINGS,
        )


__all__ = ["CqIndexSection"]
