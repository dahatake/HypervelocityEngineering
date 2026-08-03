"""HVE adapter for the shared Markdown Query management section."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from PySide6.QtWidgets import QWidget

from mdq.gui.settings_section import MdqIndexSection as _SharedMdqIndexSection

from . import settings_store


class _HveSettingsBackend:
    """Adapt HVE's process-wide settings API to the repository-aware GUI API."""

    @staticmethod
    def load(_repo_root: Path) -> dict[str, dict[str, Any]]:
        return settings_store.load()

    @staticmethod
    def save(_repo_root: Path, settings: dict[str, dict[str, Any]]) -> None:
        settings_store.save(settings)

    @staticmethod
    def get_mdq_target_folders(_repo_root: Path) -> list[str]:
        return settings_store.get_mdq_target_folders()


_HVE_SETTINGS = _HveSettingsBackend()


class MdqIndexSection(_SharedMdqIndexSection):
    """Shared panel with HVE's existing settings store injected."""

    def __init__(
        self, *, repo_root: Path, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(
            repo_root=repo_root,
            parent=parent,
            settings_backend=_HVE_SETTINGS,
        )


__all__ = ["MdqIndexSection"]
