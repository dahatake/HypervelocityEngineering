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

from hve.qa_merger import Choice, QADocument, QAMerger, QAQuestion
from hve.gui.qa_answer_dialog import (
    QAAnswerDialog,
    _COL_ANSWER,
    _COL_BACKGROUND,
    _COL_CHOICES,
    _COL_VIEWPOINTS,
)


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


def _make_doc_with_existing_other_choice() -> QADocument:
    return QADocument(
        questions=[
            QAQuestion(
                no=1,
                question="既存のその他を含む質問?",
                choices=[
                    Choice(label="A", text="既定の選択"),
                    Choice(label="B", text="その他"),
                ],
                default_answer="A) 既定の選択",
            ),
        ],
    )


def _make_doc_with_other_prefix_choice() -> QADocument:
    return QADocument(
        questions=[
            QAQuestion(
                no=1,
                question="その他で始まる通常選択肢を含む質問?",
                choices=[
                    Choice(label="A", text="標準の選択"),
                    Choice(label="B", text="その他の条件を維持"),
                ],
                default_answer="A) 標準の選択",
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
        self.assertIn("A) はい", item.text())
        self.assertIn("B) いいえ", item.text())
        self.assertEqual(item.text().count("その他"), 1)
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

    def test_choice_question_appends_other_option(self) -> None:
        """全ての選択肢付き質問には GUI 専用の「その他」が 1 件表示される。"""
        doc = _make_doc_with_choices()
        dlg = QAAnswerDialog(doc)
        for row in dlg._question_widgets:
            combo = row.combo
            assert combo is not None
            labels = [combo.itemText(i) for i in range(combo.count())]
            self.assertIn("A", labels)
            self.assertIn("B", labels)
            self.assertEqual(labels.count("その他"), 1)
        dlg.close()

    def test_selecting_other_enables_freetext_and_serializes_it(self) -> None:
        """「その他」の自由記述は既存の N:: 形式で送信される。"""
        doc = _make_doc_with_choices()
        dlg = QAAnswerDialog(doc)
        row = dlg._question_widgets[0]
        assert row.combo is not None
        other_index = row.combo.findText("その他")
        self.assertGreaterEqual(other_index, 0)
        row.combo.setCurrentIndex(other_index)
        assert row.other_line_edit is not None
        self.assertTrue(row.other_line_edit.isEnabled())
        row.other_line_edit.setText("独自の判断")

        captured: dict[str, str] = {}
        dlg.submitted.connect(lambda s: captured.setdefault("content", s))
        dlg._on_submit()
        self.assertIn("1:: その他: 独自の判断", captured["content"])

    def test_answer_column_reserves_freetext_width(self) -> None:
        """その他の自由記述欄を入力可能な初期幅で表示する。"""
        dlg = QAAnswerDialog(_make_doc_with_choices())
        self.assertGreaterEqual(dlg._table.columnWidth(_COL_ANSWER), 280)
        dlg.close()

    def test_structured_other_default_is_editable(self) -> None:
        """構造化質問票の D. その他を初期選択時から自由記述として扱う。"""
        doc = QAMerger.parse_qa_content(
            """\
[Q01]
- 質問文: 既定でその他を選ぶ質問
- 選択肢:
  A. 標準
  D. その他
- 未回答時の既定値候補: D. その他
"""
        )
        dlg = QAAnswerDialog(doc)
        row = dlg._question_widgets[0]
        assert row.combo is not None
        assert row.other_line_edit is not None
        self.assertEqual(row.combo.currentText(), "その他")
        self.assertTrue(row.other_line_edit.isEnabled())
        row.other_line_edit.setText("構造化質問票の補足")

        captured: dict[str, str] = {}
        dlg.submitted.connect(lambda s: captured.setdefault("content", s))
        dlg._on_submit()
        self.assertEqual(captured["content"], "1:: その他: 構造化質問票の補足")

    def test_other_text_default_is_editable(self) -> None:
        """ラベルと既定値が「その他」の場合も自由記述を初期選択する。"""
        doc = QADocument(
            questions=[
                QAQuestion(
                    no=1,
                    question="その他ラベルの質問",
                    choices=[
                        Choice(label="A", text="標準"),
                        Choice(label="その他", text="自由記述"),
                    ],
                    default_answer="その他",
                ),
            ],
        )
        dlg = QAAnswerDialog(doc)
        row = dlg._question_widgets[0]
        assert row.combo is not None
        assert row.other_line_edit is not None
        self.assertEqual(row.combo.currentText(), "その他")
        self.assertTrue(row.other_line_edit.isEnabled())
        row.other_line_edit.setText("既定のその他への補足")

        captured: dict[str, str] = {}
        dlg.submitted.connect(lambda s: captured.setdefault("content", s))
        dlg._on_submit()
        self.assertEqual(captured["content"], "1:: その他: 既定のその他への補足")

    def test_switching_from_other_back_to_choice_uses_label_serialization(self) -> None:
        """通常選択肢へ戻すと、その他の入力を送信しない。"""
        doc = _make_doc_with_choices()
        dlg = QAAnswerDialog(doc)
        row = dlg._question_widgets[0]
        assert row.combo is not None
        other_index = row.combo.findText("その他")
        self.assertGreaterEqual(other_index, 0)
        row.combo.setCurrentIndex(other_index)
        assert row.other_line_edit is not None
        row.other_line_edit.setText("選択し直す前の入力")

        row.combo.setCurrentIndex(row.combo.findText("A"))
        self.assertFalse(row.other_line_edit.isEnabled())
        captured: dict[str, str] = {}
        dlg.submitted.connect(lambda s: captured.setdefault("content", s))
        dlg._on_submit()
        self.assertIn("1: A", captured["content"])
        self.assertNotIn("1::", captured["content"])
        self.assertNotIn("選択し直す前の入力", captured["content"])

    def test_existing_other_choice_is_not_duplicated_and_serializes_freetext(self) -> None:
        """既存の「その他」は重複せず、同じ自由記述経路を使う。"""
        doc = _make_doc_with_existing_other_choice()
        dlg = QAAnswerDialog(doc)
        row = dlg._question_widgets[0]
        assert row.combo is not None
        self.assertEqual(row.combo.count(), 2)
        other_index = row.combo.findText("その他")
        self.assertGreaterEqual(other_index, 0)
        row.combo.setCurrentIndex(other_index)
        assert row.other_line_edit is not None
        self.assertTrue(row.other_line_edit.isEnabled())
        row.other_line_edit.setText("既存選択肢からの補足")

        captured: dict[str, str] = {}
        dlg.submitted.connect(lambda s: captured.setdefault("content", s))
        dlg._on_submit()
        self.assertIn("1:: その他: 既存選択肢からの補足", captured["content"])

    def test_choice_starting_with_other_remains_a_regular_choice(self) -> None:
        """「その他」で始まる本文は、完全一致しなければ通常選択肢として扱う。"""
        dlg = QAAnswerDialog(_make_doc_with_other_prefix_choice())
        row = dlg._question_widgets[0]
        assert row.combo is not None
        row.combo.setCurrentIndex(row.combo.findText("B"))
        assert row.other_line_edit is not None
        self.assertFalse(row.other_line_edit.isEnabled())

        captured: dict[str, str] = {}
        dlg.submitted.connect(lambda s: captured.setdefault("content", s))
        dlg._on_submit()
        self.assertEqual(captured["content"], "1: B")

    def test_empty_other_freetext_is_omitted(self) -> None:
        """空白だけの「その他」は送信せず、マージ側で既定値を採用させる。"""
        doc = _make_doc_with_choices()
        dlg = QAAnswerDialog(doc)
        row = dlg._question_widgets[0]
        assert row.combo is not None
        other_index = row.combo.findText("その他")
        self.assertGreaterEqual(other_index, 0)
        row.combo.setCurrentIndex(other_index)
        assert row.other_line_edit is not None
        row.other_line_edit.setText("  ")

        captured: dict[str, str] = {}
        dlg.submitted.connect(lambda s: captured.setdefault("content", s))
        dlg._on_submit()
        self.assertNotIn("1:", captured["content"])

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


class TestQAAnswerDialogDepthColumns(unittest.TestCase):
    """FR-QA-02: 背景と根拠 / 判断の観点 を回答入力前に参照できること。"""

    def setUp(self) -> None:
        _get_app()

    @staticmethod
    def _make_doc() -> QADocument:
        return QADocument(
            questions=[
                QAQuestion(
                    no=1,
                    question="分割方針?",
                    choices=[Choice(label="A", text="分割維持"), Choice(label="B", text="統合")],
                    default_answer="A) 分割維持",
                    reason="根拠A",
                    priority="最重要",
                    category="設計",
                    background="出典: 設計メモ / 未確定: 統合時の移行コスト",
                    viewpoints="変更容易性: A 有利 / 運用コスト: B 有利",
                ),
            ],
        )

    def test_table_has_background_and_viewpoints_columns(self) -> None:
        dlg = QAAnswerDialog(self._make_doc())
        headers = []
        for i in range(dlg._table.columnCount()):
            item = dlg._table.horizontalHeaderItem(i)
            assert item is not None
            headers.append(item.text())
        self.assertIn("背景と根拠", headers)
        self.assertIn("判断の観点", headers)
        dlg.close()

    def test_depth_values_are_displayed(self) -> None:
        dlg = QAAnswerDialog(self._make_doc())
        background_item = dlg._table.item(0, _COL_BACKGROUND)
        viewpoints_item = dlg._table.item(0, _COL_VIEWPOINTS)
        assert background_item is not None
        assert viewpoints_item is not None
        self.assertEqual(
            background_item.text(), "出典: 設計メモ / 未確定: 統合時の移行コスト"
        )
        self.assertEqual(
            viewpoints_item.text(), "変更容易性: A 有利 / 運用コスト: B 有利"
        )
        dlg.close()


if __name__ == "__main__":
    unittest.main()
