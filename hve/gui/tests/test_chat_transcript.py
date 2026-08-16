"""FR-GUI-18: 実行ジョブタブの会話ビュー（``ChatTranscriptView``）。

VS Code のチャットビューと同じく、送信メッセージ・ACK・GUI 通知・宛先の実行ログを
1 本の時系列列へ並べる。会話バブルにしてよいのは HVE 自身が発生源の要素だけで、
実行ログは生ログのまま扱い、行を解析して役割やターン境界を推定しない（FR-GUI-13）。
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from hve.gui.fonts import preferred_log_font
from hve.gui.widgets.chat_transcript import ChatTranscriptView


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(qapp) -> ChatTranscriptView:
    return ChatTranscriptView()


_VIEW_HEIGHT = 200
_LOG_LINES_PER_TURN = 40


def _laid_out_view(turns: int = 3, *, trailing_log: bool = True) -> ChatTranscriptView:
    """スクロール可能な高さまで積んだうえで、ジオメトリを確定させたビューを返す。

    ``trailing_log=False`` は最後のターンの後ろにログを置かない。最終ターンの
    ``y`` がスクロール上限を超え、上端へ寄せきれない状況を作るために使う。
    """
    view = ChatTranscriptView()
    view.resize(400, _VIEW_HEIGHT)
    for i in range(turns):
        view.append_user(f"送信 {i}", action_label="キューに追加", request_id=f"r{i}")
        if trailing_log or i < turns - 1:
            for j in range(_LOG_LINES_PER_TURN):
                view.append_log(f"log {i}-{j}")
    view.show()
    QApplication.processEvents()
    return view


def _log_block_height(view: ChatTranscriptView) -> int:
    entry = view._trailing_log_entry()
    assert entry is not None, "前提: 末尾にログブロックがあること"
    return entry.height()


class TestUserBubble:
    def test_user_message_becomes_a_bubble_entry(self, view: ChatTranscriptView) -> None:
        view.append_user("進捗を教えて", action_label="いま割り込む", request_id="r1")
        assert view.entry_kinds() == ["user"]
        assert "進捗を教えて" in view.plain_text()

    def test_user_bubble_shows_the_selected_action(self, view: ChatTranscriptView) -> None:
        view.append_user("hello", action_label="キューに追加", request_id="r1")
        assert "キューに追加" in view.plain_text()

    def test_entries_keep_their_chronological_order(self, view: ChatTranscriptView) -> None:
        view.append_user("a", action_label="いま割り込む", request_id="r1")
        view.append_log("log-1")
        view.append_notice("note")
        assert view.entry_kinds() == ["user", "log", "notice"]
        assert view.plain_text().splitlines()[-1] == "note"

    def test_multiline_message_stays_in_one_entry(self, view: ChatTranscriptView) -> None:
        view.append_user("一行目\n二行目", action_label="いま割り込む", request_id="r1")
        assert view.entry_kinds() == ["user"]
        assert "二行目" in view.plain_text()


class TestAckBadge:
    def test_ack_updates_the_matching_bubble_without_adding_an_entry(
        self, view: ChatTranscriptView
    ) -> None:
        view.append_user("hello", action_label="いま割り込む", request_id="r1")
        assert view.update_ack("r1", "accepted") is True
        assert view.entry_kinds() == ["user"]
        assert "accepted" in view.plain_text()

    def test_ack_detail_is_shown(self, view: ChatTranscriptView) -> None:
        view.append_user("hello", action_label="いま割り込む", request_id="r1")
        view.update_ack("r1", "failed", "RuntimeError")
        text = view.plain_text()
        assert "failed" in text
        assert "RuntimeError" in text

    def test_ack_for_an_unknown_request_is_reported(self, view: ChatTranscriptView) -> None:
        assert view.update_ack("ghost", "accepted") is False

    def test_ack_targets_only_its_own_bubble(self, view: ChatTranscriptView) -> None:
        view.append_user("first", action_label="いま割り込む", request_id="r1")
        view.append_user("second", action_label="キューに追加", request_id="r2")
        view.update_ack("r2", "cancelled")
        lines = view.plain_text().splitlines()
        assert "cancelled" not in lines[0]
        assert "cancelled" in lines[1]


class TestLogBlock:
    def test_consecutive_log_lines_merge_into_one_block(self, view: ChatTranscriptView) -> None:
        view.append_log("a")
        view.append_log("b")
        assert view.entry_kinds() == ["log"]
        assert view.plain_text().splitlines() == ["a", "b"]

    def test_a_message_splits_the_log_block(self, view: ChatTranscriptView) -> None:
        view.append_log("a")
        view.append_notice("n")
        view.append_log("b")
        assert view.entry_kinds() == ["log", "notice", "log"]

    def test_snapshot_replaces_the_whole_transcript(self, view: ChatTranscriptView) -> None:
        view.append_user("x", action_label="いま割り込む", request_id="r1")
        view.set_log_snapshot(["line-a", "line-b"])
        assert view.entry_kinds() == ["log"]
        assert view.plain_text().splitlines() == ["line-a", "line-b"]

    def test_empty_snapshot_leaves_no_entry(self, view: ChatTranscriptView) -> None:
        view.append_log("a")
        view.set_log_snapshot([])
        assert view.entry_kinds() == []
        assert view.plain_text() == ""

    def test_log_lines_are_not_parsed_for_roles(self, view: ChatTranscriptView) -> None:
        """FR-GUI-13: ログ行から発話者・役割・ターン境界を推定しない。"""
        line = "[06:22:13] [AAS] [1] assistant: 完了しました"
        view.append_log(line)
        assert view.entry_kinds() == ["log"]
        assert view.plain_text() == line

    def test_log_block_uses_the_shared_log_font(self, view: ChatTranscriptView) -> None:
        view.append_log("a")
        assert view.log_font().family() == preferred_log_font().family()

    def test_appended_lines_grow_the_block(self, view: ChatTranscriptView) -> None:
        """実行中の 1 行追記でも高さが追従する（潰れて行が見えなくならない）。"""
        view.append_log("line 0")
        one_line = _log_block_height(view)
        for i in range(1, 40):
            view.append_log(f"line {i}")
        assert _log_block_height(view) > one_line * 10

    def test_snapshot_and_appended_lines_reach_the_same_height(
        self, view: ChatTranscriptView
    ) -> None:
        lines = [f"line {i}" for i in range(40)]
        view.set_log_snapshot(lines)
        snapshot_height = _log_block_height(view)

        view.clear()
        for line in lines:
            view.append_log(line)
        assert _log_block_height(view) == snapshot_height


class TestTranscriptReset:
    def test_clear_removes_all_entries(self, view: ChatTranscriptView) -> None:
        view.append_user("a", action_label="いま割り込む", request_id="r1")
        view.append_log("b")
        view.clear()
        assert view.entry_kinds() == []
        assert view.plain_text() == ""

    def test_cleared_view_accepts_new_entries(self, view: ChatTranscriptView) -> None:
        view.append_log("a")
        view.clear()
        view.append_log("b")
        assert view.plain_text() == "b"

    def test_clear_forgets_previous_request_ids(self, view: ChatTranscriptView) -> None:
        view.append_user("a", action_label="いま割り込む", request_id="r1")
        view.clear()
        assert view.update_ack("r1", "accepted") is False


class TestUserTurns:
    """FR-GUI-18: ターン（利用者の送信メッセージ）の列挙と本文取得。"""

    def test_only_user_messages_are_counted_as_turns(self, view: ChatTranscriptView) -> None:
        view.append_user("a", action_label="キューに追加", request_id="r1")
        view.append_notice("送信できません")
        view.append_log("[06:22] step start")
        view.append_user("b", action_label="いま割り込む", request_id="r2")
        assert view.user_turn_count() == 2

    def test_turn_text_is_the_body_without_the_action_label(
        self, view: ChatTranscriptView
    ) -> None:
        view.append_user("進捗を教えて", action_label="キューに追加", request_id="r1")
        assert view.user_turn_text(0) == "進捗を教えて"

    def test_turn_text_does_not_change_when_the_ack_arrives(
        self, view: ChatTranscriptView
    ) -> None:
        view.append_user("進捗を教えて", action_label="キューに追加", request_id="r1")
        view.update_ack("r1", "failed", "RuntimeError")
        assert view.user_turn_text(0) == "進捗を教えて"

    def test_turn_text_out_of_range_is_empty(self, view: ChatTranscriptView) -> None:
        view.append_user("a", action_label="キューに追加", request_id="r1")
        assert view.user_turn_text(-1) == ""
        assert view.user_turn_text(1) == ""

    def test_without_turns_there_is_no_current_index(self, view: ChatTranscriptView) -> None:
        view.append_log("ログだけ")
        assert view.user_turn_count() == 0
        assert view.current_user_turn_index() == -1

    def test_clear_forgets_every_turn(self, view: ChatTranscriptView) -> None:
        view.append_user("a", action_label="キューに追加", request_id="r1")
        view.clear()
        assert view.user_turn_count() == 0
        assert view.current_user_turn_index() == -1

    def test_log_snapshot_leaves_no_turn(self, view: ChatTranscriptView) -> None:
        view.append_user("a", action_label="キューに追加", request_id="r1")
        view.set_log_snapshot(["line-a", "line-b"])
        assert view.user_turn_count() == 0

    def test_scrolling_to_an_out_of_range_turn_is_rejected(
        self, view: ChatTranscriptView
    ) -> None:
        view.append_user("a", action_label="キューに追加", request_id="r1")
        assert view.scroll_to_user_turn(-1) is False
        assert view.scroll_to_user_turn(1) is False
        assert view.scroll_to_user_turn(0) is True


class TestTurnScrollTracking:
    """FR-GUI-18: スクロール位置から現在ターンを決める。"""

    def test_top_of_the_conversation_reports_the_first_turn(self, qapp) -> None:
        view = _laid_out_view()
        view.verticalScrollBar().setValue(0)
        assert view.current_user_turn_index() == 0

    def test_scrolling_to_a_turn_makes_it_current(self, qapp) -> None:
        view = _laid_out_view()
        assert view.scroll_to_user_turn(1) is True
        assert view.current_user_turn_index() == 1

    def test_scrolling_aligns_the_turn_with_the_top_of_the_viewport(self, qapp) -> None:
        """1 ピクセル戻すだけで直前のターンへ変わる = ちょうど上端へ揃っている。"""
        view = _laid_out_view()
        assert view.scroll_to_user_turn(1) is True
        bar = view.verticalScrollBar()
        assert 0 < bar.value() < bar.maximum()
        bar.setValue(bar.value() - 1)
        assert view.current_user_turn_index() == 0

    def test_last_turn_is_current_even_when_it_cannot_reach_the_top(self, qapp) -> None:
        """スクロール上限で頭打ちになっても番号が移動先と食い違わない。"""
        view = _laid_out_view(trailing_log=False)
        bar = view.verticalScrollBar()
        last = view.user_turn_count() - 1
        assert view.scroll_to_user_turn(last) is True
        assert bar.value() == bar.maximum(), (
            "前提: 最終ターンを上端へ寄せきれずクランプされる配置であること"
        )
        assert view.current_user_turn_index() == last
