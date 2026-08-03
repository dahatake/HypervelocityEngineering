"""test_qa_answer_dialog.py — QAAnswerDialog の単体テスト (offscreen)。

実行: QT_QPA_PLATFORM=offscreen pytest hve/gui/tests/test_qa_answer_dialog.py -v
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# offscreen 強制
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PySide6.QtWidgets import QApplication

from hve.qa_merger import Choice, QADocument, QAQuestion
from hve.gui.qa_answer_dialog import QAAnswerDialog, _COL_CHOICES


_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _make_doc_with_choices() -> QADocument:
    return QADocument(
        title="テスト質問票",
        questions=[
            QAQuestion(
                no=1,
                question="Q1?",
                choices=[
                    Choice(label="A", text="はい"),
                    Choice(label="B", text="いいえ"),
                ],
                default_answer="A) はい",
                reason="既存要件",
                priority="高",
                category="設計",
            ),
            QAQuestion(
                no=2,
                question="Q2?",
                choices=[
                    Choice(label="A", text="OK"),
                    Choice(label="B", text="NG"),
                ],
                default_answer="B) NG",
            ),
        ],
    )


def _make_doc_with_free_text() -> QADocument:
    return QADocument(
        questions=[
            QAQuestion(
                no=1,
                question="自由記述?",
                choices=[],
                default_answer="既定テキスト",
            ),
        ],
    )


class TestQAAnswerDialog(unittest.TestCase):
    def setUp(self) -> None:
        _get_app()

    def test_default_is_preselected(self) -> None:
        """既定値候補のラベルが初期選択される。"""
        doc = _make_doc_with_choices()
        dlg = QAAnswerDialog(doc, step_id="1.1")
        # Q1: default A) はい → A 選択
        # Q2: default B) NG → B 選択
        labels = [qw.selected_label() for qw in dlg._question_widgets]
        self.assertEqual(labels, ["A", "B"])
        dlg.close()

    def test_choices_column_shows_full_text(self) -> None:
        """選択肢列に各選択肢の全文が「ラベル) 本文」形式・改行区切りで表示される。"""
        doc = _make_doc_with_choices()
        dlg = QAAnswerDialog(doc)
        item = dlg._table.item(0, _COL_CHOICES)
        assert item is not None
        # 選択肢は「ラベル) 本文」を改行で連結して縦に並べる
        self.assertEqual(item.text(), "A) はい\nB) いいえ")
        dlg.close()

    def test_choices_column_header_label(self) -> None:
        """新設列のヘッダが「選択肢」である。"""
        doc = _make_doc_with_choices()
        dlg = QAAnswerDialog(doc)
        header_item = dlg._table.horizontalHeaderItem(_COL_CHOICES)
        assert header_item is not None
        self.assertEqual(header_item.text(), "選択肢")
        dlg.close()

    def test_answer_combo_shows_label_only(self) -> None:
        """回答コンボは選択肢のラベル記号のみを表示し、serialize 用ラベルは不変。"""
        doc = _make_doc_with_choices()
        dlg = QAAnswerDialog(doc)
        combo = dlg._question_widgets[0].combo
        assert combo is not None
        self.assertEqual(combo.itemText(0), "A")
        self.assertEqual(combo.itemText(1), "B")
        # 全文は回答コンボには表示しない
        self.assertNotIn("はい", combo.itemText(0))
        # serialize 用のラベルは維持
        self.assertEqual(dlg._question_widgets[0].selected_label(), "A")
        dlg.close()

    def test_free_text_choices_column_is_empty(self) -> None:
        """自由記述質問（choices 空）の選択肢列は空欄。"""
        doc = _make_doc_with_free_text()
        dlg = QAAnswerDialog(doc)
        item = dlg._table.item(0, _COL_CHOICES)
        assert item is not None
        self.assertEqual(item.text(), "")
        dlg.close()

    def test_submit_emits_answers(self) -> None:
        """[Submit] で番号:ラベル形式の文字列が emit される。"""
        doc = _make_doc_with_choices()
        dlg = QAAnswerDialog(doc)
        captured = {}
        dlg.submitted.connect(lambda s: captured.setdefault("content", s))
        dlg._on_submit()
        self.assertIn("content", captured)
        self.assertIn("1: A", captured["content"])
        self.assertIn("2: B", captured["content"])

    def test_defaults_button_emits_signal(self) -> None:
        doc = _make_doc_with_choices()
        dlg = QAAnswerDialog(doc)
        called = []
        dlg.adopt_all_defaults.connect(lambda: called.append(True))
        dlg._on_defaults()
        self.assertEqual(called, [True])

    def test_cancel_button_emits_signal(self) -> None:
        doc = _make_doc_with_choices()
        dlg = QAAnswerDialog(doc)
        called = []
        dlg.cancelled.connect(lambda: called.append(True))
        dlg._on_cancel()
        self.assertEqual(called, [True])

    def test_free_text_question_uses_line_edit(self) -> None:
        """choices 空の質問は QLineEdit が編集可能で、既定値が初期表示される。"""
        doc = _make_doc_with_free_text()
        dlg = QAAnswerDialog(doc)
        row = dlg._question_widgets[0]
        # 自由記述行は label を返さない
        self.assertEqual(row.selected_label(), "")
        # 既定値が初期値として表示される
        self.assertEqual(row.freetext_value(), "既定テキスト")
        # 既定値のままで Submit → `N:: 既定テキスト` 形式で出力
        captured = {}
        dlg.submitted.connect(lambda s: captured.setdefault("content", s))
        dlg._on_submit()
        self.assertIn("1:: 既定テキスト", captured["content"])

    def test_free_text_user_edit_is_serialized(self) -> None:
        """自由記述で書き換えた内容が `N:: <text>` 形式で出力される。"""
        doc = _make_doc_with_free_text()
        dlg = QAAnswerDialog(doc)
        row = dlg._question_widgets[0]
        assert row.line_edit is not None
        row.line_edit.setText("ユーザー入力の自由記述")
        captured = {}
        dlg.submitted.connect(lambda s: captured.setdefault("content", s))
        dlg._on_submit()
        self.assertIn("1:: ユーザー入力の自由記述", captured["content"])

    def test_free_text_empty_is_omitted(self) -> None:
        """自由記述を空にした場合は当該質問の行が省略される（CLI 既定値採用）。"""
        doc = _make_doc_with_free_text()
        dlg = QAAnswerDialog(doc)
        row = dlg._question_widgets[0]
        assert row.line_edit is not None
        row.line_edit.setText("")
        captured = {}
        dlg.submitted.connect(lambda s: captured.setdefault("content", s))
        dlg._on_submit()
        self.assertNotIn("1:", captured["content"])


if __name__ == "__main__":
    unittest.main()
