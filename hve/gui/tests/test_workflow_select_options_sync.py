"""左 workflow チェック → 右 OptionsPage 即時同期の回帰テスト。

T1〜T7 で導入した「左の workflow チェック操作が即時に右ペイン
`OptionsPage` の表示カテゴリへ反映される」挙動を担保する。
旧 `AutopilotInputPanel` を統合し、Autopilot ON/OFF いずれでも
同等に動作することを検証する。
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from hve.gui.page_options import OptionsPage
from hve.gui.page_workflow_select import WorkflowSelectPage


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _category_visible(options: OptionsPage, key: str) -> bool:
    """`OptionsPage._category_groups[key]` の表示意図を取得。

    isVisible() は親が未描画なら False を返すため、`isHidden()` の否定で
    「明示的に hide されていない」を検査する。
    """
    g = options._category_groups.get(key)
    assert g is not None, f"category {key} not found"
    return not g.isHidden()


def test_options_page_initially_empty(qapp) -> None:
    """workflow 未選択時は C10〜C14 はすべて非表示。"""
    options = OptionsPage()
    # 既定で hide される（Step 2 不要カテゴリ）
    for hidden_key in ("C1", "C3", "C5", "C6", "C7", "AZURE"):
        assert _category_visible(options, hidden_key) is False
    # workflow 未選択 → C10〜C14 も非表示
    for cond_key in ("C4", "C10", "C11", "C12", "C13", "C14"):
        assert _category_visible(options, cond_key) is False


def test_options_page_updates_on_set_workflows_ard(qapp) -> None:
    """ARD 選択 → C4 (Work IQ) と C14 (要求定義書) が表示される。"""
    options = OptionsPage()
    options.set_workflows(["ard"], {"ard": "ARD"})
    assert _category_visible(options, "C14") is True
    assert _category_visible(options, "C4") is True
    # 他は非表示
    for cond_key in ("C10", "C11", "C12", "C13"):
        assert _category_visible(options, cond_key) is False


def test_options_page_updates_on_set_workflows_aad_web(qapp) -> None:
    """aad-web 選択 → C10 (アプリケーション ID) が表示される。"""
    options = OptionsPage()
    options.set_workflows(["aad-web"], {"aad-web": "AAD Web"})
    assert _category_visible(options, "C10") is True


def test_options_page_clears_when_workflow_unset(qapp) -> None:
    """workflow を空に戻すと C10〜C14 はすべて非表示に戻る。"""
    options = OptionsPage()
    options.set_workflows(["aad-web"], {"aad-web": "AAD Web"})
    assert _category_visible(options, "C10") is True
    options.set_workflows([], {})
    for cond_key in ("C4", "C10", "C11", "C12", "C13", "C14"):
        assert _category_visible(options, cond_key) is False


def test_workflow_select_page_has_no_autopilot_input_panel(qapp) -> None:
    """旧 AutopilotInputPanel は完全に削除されている。"""
    w = WorkflowSelectPage()
    assert not hasattr(w, "autopilot_input_panel")
    assert not hasattr(w, "_autopilot_input_panel")
    assert not hasattr(w, "_right_splitter")


def test_options_page_no_per_section_api(qapp) -> None:
    """OptionsPage の per-workflow セクション API も削除されている。"""
    options = OptionsPage()
    assert not hasattr(options, "create_per_workflow_section")
    assert not hasattr(options, "build_args_for_workflow_using_section")
