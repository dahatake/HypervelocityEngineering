"""Smoke tests for the test-search preview panel (Phase 2 / T07).

We don't invoke a real search here — the underlying SearchPreviewThread is
exercised in Phase 1 tests. This module only verifies UI wiring:
construction, collapse/expand, and that set_context updates internal state.
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


def test_panel_construction(qapp, tmp_path: Path):
    from tools.skills.markdown_query.gui.search_preview_panel import (
        TestSearchPanel,
    )
    panel = TestSearchPanel(repo_root=tmp_path)
    # Body must be hidden by default (Q4=B). isVisible() requires show(), so
    # we assert via isHidden() which reflects setVisible() regardless of show.
    assert panel._body.isHidden() is True


def test_panel_toggle_expands_body(qapp, tmp_path: Path):
    from tools.skills.markdown_query.gui.search_preview_panel import (
        TestSearchPanel,
    )
    panel = TestSearchPanel(repo_root=tmp_path)
    panel._toggle.setChecked(True)
    assert panel._body.isHidden() is False
    panel._toggle.setChecked(False)
    assert panel._body.isHidden() is True


def test_panel_set_context_updates_internal_state(qapp, tmp_path: Path):
    from tools.skills.markdown_query.gui.search_preview_panel import (
        TestSearchPanel,
    )
    panel = TestSearchPanel(repo_root=tmp_path)
    panel.set_context(lang="en-us", strategy="semantic_paragraph", fusion_alpha=0.3)
    assert panel._lang == "en-us"
    assert panel._strategy == "semantic_paragraph"
    assert panel._fusion_alpha == 0.3


def test_panel_clear_results_empties_table(qapp, tmp_path: Path):
    from tools.skills.markdown_query.gui.search_preview_panel import (
        TestSearchPanel,
    )
    panel = TestSearchPanel(repo_root=tmp_path)
    panel._populate_table([
        {"path": "a.md", "heading_path": "# A", "score": 1.0, "snippet": "x"},
    ])
    assert panel._table.rowCount() == 1
    panel.clear_results()
    assert panel._table.rowCount() == 0


def test_panel_empty_query_shows_message(qapp, tmp_path: Path):
    from tools.skills.markdown_query.gui.search_preview_panel import (
        TestSearchPanel,
    )
    panel = TestSearchPanel(repo_root=tmp_path)
    panel._query_input.setText("   ")
    panel._on_run_clicked()
    assert "クエリ" in panel._status.text()
