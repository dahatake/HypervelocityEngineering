"""Smoke / integration tests for MdqIndexSection (Phase 3 / T08).

Focus on signal wiring and visibility behavior; no real index build.
Each test redirects the HVE settings file to an isolated tmp_path so
persistence does not leak between tests (敵対的レビュー指摘事項).
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def isolated_settings(tmp_path: Path, monkeypatch):
    """Redirect both the HVE settings file and the standalone settings path
    to an isolated tmp file so each test starts from defaults().
    """
    fake = tmp_path / "isolated-settings.ini"
    # Standalone path: detect_settings_path falls back to repo_root/.mdq-gui-settings.txt
    # when neither hve dir nor file exists. We monkeypatch to force this fake file.
    from tools.skills.markdown_query.gui import settings_store as ss
    monkeypatch.setattr(ss, "_try_hve_settings_store", lambda: None)
    monkeypatch.setattr(
        ss, "detect_settings_path", lambda _repo_root: fake
    )
    return tmp_path


def _make_section(repo_root: Path, qapp):
    from tools.skills.markdown_query.gui.settings_section import MdqIndexSection
    sec = MdqIndexSection(repo_root=repo_root)
    return sec


def test_section_constructs(isolated_settings: Path, qapp):
    sec = _make_section(isolated_settings, qapp)
    assert sec is not None
    assert hasattr(sec, "_btn_force_rebuild")
    assert hasattr(sec, "_btn_delete_db")
    assert hasattr(sec, "_refresh_progress")
    assert hasattr(sec, "_semantic_options_widget")
    assert hasattr(sec, "_test_search_panel")


def test_semantic_widget_visibility_follows_strategy(
    isolated_settings: Path, qapp
):
    sec = _make_section(isolated_settings, qapp)
    assert sec._semantic_options_widget.isHidden() is True
    idx = sec._strategy_combo.findData("semantic_paragraph")
    assert idx >= 0
    sec._strategy_combo.setCurrentIndex(idx)
    assert sec._semantic_options_widget.isHidden() is False
    idx0 = sec._strategy_combo.findData("heading")
    sec._strategy_combo.setCurrentIndex(idx0)
    assert sec._semantic_options_widget.isHidden() is True


def test_resolve_fusion_alpha_only_when_late_chunking(
    isolated_settings: Path, qapp
):
    sec = _make_section(isolated_settings, qapp)
    assert sec._resolve_fusion_alpha() is None
    idx = sec._strategy_combo.findData("semantic_paragraph")
    sec._strategy_combo.setCurrentIndex(idx)
    assert sec._resolve_fusion_alpha() is None
    sec._semantic_options_widget._late_chunking.setChecked(True)
    val = sec._resolve_fusion_alpha()
    assert isinstance(val, float)


def test_progress_bar_updates(isolated_settings: Path, qapp):
    sec = _make_section(isolated_settings, qapp)
    sec._on_refresh_progressed("docs/a.md", 1, 4)
    assert sec._refresh_progress.value() == 1
    assert sec._refresh_progress.maximum() == 4
    sec._on_refresh_progressed("docs/d.md", 4, 4)
    assert sec._refresh_progress.value() == 4
