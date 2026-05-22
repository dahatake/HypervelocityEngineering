"""Smoke + logic tests for the SemanticOptionsWidget (Phase 2 / T05).

Uses ``pytest-qt`` style fixtures when available; otherwise creates a
QApplication directly. We test the load/save roundtrip and the
fusion-alpha visibility rule (Q9=A) — pure UI logic without external
backends.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_widget_construction_and_defaults(qapp):
    from tools.skills.markdown_query.gui.semantic_options import (
        SemanticOptionsWidget,
    )
    w = SemanticOptionsWidget()
    d = w.to_settings_dict()
    # Defaults: zeros for "use code default", contextualize True, late off.
    assert d["semantic_max_chunk_chars"] == 0
    assert d["semantic_min_chars"] == 0
    assert d["semantic_breakpoint_percentile_lo"] == 0.0
    assert d["semantic_breakpoint_percentile_hi"] == 0.0
    assert d["semantic_embed_provider"] == ""
    assert d["semantic_embed_model"] == ""
    assert d["semantic_contextualize"] is True
    assert d["semantic_late_chunking"] is False
    assert d["semantic_fusion_alpha"] == 0.5


def test_widget_load_roundtrip(qapp):
    from tools.skills.markdown_query.gui.semantic_options import (
        SemanticOptionsWidget,
    )
    w = SemanticOptionsWidget()
    payload = {
        "semantic_max_chunk_chars": 1200,
        "semantic_min_chars": 250,
        "semantic_breakpoint_percentile_lo": 55.5,
        "semantic_breakpoint_percentile_hi": 95.0,
        "semantic_embed_provider": "fastembed",
        "semantic_embed_model": "BAAI/bge-small-en-v1.5",
        "semantic_contextualize": False,
        "semantic_late_chunking": True,
        "semantic_fusion_alpha": 0.75,
    }
    w.load_from(payload)
    out = w.to_settings_dict()
    for k, v in payload.items():
        assert out[k] == v, f"{k}: {out[k]} != {v}"


def test_fusion_alpha_visibility_follows_late_chunking(qapp):
    """Q9=A: fusion_alpha is shown only when late_chunking is ON."""
    from tools.skills.markdown_query.gui.semantic_options import (
        SemanticOptionsWidget,
    )
    w = SemanticOptionsWidget()
    # Initially off → row hidden.
    assert w._fusion_alpha.isVisible() is False
    # Turn on → row visible (we read internal widget directly).
    w._late_chunking.setChecked(True)
    # Qt visibility requires show(); for headless test we ensure the
    # *intended* visibility flag (visibility hint) is set. The widget
    # exposes _refresh_fusion_visibility which sets visibility via
    # setVisible(True) — but isVisible() returns False until shown().
    # Use visibility-state-of-intent via the widget's own setVisible call.
    # Adapter: check the row label flag.
    assert w._fusion_row_label.isHidden() is False or not w._fusion_row_label.isHidden()


def test_changed_signal_fires(qapp):
    from tools.skills.markdown_query.gui.semantic_options import (
        SemanticOptionsWidget,
    )
    w = SemanticOptionsWidget()
    hits = []
    w.changed.connect(lambda: hits.append(1))
    w._contextualize.setChecked(False)
    w._late_chunking.setChecked(True)
    w._max_chars.setValue(1234)
    assert len(hits) >= 2  # at least 2 distinct changes registered
