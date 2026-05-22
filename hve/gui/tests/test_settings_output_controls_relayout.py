"""設定画面の出力制御レイアウト変更に関する回帰テスト。"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_settings_category_tree_removes_c6_output_controls() -> None:
    from hve.gui.settings_window import _CATEGORY_TREE

    general_items = [items for label, items in _CATEGORY_TREE if label == "一般"][0]
    labels = [name for name, _key in general_items]
    keys = [key for _name, key in general_items]

    assert "基本設定" in labels
    assert "出力制御" not in labels
    assert "C1" in keys
    assert "C6" not in keys


def test_settings_apply_maps_verbosity_to_c1_only() -> None:
    from hve.gui.settings_apply import _SECTION_FIELDS

    assert "C1" in _SECTION_FIELDS
    assert _SECTION_FIELDS["C1"]["verbosity"] == "verbosity"
    assert "C6" not in _SECTION_FIELDS


def test_c1_basic_has_verbosity_selector(qapp) -> None:
    from hve.gui.page_options import _C1Basic

    c1 = _C1Basic()
    assert hasattr(c1, "verbosity")

    values = [c1.verbosity.itemData(i) for i in range(c1.verbosity.count())]
    assert values[0] is None
    assert values[1:] == ["quiet", "compact", "normal", "verbose"]
