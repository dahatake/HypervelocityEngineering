"""hve.gui.tests.test_labeled_field_layout

`_LabeledField` のレイアウト要件検証:

- テキスト入力系 (QLineEdit / QPlainTextEdit / QTextEdit / _FilePickerWidget)
  はラベル右側で「左寄り＋幅最大化（stretch=1, SizePolicy.Expanding）」で配置される。
- 非テキスト系 (QComboBox 等) は従来通り右寄せ配置で維持される。

根拠: ユーザー要件「テキストボックスは左寄りに表示、横幅を表示エリアで最大化、
画面横幅が変わったら動的に拡大・縮小」。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QSizePolicy,
    QTextEdit,
)

from hve.gui.page_options import _FilePickerWidget, _LabeledField, _is_text_input_widget  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_is_text_input_widget_for_text_types(qapp):
    assert _is_text_input_widget(QLineEdit()) is True
    assert _is_text_input_widget(QPlainTextEdit()) is True
    assert _is_text_input_widget(QTextEdit()) is True
    assert _is_text_input_widget(_FilePickerWidget()) is True


def test_is_text_input_widget_for_non_text_types(qapp):
    assert _is_text_input_widget(QComboBox()) is False


def test_qlineedit_field_is_expanding(qapp):
    edit = QLineEdit()
    field = _LabeledField("ラベル", "説明", edit)
    # 入力ウィジェット側 SizePolicy が Expanding になっている
    assert edit.sizePolicy().horizontalPolicy() == QSizePolicy.Expanding
    # レイアウト内で stretch=1 で配置されている
    layout = field.layout()
    idx = layout.indexOf(edit)
    assert idx >= 0
    assert layout.stretch(idx) == 1


def test_qcombobox_field_keeps_right_align(qapp):
    combo = QComboBox()
    field = _LabeledField("ラベル", "説明", combo)
    layout = field.layout()
    idx = layout.indexOf(combo)
    # 非テキスト系は stretch=0（従来挙動）
    assert layout.stretch(idx) == 0


def test_file_picker_field_is_expanding(qapp):
    picker = _FilePickerWidget()
    field = _LabeledField("ラベル", "説明", picker)
    layout = field.layout()
    idx = layout.indexOf(picker)
    assert layout.stretch(idx) == 1
