"""FR-GUI-05 / FR-KIT-05: mdq 管理画面と索引操作サービスの単一実装化。

根拠: hve-dev/requirement-definition.md §6.5 FR-GUI-05 / §3.10 FR-KIT-05

RED（実装前）:
  - ``import mdq.gui`` が ``ModuleNotFoundError``
  - ``hve/gui/mdq_index_service.py`` が索引ロジックの実体を保持
  - ``hve/gui/settings_window.py`` が ``tools.skills.markdown_query`` を import
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

_SHARED_SERVICE_FUNCS = (
    "resolve_effective_roots",
    "get_index_stats",
    "get_index_stats_all_strategies",
    "rebuild_index",
    "delete_index_db",
    "search_preview",
)


def _read(rel: str) -> str:
    return (_REPO_ROOT / rel).read_text(encoding="utf-8")


class TestSharedServiceIsSingleImplementation:
    def test_mdq_gui_package_is_importable(self) -> None:
        import mdq.gui  # noqa: F401

    def test_shared_service_exposes_merged_api(self) -> None:
        from mdq.gui import index_service

        for name in _SHARED_SERVICE_FUNCS:
            assert hasattr(index_service, name), f"missing {name}"

    def test_rebuild_index_accepts_both_drifted_options(self) -> None:
        """standalone 側のみが持っていた pageindex_options を共有実装が持つ。"""
        from mdq.gui import index_service

        params = inspect.signature(index_service.rebuild_index).parameters
        assert "pageindex_options" in params
        assert "semantic_options" in params

    def test_resolve_effective_roots_takes_repo_root(self) -> None:
        from mdq.gui import index_service

        params = list(
            inspect.signature(index_service.resolve_effective_roots).parameters
        )
        assert params[0] == "repo_root"

    def test_hve_service_is_reexport_only(self) -> None:
        """HVE 側に索引ロジックの第 2 実装が残っていないこと。"""
        src = _read("hve/gui/mdq_index_service.py")
        for banned in ("open_store(", "sqlite3", "build_index(", "SELECT COUNT"):
            assert banned not in src, f"second implementation detected: {banned}"

    def test_hve_service_reexports_shared_symbols(self) -> None:
        from hve.gui import mdq_index_service
        from mdq.gui import index_service

        for name in _SHARED_SERVICE_FUNCS:
            assert getattr(mdq_index_service, name) is getattr(index_service, name)


class TestDependencyDirection:
    def test_hve_gui_does_not_import_the_distribution_kit(self) -> None:
        src = _read("hve/gui/settings_window.py")
        assert "tools.skills.markdown_query" not in src

    def test_shared_gui_has_no_upstream_dependency(self) -> None:
        gui_dir = _REPO_ROOT / "mdq" / "gui"
        offenders: list[str] = []
        for path in sorted(gui_dir.rglob("*.py")):
            if "tests" in path.relative_to(gui_dir).parts:
                continue
            text = path.read_text(encoding="utf-8")
            if "import hve" in text or "from hve" in text:
                offenders.append(str(path.relative_to(_REPO_ROOT)))
        assert offenders == []

    def test_kit_gui_directory_is_removed(self) -> None:
        assert not (_REPO_ROOT / "tools" / "skills" / "markdown_query" / "gui").exists()


class TestSettingsBackendInjection:
    def test_section_accepts_injected_backend(self) -> None:
        pytest.importorskip("PySide6")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from mdq.gui.settings_section import MdqIndexSection

        params = inspect.signature(MdqIndexSection.__init__).parameters
        assert "settings_backend" in params

    def test_hve_adapter_subclasses_shared_section(self) -> None:
        pytest.importorskip("PySide6")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from hve.gui.mdq_settings_section import MdqIndexSection as HveSection
        from mdq.gui.settings_section import MdqIndexSection as SharedSection

        assert issubclass(HveSection, SharedSection)

    def test_shared_settings_store_has_no_runtime_upstream_probe(self) -> None:
        src = _read("mdq/gui/settings_store.py")
        assert "_try_hve_settings_store" not in src
