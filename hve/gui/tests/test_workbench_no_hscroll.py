"""hve.gui.tests.test_workbench_no_hscroll

ワークベンチ画面で横スクロールバーが発生しないこと、および
テキスト系ウィジェットに CJK 折り返しが適用されることを検証する回帰テスト。

根拠: ユーザー要件「ワークベンチ画面の横幅について、横スクロールバーは
出さないように、かつ、画面内の全てのコンポーネントが表示画面に収まらない場合は
ラベルなどを複数行にわたって自動的に折り返す」。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QTextOption  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QPlainTextEdit,
    QTextEdit,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# wrap_helpers の直接検証
# ---------------------------------------------------------------------------


def test_apply_cjk_wrap_to_plain_text_edit(qapp):
    from hve.gui.widgets.wrap_helpers import apply_cjk_wrap

    w = QPlainTextEdit()
    apply_cjk_wrap(w)
    assert w.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
    assert w.wordWrapMode() == QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere
    assert w.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff


def test_apply_cjk_wrap_to_text_edit(qapp):
    from hve.gui.widgets.wrap_helpers import apply_cjk_wrap

    w = QTextEdit()
    apply_cjk_wrap(w)
    assert w.lineWrapMode() == QTextEdit.LineWrapMode.WidgetWidth
    assert w.wordWrapMode() == QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere
    assert w.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff


# ---------------------------------------------------------------------------
# WorkbenchWindow 内ウィジェットの検証
# ---------------------------------------------------------------------------


def test_workbench_window_panes_have_no_hscroll(qapp):
    from hve.gui.workbench_window import _LogPane, _UserActionsPane

    log = _LogPane("ログ")
    ua = _UserActionsPane()
    try:
        assert (
            log.log_view.horizontalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert log.log_view.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
        assert (
            ua.view.horizontalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
    finally:
        log.deleteLater()
        ua.deleteLater()


# ---------------------------------------------------------------------------
# page_workbench の LogPane / UserActions の検証
# ---------------------------------------------------------------------------


def test_page_workbench_log_pane_no_hscroll(qapp, tmp_path, monkeypatch):
    # _open_new_log_file が cwd 配下に書き込むためテンポラリへ
    monkeypatch.chdir(tmp_path)
    from hve.gui.page_workbench import _EnhancedUserActionsPane, _LogPane

    log = _LogPane("ログ")
    ua = _EnhancedUserActionsPane()
    try:
        assert (
            log.log_view.horizontalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert log.log_view.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
        assert (
            ua.view.horizontalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert ua.view.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
    finally:
        log.deleteLater()
        ua.deleteLater()


# ---------------------------------------------------------------------------
# [REMOVED] ActivityStatusWidget の Tree 横スクロール検証は DagStatusWidget への
# 置換で陳腐化したためスキップする。DAG ビューは QGraphicsView ベースであり
# 横スクロールはコンテンツに応じて出る前提（ScrollBarAsNeeded）。
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="ActivityStatusWidget removed; replaced by DagStatusWidget")
def test_activity_status_tree_no_hscroll_and_delegate(qapp):
    pass


# ---------------------------------------------------------------------------
# 横幅永続化キーが defaults に登録されている
# ---------------------------------------------------------------------------


def test_settings_store_window_width_keys_exist():
    from hve.gui import settings_store

    d = settings_store.defaults()
    assert "main_window_width" in d["options"]
    assert "workbench_window_width" in d["options"]
    # 既定値 0 = 未設定
    assert d["options"]["main_window_width"] == 0
    assert d["options"]["workbench_window_width"] == 0


def test_settings_store_set_option_round_trip(tmp_path, monkeypatch):
    from hve.gui import settings_store

    monkeypatch.setattr(
        settings_store, "settings_path", lambda: tmp_path / ".settings.txt"
    )
    settings_store.set_option("main_window_width", 1234)
    assert settings_store.get_option("main_window_width") == 1234
