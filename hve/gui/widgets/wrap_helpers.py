"""hve.gui.widgets.wrap_helpers — テキスト系ウィジェットの折り返し / 横スクロール抑止ヘルパー。

ワークベンチ画面で「横スクロールバーを表示しない」「日本語を可能な限り
折り返す」要件を満たすための共通処理を提供する。

- :func:`apply_cjk_wrap` : ``QPlainTextEdit`` / ``QTextEdit`` 等に対し
  ``WrapAtWordBoundaryOrAnywhere`` を適用し、ウィジェット幅で折り返す。
- :func:`disable_horizontal_scrollbar` : 任意の ``QAbstractScrollArea`` の
  水平スクロールバーを常時非表示にする。

Notes:
    Qt 標準では日本語の禁則処理は完全には実装されていない。
    本ヘルパーは ``WrapAtWordBoundaryOrAnywhere`` により
    「単語境界優先・必要に応じて任意位置で折り返し」とすることで、
    読みやすさを維持しつつ横スクロールを発生させない。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import QAbstractScrollArea, QPlainTextEdit, QTextEdit


def disable_horizontal_scrollbar(widget: QAbstractScrollArea) -> None:
    """ウィジェットの水平スクロールバーを常時非表示にする。"""
    widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)


def apply_cjk_wrap(widget: QAbstractScrollArea) -> None:
    """テキスト系ウィジェットに CJK 対応の折り返しを適用する。

    対象:
        - :class:`PySide6.QtWidgets.QPlainTextEdit`
        - :class:`PySide6.QtWidgets.QTextEdit`

    その他の :class:`QAbstractScrollArea` 派生は水平スクロールバー OFF のみ適用する。
    """
    disable_horizontal_scrollbar(widget)

    if isinstance(widget, QPlainTextEdit):
        widget.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        widget.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        _apply_document_option(widget)
    elif isinstance(widget, QTextEdit):
        widget.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        widget.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        _apply_document_option(widget)


def _apply_document_option(widget: QAbstractScrollArea) -> None:
    """``document().defaultTextOption()`` 経由でも同じラップモードを反映する。

    一部の Qt バージョンでは ``setWordWrapMode`` だけでは
    ``document()`` 側の設定が更新されないことがあるため、明示的に再設定する。
    """
    doc = getattr(widget, "document", None)
    if doc is None:
        return
    document = doc()
    if document is None:
        return
    opt: Optional[QTextOption] = document.defaultTextOption()
    if opt is None:
        return
    opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    document.setDefaultTextOption(opt)
