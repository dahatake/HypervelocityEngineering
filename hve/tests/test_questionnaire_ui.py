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


class TestCollectQaAnswersWithPresetMode(unittest.TestCase):
    """_collect_qa_answers() で config.qa_answer_mode が設定済みの場合の動作検証。

    ウィザードで事前に選択した回答モード（"all" or "one"）が
    config.qa_answer_mode に設定されているとき、
    実行時に prompt_answer_mode() が呼ばれず、設定値がそのまま使われることを確認する。
    """

    def _make_doc(self) -> QADocument:
        doc = QADocument(title="テスト質問票")
        doc.questions = [_make_question(no=1), _make_question(no=2)]
        return doc

    def test_preset_mode_all_skips_prompt_answer_mode(self) -> None:
        """config.qa_answer_mode='all' → prompt_answer_mode は呼ばれず、一括入力フローが使われる。"""
        c = _make_console()
        doc = self._make_doc()
        cfg = SDKConfig(dry_run=True, model="claude-opus-4.6", qa_answer_mode="all")

        mode_called = []

        async def fake_read_multiline(*args, **kwargs):
            return "1: A\n2: B"

        with unittest.mock.patch.object(
            c, "prompt_answer_mode", side_effect=lambda: mode_called.append(True) or "one"
        ), unittest.mock.patch.object(
            c, "questionnaire_table"
        ), unittest.mock.patch.object(
            c, "answer_summary"
        ), unittest.mock.patch("sys.stdin") as mock_stdin, \
        unittest.mock.patch("runner._read_stdin_multiline", side_effect=fake_read_multiline):
            mock_stdin.isatty.return_value = True
            raw, skip = asyncio.run(_collect_qa_answers(c, doc, "1.1", cfg))

        self.assertFalse(mode_called, "qa_answer_mode 設定済みなら prompt_answer_mode を呼ばないべき")
        self.assertFalse(skip)
        self.assertIn("1: A", raw)

    def test_preset_mode_one_skips_prompt_answer_mode(self) -> None:
        """config.qa_answer_mode='one' → prompt_answer_mode は呼ばれず、1問ずつフローが使われる。"""
        c = _make_console()
        doc = self._make_doc()
        cfg = SDKConfig(dry_run=True, model="claude-opus-4.6", qa_answer_mode="one")

        mode_called = []

        with unittest.mock.patch.object(
            c, "prompt_answer_mode", side_effect=lambda: mode_called.append(True) or "all"
        ), unittest.mock.patch.object(
            c, "questionnaire_table"
        ), unittest.mock.patch.object(
            c, "answer_summary"
        ), unittest.mock.patch.object(
            c, "prompt_question_answer", return_value="A"
        ), unittest.mock.patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            raw, skip = asyncio.run(_collect_qa_answers(c, doc, "1.1", cfg))

        self.assertFalse(mode_called, "qa_answer_mode 設定済みなら prompt_answer_mode を呼ばないべき")
        self.assertFalse(skip)
        self.assertIn("1: A", raw)
        self.assertIn("2: A", raw)


class TestCollectQaAnswersNonTtyWarning(unittest.TestCase):
    """非 TTY 時に console.warning() が呼ばれることを検証する。"""

    def _make_doc(self) -> QADocument:
        doc = QADocument(title="テスト質問票")
        doc.questions = [_make_question(no=1), _make_question(no=2)]
        return doc

    def test_non_tty_calls_console_warning(self) -> None:
        """非 TTY 時: console.warning() が呼ばれ、内容に非対話モードの旨が含まれること。"""
        c = _make_console()
        doc = self._make_doc()
        cfg = SDKConfig(dry_run=True, model="claude-opus-4.6")

        warning_messages = []

        with unittest.mock.patch.object(
            c, "questionnaire_table"
        ), unittest.mock.patch.object(
            c, "status"
        ), unittest.mock.patch.object(
            c, "warning", side_effect=lambda msg: warning_messages.append(msg)
        ), unittest.mock.patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            raw, skip = asyncio.run(_collect_qa_answers(c, doc, "1.1", cfg))

        self.assertTrue(skip, "非 TTY 時は skip=True のはず")
        self.assertTrue(warning_messages, "非 TTY 時は console.warning() が呼ばれるべき")
        combined = "\n".join(warning_messages)
        self.assertIn("非対話", combined, "警告メッセージに非対話モードの旨が含まれるべき")


class TestCollectQaAnswersForceInteractive(unittest.TestCase):
    """force_interactive=True 時に TTY 判定をバイパスすることを検証する。"""

    def _make_doc(self) -> QADocument:
        doc = QADocument(title="テスト質問票")
        doc.questions = [_make_question(no=1), _make_question(no=2)]
        return doc

    def test_force_interactive_bypasses_tty_check(self) -> None:
        """force_interactive=True 時: sys.stdin.isatty()=False でも prompt_answer_mode が呼ばれる。"""
        c = _make_console()
        doc = self._make_doc()
        cfg = SDKConfig(dry_run=True, model="claude-opus-4.6", force_interactive=True)

        mode_called = []

        async def fake_read_multiline(*args, **kwargs):
            return "1: A\n2: B"

        with unittest.mock.patch.object(
            c, "questionnaire_table"
        ), unittest.mock.patch.object(
            c, "answer_summary"
        ), unittest.mock.patch.object(
            c, "prompt_answer_mode", side_effect=lambda: mode_called.append(True) or "all"
        ), unittest.mock.patch("sys.stdin") as mock_stdin, \
        unittest.mock.patch("runner._read_stdin_multiline", side_effect=fake_read_multiline):
            mock_stdin.isatty.return_value = False  # TTY ではない
            raw, skip = asyncio.run(_collect_qa_answers(c, doc, "1.1", cfg))

        self.assertTrue(mode_called, "force_interactive=True 時は prompt_answer_mode が呼ばれるべき")
        self.assertFalse(skip, "force_interactive=True 時は skip=False のはず")


class TestSkipInputNoAnswerSummary(unittest.TestCase):
    """skip_input=True 時に answer_summary() が呼ばれないことを検証する。"""

    def _make_doc(self) -> QADocument:
        doc = QADocument(title="テスト質問票")
        doc.questions = [_make_question(no=1)]
        return doc

    def test_skip_input_calls_status_not_answer_summary(self) -> None:
        """非 TTY (skip_input=True) 時: answer_summary は呼ばれず status が呼ばれること。"""
        c = _make_console()
        doc = self._make_doc()
        cfg = SDKConfig(dry_run=True, model="claude-opus-4.6")

        summary_called = []
        status_called = []

        with unittest.mock.patch.object(
            c, "questionnaire_table"
        ), unittest.mock.patch.object(
            c, "warning"
        ), unittest.mock.patch.object(
            c, "answer_summary", side_effect=lambda *a, **kw: summary_called.append(True)
        ), unittest.mock.patch.object(
            c, "status", side_effect=lambda msg: status_called.append(msg)
        ), unittest.mock.patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            asyncio.run(_collect_qa_answers(c, doc, "1.1", cfg))

        self.assertFalse(summary_called, "skip_input=True 時は answer_summary を呼ばないべき")
        self.assertTrue(status_called, "skip_input=True 時は status が呼ばれるべき")


class TestCharWidth(unittest.TestCase):
    """_char_width() の基本動作検証。"""

    def test_ascii_is_1(self) -> None:
        """ASCII 文字の幅は 1。"""
        self.assertEqual(Console._char_width("a"), 1)
        self.assertEqual(Console._char_width("Z"), 1)
        self.assertEqual(Console._char_width("0"), 1)

    def test_fullwidth_is_2(self) -> None:
        """全角文字の幅は 2。"""
        self.assertEqual(Console._char_width("あ"), 2)
        self.assertEqual(Console._char_width("テ"), 2)
        self.assertEqual(Console._char_width("漢"), 2)


class TestWrapText(unittest.TestCase):
    """_wrap_text() の動作検証。"""

    def test_short_text_no_wrap(self) -> None:
        """折り返し不要な短文はそのまま1要素リストを返す。"""
        result = Console._wrap_text("hello", 20)
        self.assertEqual(result, ["hello"])

    def test_empty_string(self) -> None:
        """空文字列は [""] を返す。"""
        result = Console._wrap_text("", 20)
        self.assertEqual(result, [""])

    def test_fullwidth_long_preserves_all_chars(self) -> None:
        """全角長文の折り返しで全文字が保持される。"""
        text = "あいうえおかきくけこさしすせそたちつてとなにぬねの"
        result = Console._wrap_text(text, 10)
        self.assertEqual("".join(result), text)

    def test_ascii_long_wraps(self) -> None:
        """ASCII 長文が折り返される。"""
        text = "a" * 50
        result = Console._wrap_text(text, 10)
        self.assertGreater(len(result), 1)
        self.assertEqual("".join(result), text)

    def test_kinsoku_head_not_at_line_start(self) -> None:
        """行頭禁則文字（。等）が行頭に来ないこと。"""
        # 幅10で、11文字目が「。」になるように構成
        text = "あいうえお。かきくけこ。"
        result = Console._wrap_text(text, 10)
        # 1行目は入力の先頭から始まるため行頭禁則文字が現れる可能性はない。
        # 2行目以降は禁則処理により行頭禁則文字が行頭に来ないことを検証する。
        for line in result[1:]:
            if line:
                self.assertNotIn(line[0], "。、．，）)」』】〕〉》｝}！？!?ー・：；…‥")

    def test_kinsoku_tail_not_at_line_end(self) -> None:
        """行末禁則文字（「等）が行末に来ないこと（行末禁則が効く場合）。"""
        # 幅10ちょうどで「が行末になる文字列を作る
        text = "あいうえ「かきくけこさ"
        result = Console._wrap_text(text, 10)
        for line in result[:-1]:  # 最終行以外をチェック
            if line:
                self.assertNotIn(line[-1], "（(「『【〔〈《｛{")

    def test_mixed_text_preserves_all_chars(self) -> None:
        """全角＋ASCII 混在テキストで全文字が保持される。"""
        text = "Test テスト ABC あいうえお XYZ かきくけこ"
        result = Console._wrap_text(text, 12)
        self.assertEqual("".join(result), text)

    def test_no_line_exceeds_max_width(self) -> None:
        """各行の表示幅が max_width を超えないこと。"""
        text = "あいうえおかきくけこ。さしすせそたちつてと。なにぬねの"
        max_w = 10
        result = Console._wrap_text(text, max_w)
        c = _make_console()
        for line in result:
            self.assertLessEqual(c._visible_len(line), max_w)


class TestQuestionnaireTableNoTruncation(unittest.TestCase):
    """questionnaire_table() で長文が省略されないことを検証する。"""

    def setUp(self) -> None:
        self.c = _make_console()
        # 非 TTY 強制（罫線文字のフィルタ不要で堅牢）
        self.c._is_tty = False

    def _capture_table(self, questions: list[QAQuestion]) -> str:
        buf = io.StringIO()
        with unittest.mock.patch("sys.stdout", buf):
            self.c.questionnaire_table(questions)
        return buf.getvalue()

    def test_long_question_not_truncated(self) -> None:
        """40幅超の質問文が省略されず全文表示されること。"""
        long_question = "出力先は Issue 指定どおり `docs/app-catalog.md` に準拠しますか？"
        q = _make_question(no=1, question=long_question)
        output = self._capture_table([q])
        self.assertNotIn("...", output)
        # 省略されていれば消えるはずの末尾付近のテキストが存在することを確認
        self.assertIn("log.md", output)
        self.assertIn("に準拠しますか", output)

    def test_long_choices_not_truncated(self) -> None:
        """40幅超の選択肢が省略されず全文表示されること。"""
        choices = [
            Choice(label="A", text="上書き再作成（既存ファイルを削除してから再生成）"),
            Choice(label="B", text="追記更新（既存ファイルに差分を追記）"),
        ]
        q = _make_question(no=1, choices=choices)
        output = self._capture_table([q])
        self.assertNotIn("...", output)
        # 省略されていれば消えるはずのテキストが存在することを確認
        self.assertIn("上書き再作成", output)
        self.assertIn("から再生成", output)
        self.assertIn("追記更新", output)

    def test_header_fifth_column_is_correct(self) -> None:
        """ヘッダー5列目が "回答案の理由" であること。"""
        q = _make_question(no=1)
        output = self._capture_table([q])
        self.assertIn("回答案の理由", output)
        self.assertNotIn("選択理由", output)


class TestQuestionnaireTableFixedWidth(unittest.TestCase):
    """ターミナル幅をモックしてテーブル幅を検証する。"""

    def setUp(self) -> None:
        self.c = _make_console()
        self.c._is_tty = False

    def _capture_with_width(self, questions: list[QAQuestion], term_width: int) -> str:
        buf = io.StringIO()
        with unittest.mock.patch("sys.stdout", buf), \
             unittest.mock.patch("shutil.get_terminal_size", return_value=unittest.mock.MagicMock(columns=term_width)):
            self.c.questionnaire_table(questions)
        return buf.getvalue()

    def _max_line_width(self, output: str) -> int:
        c = _make_console()
        return max((c._visible_len(line) for line in output.splitlines()), default=0)

    def test_width_80(self) -> None:
        """幅80でレンダリングしてもターミナル幅を超えないこと。"""
        questions = [
            _make_question(no=1, question="出力先は Issue 指定どおり `docs/app-catalog.md` に準拠しますか？"),
        ]
        output = self._capture_with_width(questions, 80)
        self.assertLessEqual(self._max_line_width(output), 80)

    def test_width_120(self) -> None:
        """幅120でレンダリングしてもターミナル幅を超えないこと。"""
        questions = [
            _make_question(no=1, question="出力先は Issue 指定どおり `docs/app-catalog.md` に準拠しますか？"),
        ]
        output = self._capture_with_width(questions, 120)
        self.assertLessEqual(self._max_line_width(output), 120)

    def test_width_200(self) -> None:
        """幅200でレンダリングしてもターミナル幅を超えないこと。"""
        questions = [
            _make_question(no=1, question="出力先は Issue 指定どおり `docs/app-catalog.md` に準拠しますか？"),
        ]
        output = self._capture_with_width(questions, 200)
        self.assertLessEqual(self._max_line_width(output), 200)


if __name__ == "__main__":
    unittest.main()
