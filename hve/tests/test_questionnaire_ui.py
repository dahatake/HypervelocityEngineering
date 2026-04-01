"""test_questionnaire_ui.py — questionnaire UI メソッドの単体テスト"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig
from console import Console
from qa_merger import Choice, QADocument, QAQuestion
from runner import _collect_qa_answers


def _make_console() -> Console:
    """テスト用 Console（verbose=True, quiet=False）を返す。"""
    return Console(verbose=True, quiet=False)


def _make_question(
    no: int = 1,
    question: str = "テスト質問ですか？",
    choices: list[Choice] | None = None,
    default_answer: str = "A) はい",
    reason: str = "既存要件に合致",
) -> QAQuestion:
    if choices is None:
        choices = [
            Choice(label="A", text="はい"),
            Choice(label="B", text="いいえ"),
        ]
    return QAQuestion(
        no=no,
        question=question,
        choices=choices,
        default_answer=default_answer,
        reason=reason,
    )


class TestVisibleLen(unittest.TestCase):
    """_visible_len() の動作検証。"""

    def setUp(self) -> None:
        self.c = _make_console()

    def test_visible_len_ascii(self) -> None:
        """ASCII 文字のみ: 幅 = 文字数。"""
        text = "hello"
        self.assertEqual(self.c._visible_len(text), len(text))

    def test_visible_len_cjk(self) -> None:
        """日本語全角文字: 幅 = 2 × 文字数。"""
        text = "テスト"  # 3文字
        self.assertEqual(self.c._visible_len(text), 6)

    def test_visible_len_ansi(self) -> None:
        """ANSI エスケープ付き: エスケープは幅 0。"""
        text = "\033[1mhello\033[0m"  # "hello" のみ
        self.assertEqual(self.c._visible_len(text), 5)

    def test_visible_len_mixed(self) -> None:
        """ASCII + CJK + ANSI 混在。"""
        # "AB" (2) + "テスト" (6) = 8、ANSI は除外
        text = "\033[32mAB\033[0mテスト"
        self.assertEqual(self.c._visible_len(text), 8)


class TestQuestionnaireTable(unittest.TestCase):
    """questionnaire_table() の動作検証。"""

    def setUp(self) -> None:
        self.c = _make_console()

    def _capture_table(self, questions: list[QAQuestion]) -> str:
        buf = io.StringIO()
        with unittest.mock.patch("sys.stdout", buf):
            self.c.questionnaire_table(questions)
        return buf.getvalue()

    def test_questionnaire_table_output(self) -> None:
        """ヘッダーとデータ行が出力に含まれること。"""
        q = _make_question(no=1, question="○○を選択しますか？")
        output = self._capture_table([q])
        self.assertIn("質問", output)
        self.assertIn("選択肢", output)
        self.assertIn("デフォルトの回答案", output)
        self.assertIn("回答案の理由", output)
        self.assertIn("○○を選択しますか？", output)
        self.assertIn("1", output)

    def test_questionnaire_table_empty(self) -> None:
        """空リストでエラーにならず、何も出力しないこと。"""
        output = self._capture_table([])
        self.assertEqual(output, "")

    def test_questionnaire_table_multiple_rows(self) -> None:
        """複数質問を渡したとき各 No. が出力に含まれること。"""
        questions = [
            _make_question(no=1, question="質問1"),
            _make_question(no=2, question="質問2"),
        ]
        output = self._capture_table(questions)
        self.assertIn("1", output)
        self.assertIn("2", output)
        self.assertIn("質問1", output)
        self.assertIn("質問2", output)


class TestPromptAnswerMode(unittest.TestCase):
    """prompt_answer_mode() の動作検証。"""

    def setUp(self) -> None:
        self.c = _make_console()

    def test_prompt_answer_mode_all(self) -> None:
        """stdin に "1" → "all" を返す。"""
        with unittest.mock.patch("builtins.input", return_value="1"):
            result = self.c.prompt_answer_mode()
        self.assertEqual(result, "all")

    def test_prompt_answer_mode_one(self) -> None:
        """stdin に "2" → "one" を返す。"""
        with unittest.mock.patch("builtins.input", return_value="2"):
            result = self.c.prompt_answer_mode()
        self.assertEqual(result, "one")


class TestPromptQuestionAnswer(unittest.TestCase):
    """prompt_question_answer() の動作検証。"""

    def setUp(self) -> None:
        self.c = _make_console()

    def test_prompt_question_answer_valid(self) -> None:
        """有効な選択肢入力 → ラベルを返す。"""
        q = _make_question(default_answer="A) はい")
        with unittest.mock.patch("builtins.input", return_value="B"):
            result = self.c.prompt_question_answer(q)
        self.assertEqual(result, "B")

    def test_prompt_question_answer_empty_default(self) -> None:
        """空入力 → デフォルトラベル（"A"）を返す。

        prompt_input が空入力時に default_label を返すため、
        有効ラベルとして "A" が返却される。
        これは QAMerger.parse_answers が期待する形式（ラベル文字列）に合致する。
        """
        q = _make_question(default_answer="A) はい")
        # prompt_input は空入力時 default_label ("A") を返す → 有効ラベルとして "A" が返る
        with unittest.mock.patch("builtins.input", return_value=""):
            result = self.c.prompt_question_answer(q)
        self.assertEqual(result, "A")

    def test_prompt_question_answer_freetext(self) -> None:
        """選択肢なし質問 → プロンプトなしでデフォルト回答のラベルを返す。

        QAMerger.parse_answers() はラベル入力のみ処理できるため、
        choices=[] の質問は自由テキスト入力を受け付けず default_answer のラベルを返す。
        """
        q = QAQuestion(
            no=1,
            question="自由記述質問",
            choices=[],  # 選択肢なし
            default_answer="A) デフォルトテキスト",
            reason="理由",
        )
        # choices == [] なので入力を求めずデフォルトラベルを返す
        result = self.c.prompt_question_answer(q)
        self.assertEqual(result, "A")


class TestAnswerSummary(unittest.TestCase):
    """answer_summary() の動作検証。"""

    def setUp(self) -> None:
        self.c = _make_console()

    def _capture_summary(
        self,
        questions: list[QAQuestion],
        answers: dict[int, str],
    ) -> str:
        buf = io.StringIO()
        with unittest.mock.patch("sys.stdout", buf):
            self.c.answer_summary(questions, answers)
        return buf.getvalue()

    def test_answer_summary_output(self) -> None:
        """変更数 / デフォルト数が正しくカウントされる。"""
        questions = [
            _make_question(no=1, default_answer="A) はい"),
            _make_question(no=2, default_answer="A) はい"),
            _make_question(no=3, default_answer="A) はい"),
        ]
        # No.1 はデフォルト採用、No.2 は変更（B）、No.3 はデフォルト採用
        answers = {1: "A", 2: "B", 3: "A"}
        output = self._capture_summary(questions, answers)
        self.assertIn("3", output)   # 全質問数
        self.assertIn("1", output)   # 回答変更
        self.assertIn("回答サマリー", output)


class TestCollectQaAnswersNonTty(unittest.TestCase):
    """_collect_qa_answers() の非 TTY フォールバック動作を検証する。

    実際の runner._collect_qa_answers() 関数を呼び出すため、
    実装が壊れた場合もこのテストで検出できる。
    """

    def _make_doc(self) -> QADocument:
        doc = QADocument(title="テスト質問票")
        doc.questions = [_make_question(no=1), _make_question(no=2)]
        return doc

    def test_non_tty_skips_mode_and_uses_defaults(self) -> None:
        """非 TTY 時: questionnaire_table は呼ばれ、prompt_answer_mode は呼ばれず skip=True。"""
        c = _make_console()
        doc = self._make_doc()
        cfg = SDKConfig(dry_run=True, model="claude-opus-4.6")

        table_called = []
        mode_called = []

        with unittest.mock.patch.object(
            c, "questionnaire_table", side_effect=lambda *a, **kw: table_called.append(True)
        ), unittest.mock.patch.object(
            c, "prompt_answer_mode", side_effect=lambda: mode_called.append(True) or "all"
        ), unittest.mock.patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            raw, skip = asyncio.run(_collect_qa_answers(c, doc, "1.1", cfg))

        self.assertTrue(table_called, "questionnaire_table は呼ばれるべき")
        self.assertFalse(mode_called, "非 TTY 時は prompt_answer_mode を呼ばないべき")
        self.assertTrue(skip, "非 TTY 時は skip_input=True のはず")
        self.assertEqual(raw, "", "非 TTY 時は user_answers_raw は空のはず")


if __name__ == "__main__":
    unittest.main()
