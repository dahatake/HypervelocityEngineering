"""hve.gui.tests.test_copilot_chat_panel

``CopilotChatPanel`` のストリーミング表示ロジックの回帰テスト。

背景:
    `copilot -p`（非対話モード）の応答は ``QProcess.readyReadStandardOutput`` が
    細かい断片（サブワード単位）で発火する。断片ごとに
    ``QPlainTextEdit.appendPlainText`` で新しい段落を作ると、1 行が極端に短い
    断片の縦積みになり非常に読みづらい不具合が実運用で確認された。
    本テストは、断片が 1 つの連続した段落へ連結され、CJK 折り返しが適用され、
    ユーザーの既存テキスト選択が破壊されないことを検証する。

実 ``copilot`` CLI プロセスは一切起動しない。``QProcess`` の代わりに
``readAllStandardOutput()`` 互換の最小 Fake を ``panel._process`` に差し替えて
``_on_stdout()`` を直接呼び出す。
"""

from __future__ import annotations

import codecs
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtCore import QByteArray, QProcess, Qt  # noqa: E402
from PySide6.QtGui import QTextCursor, QTextOption  # noqa: E402
from PySide6.QtWidgets import QApplication, QPlainTextEdit  # noqa: E402

from hve.gui.copilot_chat_panel import CopilotChatPanel, _sanitize_stream_text  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def panel(qapp, tmp_path):
    p = CopilotChatPanel(repo_root=tmp_path)
    yield p
    p.shutdown()


class _FakeProcess:
    """``QProcess`` 互換の最小 Fake。``_on_stdout`` が使う API のみ実装する。"""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    def readAllStandardOutput(self) -> QByteArray:
        chunk = self._chunks.pop(0) if self._chunks else b""
        return QByteArray(chunk)

    def state(self) -> QProcess.ProcessState:
        # panel.shutdown() のガード（state() != NotRunning）を安全に通すため。
        return QProcess.ProcessState.NotRunning


# ---------------------------------------------------------------------------
# 断片の連結（報告された不具合の再現・回帰テスト）
# ---------------------------------------------------------------------------


def test_streaming_deltas_concatenate_into_single_paragraph(panel):
    """サブワード単位の断片が 1 つの段落へ連結され、prefix は 1 回のみ付与される。"""
    for delta in ("azure", "-services", "-add", "-itional", ".md"):
        panel._append_copilot_delta(delta)
    text = panel._history.toPlainText()
    assert text == "[Copilot] azure-services-add-itional.md"
    assert text.count("[Copilot]") == 1


def test_embedded_newline_creates_new_paragraph(panel):
    panel._append_copilot_delta("line1")
    panel._append_copilot_delta("\nline2")
    assert panel._history.toPlainText() == "[Copilot] line1\nline2"


def test_role_switch_closes_and_reopens_copilot_turn(panel):
    panel._append_copilot_delta("first response")
    panel._append("you", "next question")
    panel._append_copilot_delta("second response")
    text = panel._history.toPlainText()
    assert text.count("[Copilot]") == 2
    assert "[あなた] next question" in text


# ---------------------------------------------------------------------------
# \r / ANSI エスケープの正規化（QPlainTextEdit は端末エミュレータではないため
# 生のまま挿入すると表示が崩れる。実 copilot CLI は起動せず合成データで検証）
# ---------------------------------------------------------------------------


def test_ansi_escape_sequences_are_stripped(panel):
    panel._append_copilot_delta("\x1b[1mBold\x1b[0m normal \x1b[32mGreen\x1b[0m")
    assert panel._history.toPlainText() == "[Copilot] Bold normal Green"


def test_crlf_normalized_to_lf(panel):
    panel._append_copilot_delta("line1\r\nline2")
    assert panel._history.toPlainText() == "[Copilot] line1\nline2"


def test_lone_carriage_return_does_not_create_extra_paragraph(panel):
    """単独の `\\r`（スピナー等の行上書き）は除去し、余分な段落を作らない。

    ``QPlainTextEdit`` には端末のような「その場で上書き」機能がないため、
    `\\r` をそのまま挿入すると Qt が改段落として扱ってしまい、スピナーの全
    フレームが個別行として残ってしまう（実機検証済み）。
    """
    for frame in ("-", "\\", "|", "/"):
        panel._append_copilot_delta(f"\r{frame} thinking")
    text = panel._history.toPlainText()
    assert text == "[Copilot] - thinking\\ thinking| thinking/ thinking"
    assert text.count("\n") == 0


def test_pure_ansi_delta_does_not_open_empty_turn(panel):
    """断片がANSIエスケープのみ（サニタイズ後が空文字）の場合、空のターンを開始しない。"""
    panel._append_copilot_delta("\x1b[2K\x1b[1G")
    assert panel._history.toPlainText() == ""
    assert panel._copilot_turn_open is False
    # 後続の実テキストは正しく新規ターンとして開始される
    panel._append_copilot_delta("actual text")
    assert panel._history.toPlainText() == "[Copilot] actual text"


def test_sanitize_stream_text_unit() -> None:
    """``_sanitize_stream_text`` をパネル経由でなく直接単体検証する。"""
    assert _sanitize_stream_text("\x1b[31mred\x1b[0m") == "red"
    assert _sanitize_stream_text("a\r\nb") == "a\nb"
    assert _sanitize_stream_text("a\rb") == "ab"
    assert _sanitize_stream_text("plain text") == "plain text"
    assert _sanitize_stream_text("\x1b[2K\x1b[1G") == ""


# ---------------------------------------------------------------------------
# ターン境界の空行（you/Copilot の前のみ・system は詰める）
# ---------------------------------------------------------------------------


def test_blank_line_before_you_and_copilot_but_not_system(panel):
    panel._append("you", "Q1")
    panel._append("system", "running...")
    panel._append_copilot_delta("answer")
    panel._append("system", "done")
    panel._append("you", "Q2")
    expected = (
        "[あなた] Q1\n"
        "[system] running...\n"
        "\n"
        "[Copilot] answer\n"
        "[system] done\n"
        "\n"
        "[あなた] Q2"
    )
    assert panel._history.toPlainText() == expected


def test_no_leading_blank_line_for_first_message(panel):
    panel._append("you", "first ever message")
    assert panel._history.toPlainText() == "[あなた] first ever message"


# ---------------------------------------------------------------------------
# マルチバイト UTF-8 のチャンク境界分割（_on_stdout 経由）
# ---------------------------------------------------------------------------


def test_on_stdout_handles_utf8_split_across_reads(panel):
    data = "こんにちは".encode("utf-8")
    split = 7  # 3バイト境界(3,6,9,...)ではない位置で分割し、意図的に文字境界をまたぐ
    panel._process = _FakeProcess([data[:split], data[split:]])
    panel._on_stdout()
    panel._on_stdout()
    assert panel._history.toPlainText() == "[Copilot] こんにちは"


def test_on_stdout_ignores_empty_read(panel):
    panel._process = _FakeProcess([b""])
    panel._on_stdout()
    assert panel._history.toPlainText() == ""


# ---------------------------------------------------------------------------
# finalize（プロセス終了時のデコーダ flush）
# ---------------------------------------------------------------------------


def test_finalize_copilot_stream_noop_without_decoder(panel):
    panel._utf8_decoder = None
    panel._finalize_copilot_stream()
    assert panel._utf8_decoder is None
    assert panel._history.toPlainText() == ""


def test_finalize_copilot_stream_resets_decoder(panel):
    panel._utf8_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    panel._finalize_copilot_stream()
    assert panel._utf8_decoder is None


# ---------------------------------------------------------------------------
# CJK 折り返し（他のログ系ペインと同一 policy）
# ---------------------------------------------------------------------------


def test_history_view_has_cjk_wrap_applied(panel):
    assert panel._history.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
    assert panel._history.wordWrapMode() == QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere
    assert panel._history.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff


# ---------------------------------------------------------------------------
# 既存のテキスト選択を破壊しないこと
# ---------------------------------------------------------------------------


def test_append_copilot_delta_preserves_existing_selection(panel):
    panel._append_copilot_delta("Hello World response paragraph.")
    doc_text = panel._history.toPlainText()
    start = doc_text.index("Hello")
    end = start + len("Hello")
    sel = panel._history.textCursor()
    sel.setPosition(start)
    sel.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    panel._history.setTextCursor(sel)

    before = panel._history.textCursor().selectedText()
    panel._append_copilot_delta(" and more streamed text")
    after = panel._history.textCursor().selectedText()

    assert before == after == "Hello"
