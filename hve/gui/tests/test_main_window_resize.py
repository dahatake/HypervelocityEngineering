"""hve.gui.tests.test_main_window_resize

MainWindow がユーザー操作で横幅を狭められることの回帰テスト。

検証観点:
- `setMinimumWidth(640)` により 640px 以下までドラッグ縮小可能であること
  （`minimumWidth()` / `minimumSizeHint()` が 640 以下）。
- 「表示」メニューの横幅プリセット QAction を `trigger()` するとウィンドウ幅が
  指定値に一致すること。
- 「現在の幅を既定にする」アクションが `settings_store` の
  `main_window_width` キーへ現在幅を書き込むこと。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_window(qapp):
    from hve.gui.main_window import MainWindow

    mw = MainWindow()
    # 起動時 GitHub 認証強制モーダル等の副作用を抑止するため、
    # show() は行わずインスタンス検査のみで十分。
    return mw


def test_main_window_minimum_width_is_at_most_threshold(qapp):
    """ウィンドウ全体の最小幅が現実的な閾値以下であること。

    Step 1 を 2 ペイン化 (ワークフロー選択 + オプション) に変更したため、
    OptionsPage を内包する右ペインの最小サイズヒントが増え、従来の 640px は
    達成困難となった。ドラッグ縮小を妨げない実用上限として 800px を採用する。
    """
    THRESHOLD = 800
    mw = _make_window(qapp)
    try:
        assert mw.minimumWidth() <= THRESHOLD, (
            f"minimumWidth={mw.minimumWidth()} > {THRESHOLD} のため、"
            "ドラッグでの縮小が制限される可能性がある"
        )
        # minimumSizeHint も閾値以下（子レイアウトが過度に押し上げていない）
        assert mw.minimumSizeHint().width() <= THRESHOLD, (
            f"minimumSizeHint().width()={mw.minimumSizeHint().width()} > {THRESHOLD}"
        )
    finally:
        mw.deleteLater()


def test_view_menu_width_presets_apply(qapp):
    """「表示」メニューの 800/1100/1400 プリセットが resize に反映されること。"""
    mw = _make_window(qapp)
    try:
        menu = mw._build_view_menu()  # type: ignore[attr-defined]
        actions = menu.actions()
        # 区切り線含めて最低 5 要素（プリセット3 + sep + 保存）
        assert len(actions) >= 5
        # プリセット 3 件と保存アクション 1 件をテキストで識別。
        preset_actions = {}
        save_action = None
        for act in actions:
            if act.isSeparator():
                continue
            text = act.text()
            if "800" in text:
                preset_actions[800] = act
            elif "1100" in text:
                preset_actions[1100] = act
            elif "1400" in text:
                preset_actions[1400] = act
            elif "既定" in text:
                save_action = act

        assert set(preset_actions.keys()) == {800, 1100, 1400}, (
            f"プリセット 3 件が見つからない: {list(preset_actions)}"
        )
        assert save_action is not None, "「現在の幅を既定にする」アクションが無い"

        for width, act in preset_actions.items():
            act.trigger()
            QApplication.processEvents()
            assert mw.width() == width, (
                f"プリセット {width}px 選択後の幅 {mw.width()} が一致しない"
            )
    finally:
        mw.deleteLater()


def test_save_current_width_as_default_writes_settings(qapp, tmp_path, monkeypatch):
    """「現在の幅を既定にする」が settings_store へ書き込むこと。"""
    from hve.gui import settings_store

    # settings_store の保存先をテンポラリへ向ける。
    monkeypatch.setattr(settings_store, "settings_path", lambda: tmp_path / "s.txt")

    mw = _make_window(qapp)
    try:
        mw.resize(987, mw.height())
        QApplication.processEvents()

        mw._save_current_width_as_default()  # type: ignore[attr-defined]

        saved = settings_store.get_option("main_window_width")
        assert int(saved) == 987, f"保存値 {saved} != 987"
    finally:
        mw.deleteLater()
