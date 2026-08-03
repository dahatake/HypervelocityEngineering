"""hve.gui.tests.test_main_window_resize

MainWindow がユーザー操作で横幅を狭められることの回帰テスト。

検証観点:
- `setMinimumWidth(640)` により 640px 以下までドラッグ縮小可能であること
  （`minimumWidth()` / `minimumSizeHint()` が 640 以下）。
- resize 後の幅が `_persist_window_width` で `settings_store` の
  `main_window_width` キーへ書き込まれること（旧「表示」メニューは撤去済み）。
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


def _make_window(qapp, tmp_path):
    from hve.gui.main_window import MainWindow

    # repo_root を構築時に渡す。__init__ 内の GuiSessionWorkdir.create() が
    # work/run/<id>/ を作成するため、tmp_path で隔離して実リポジトリ汚染を防ぐ。
    mw = MainWindow(repo_root=tmp_path)
    # 起動時 GitHub 認証強制モーダル等の副作用を抑止するため、
    # show() は行わずインスタンス検査のみで十分。
    return mw


def test_main_window_minimum_width_is_at_most_threshold(qapp, tmp_path):
    """ウィンドウ全体の最小幅が現実的な閾値以下であること。

    Step 1 を 2 ペイン化 (ワークフロー選択 + オプション) に変更したため、
    OptionsPage を内包する右ペインの最小サイズヒントが増え、従来の 640px は
    達成困難となった。さらに Phase D (Dock 統合) で左右に
    FileTreePanel / MarkdownPreviewPanel を追加し既定可視にしたため、
    最小幅は FileTree 180 + 中央 stack + Preview 200 程度に
    なる。ドラッグ縮小を妨げない実用上限として 1200px を採用する。
    """
    THRESHOLD = 1200
    mw = _make_window(qapp, tmp_path)
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


def test_persist_window_width_writes_settings(qapp, tmp_path, monkeypatch):
    """resize 後の幅が ``_persist_window_width`` で settings_store へ保存されること。

    旧「表示」メニュー（幅プリセット / 現在の幅を既定にする）は撤去され、
    現仕様では resizeEvent 経由の auto-persist（``_persist_window_width``）に
    一本化された。本テストはその永続化契約の回帰防止。
    """
    from hve.gui import settings_store

    # settings_store の保存先をテンポラリへ向ける。
    monkeypatch.setattr(settings_store, "settings_path", lambda: tmp_path / "s.txt")

    mw = _make_window(qapp, tmp_path)
    try:
        mw.resize(987, mw.height())
        QApplication.processEvents()

        mw._persist_window_width()  # type: ignore[attr-defined]

        saved = settings_store.get_option("main_window_width")
        assert int(saved) == 987, f"保存値 {saved} != 987"
    finally:
        mw.deleteLater()
