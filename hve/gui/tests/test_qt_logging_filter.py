"""`hve.gui.app._configure_qt_logging` のテスト。

検証観点:
- `_configure_qt_logging()` 呼び出し後、`qt.text.font.db` カテゴリの
  warning / info / critical が **全て** 無効化されること。

なぜ全レベルを検証するか:
  warning レベルのみを無効化する `qt.text.font.db.warning=false` では、
  当該 "OpenType support missing" メッセージは実測上抑止されない
  （`isWarningEnabled()` は False を返すが警告は出力され続ける）。
  抑止に有効なのはカテゴリ全体を無効化する `qt.text.font.db=false` のみで、
  この場合 info / warning / critical が全て False になる。warning のみ False
  だと critical / info は True のまま残るため、本テストは壊れたルールへの
  差し戻しを回帰として検出できる。
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QLoggingCategory  # noqa: E402

from hve.gui.app import _configure_qt_logging  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_qt_filter_rules():
    """グローバルなロギングフィルタを変更するため、テスト後に既定へ戻す。"""
    yield
    QLoggingCategory.setFilterRules("")


def test_configure_qt_logging_disables_whole_font_db_category():
    _configure_qt_logging()

    cat = QLoggingCategory("qt.text.font.db")
    # カテゴリ全体が無効化されていること（warning 限定では抑止できないため）。
    assert cat.isWarningEnabled() is False
    assert cat.isInfoEnabled() is False
    assert cat.isCriticalEnabled() is False
