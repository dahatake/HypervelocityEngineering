"""FR-GUI-18: Copilot パネル「実行ジョブ」タブの VS Code チャット同等 UI。

会話ビュー / 送信待ちキュー / 入力ボックス / 状態行の組み立てと、
未消費要求の取り消し・並べ替えを固定する。QtWebEngine を読み込まないよう、
端末ビューと対話セッションは注入可能なファクトリで差し替える。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget

from hve.gui.copilot_chat_panel import CopilotChatPanel
from hve.gui.job_interaction_model import JobTarget
from hve.gui.widgets.chat_input_box import ChatInputBox
from hve.gui.widgets.chat_transcript import ChatTranscriptView
from hve.job_interaction_ipc import (
    claim_request,
    list_pending_requests,
    list_request_paths,
    write_ack,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _FakeSession:
    def __init__(self) -> None:
        self.starts: List[Optional[str]] = []
        self._running = False

    def start(self, *, initial_prompt: Optional[str] = None) -> None:
        self.starts.append(initial_prompt)
        self._running = True

    def stop(self) -> None:
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def set_repo_root(self, repo_root: Path) -> None:
        pass


class _FakePage:
    def __init__(self, targets: List[JobTarget], *, work_root: Optional[Path] = None) -> None:
        self._targets = targets
        self._work_root = work_root
        self.snapshots: Dict[str, List[str]] = {"": []}

    def job_targets(self) -> List[JobTarget]:
        return list(self._targets)

    def job_log_snapshot(self, target: JobTarget) -> List[str]:
        return list(self.snapshots.get(target.step_id or "", []))

    def session_work_root(self) -> Optional[Path]:
        return self._work_root

    def session_artifacts(self):
        return []


def _running_target(channel: Optional[Path]) -> JobTarget:
    return JobTarget(
        instance_id="asdw-web#APP-001",
        workflow_id="asdw-web",
        label="ASDW-WEB (APP-001)",
        step_id="1.2",
        step_title="Data Implementation",
        status="running",
        channel_dir=str(channel) if channel else None,
    )


def _finished_target() -> JobTarget:
    return JobTarget(
        instance_id="aad-web#APP-001",
        workflow_id="aad-web",
        label="AAD-WEB (APP-001)",
        step_id=None,
        step_title="",
        status="failed",
        channel_dir=None,
        returncode=1,
    )


def _make_panel(tmp_path: Path) -> CopilotChatPanel:
    return CopilotChatPanel(
        repo_root=tmp_path,
        terminal_factory=lambda: QWidget(),
        session_factory=lambda view, repo_root: _FakeSession(),
    )


def _panel_with_running_job(tmp_path: Path) -> tuple[CopilotChatPanel, Path]:
    channel = tmp_path / "ipc"
    channel.mkdir(exist_ok=True)
    panel = _make_panel(tmp_path)
    panel.set_workbench_page(_FakePage([_running_target(channel)]))
    return panel, channel


class TestJobTabComposition:
    def test_transcript_and_input_box_replace_the_flat_log_view(self, qapp, tmp_path: Path) -> None:
        panel = _make_panel(tmp_path)
        assert isinstance(panel._transcript, ChatTranscriptView)
        assert isinstance(panel._input_box, ChatInputBox)

    def test_sections_are_stacked_in_the_vs_code_order(self, qapp, tmp_path: Path) -> None:
        panel = _make_panel(tmp_path)
        layout = panel._job_tab_layout
        order = [
            layout.indexOf(panel._turn_nav_bar),
            layout.indexOf(panel._transcript),
            layout.indexOf(panel._pending_bar),
            layout.indexOf(panel._input_box),
            layout.indexOf(panel._status_footer),
        ]
        assert all(index >= 0 for index in order)
        assert order == sorted(order)

    def test_submitting_from_the_input_box_sends_the_selected_action(
        self, qapp, tmp_path: Path
    ) -> None:
        panel, channel = _panel_with_running_job(tmp_path)
        panel._input_box.select_action("中断して送信")
        panel._input_box.set_text("方針を変えて")
        panel._input_box.submitted.emit()

        pending = list_pending_requests(channel, "1.2")
        assert [(r.action, r.text) for r in pending] == [("stop_and_send", "方針を変えて")]

    def test_attachment_paths_are_included_in_the_sent_text(self, qapp, tmp_path: Path) -> None:
        panel, channel = _panel_with_running_job(tmp_path)
        panel._input_box.set_text("見てほしい")
        panel._input_box.add_attachment("docs/business-requirement.md")
        panel._input_box.submitted.emit()

        text = list_pending_requests(channel, "1.2")[0].text
        assert "見てほしい" in text
        assert "docs/business-requirement.md" in text

    def test_successful_send_clears_the_input_and_attachments(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        panel._input_box.set_text("hello")
        panel._input_box.add_attachment("docs/a.md")
        panel._input_box.submitted.emit()
        assert panel._input_box.text() == ""
        assert panel._input_box.attachments() == ()

    def test_rejected_send_keeps_the_input(self, qapp, tmp_path: Path) -> None:
        panel = _make_panel(tmp_path)
        panel.set_workbench_page(_FakePage([_finished_target()]))
        panel._input_box.set_text("hello")
        panel._input_box.submitted.emit()
        assert panel._input_box.text() == "hello"

    def test_composed_text_over_the_input_limit_is_not_sent(self, qapp, tmp_path: Path) -> None:
        panel, channel = _panel_with_running_job(tmp_path)
        panel._input_box.set_text("あ" * 2000)
        panel._input_box.add_attachment("x" * 3000)
        panel._input_box.submitted.emit()
        assert list_pending_requests(channel, "1.2") == []
        assert "上限" in panel.job_log_text()

    def test_sent_message_appears_as_a_conversation_entry(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        panel.send_job_message("進捗を教えて")
        assert panel._transcript.entry_kinds() == ["user"]
        assert "進捗を教えて" in panel.job_log_text()


class TestPendingQueue:
    def test_pending_requests_are_listed_in_processing_order(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        panel.send_job_message("first")
        panel.send_job_message("second")
        panel.refresh_pending_queue()
        assert panel.pending_request_labels() == ["first", "second"]

    def test_queue_is_hidden_when_there_is_nothing_pending(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        panel.refresh_pending_queue()
        assert panel._pending_bar.isHidden() is True

    def test_queue_becomes_visible_once_a_request_is_pending(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        panel.send_job_message("first")
        panel.refresh_pending_queue()
        assert panel._pending_bar.isHidden() is False

    def test_cancelling_removes_the_request_from_the_channel(self, qapp, tmp_path: Path) -> None:
        panel, channel = _panel_with_running_job(tmp_path)
        panel.send_job_message("first")
        panel.send_job_message("second")
        panel.refresh_pending_queue()
        panel.select_pending_row(0)
        assert panel.cancel_selected_pending() is True
        assert [r.text for r in list_pending_requests(channel, "1.2")] == ["second"]

    def test_moving_a_request_changes_the_processing_order(self, qapp, tmp_path: Path) -> None:
        panel, channel = _panel_with_running_job(tmp_path)
        panel.send_job_message("first")
        panel.send_job_message("second")
        panel.refresh_pending_queue()
        panel.select_pending_row(1)
        assert panel.move_selected_pending(-1) is True
        assert [r.text for r in list_pending_requests(channel, "1.2")] == ["second", "first"]

    def test_moving_beyond_the_edge_is_rejected(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        panel.send_job_message("only")
        panel.refresh_pending_queue()
        panel.select_pending_row(0)
        assert panel.move_selected_pending(-1) is False

    def test_operations_without_a_selection_are_rejected(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        panel.send_job_message("only")
        panel.refresh_pending_queue()
        panel.select_pending_row(-1)
        assert panel.cancel_selected_pending() is False
        assert panel.move_selected_pending(-1) is False

    def test_claimed_requests_leave_the_queue(self, qapp, tmp_path: Path) -> None:
        """FR-GUI-12: 処理中・処理済みの要求は取り消し・並べ替えの対象にしない。"""
        panel, channel = _panel_with_running_job(tmp_path)
        panel.send_job_message("first")
        claim_request(list_request_paths(channel, "1.2")[0])
        panel.refresh_pending_queue()
        assert panel.pending_request_labels() == []

    def test_finished_target_has_no_queue(self, qapp, tmp_path: Path) -> None:
        panel = _make_panel(tmp_path)
        panel.set_workbench_page(_FakePage([_finished_target()]))
        panel.refresh_pending_queue()
        assert panel.pending_request_labels() == []
        assert panel._pending_bar.isHidden() is True


class TestStatusFooter:
    def test_footer_reports_state_channel_and_queue_depth(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        panel.send_job_message("first")
        panel.send_job_message("second")
        panel.refresh_pending_queue()
        text = panel.status_footer_text()
        assert "running" in text
        assert "利用できます" in text
        assert "送信待ち" in text
        assert "2" in text

    def test_footer_reports_a_missing_selection(self, qapp, tmp_path: Path) -> None:
        panel = _make_panel(tmp_path)
        panel.set_workbench_page(_FakePage([]))
        assert "選択" in panel.status_footer_text()

    def test_footer_reports_an_unavailable_channel(self, qapp, tmp_path: Path) -> None:
        panel = _make_panel(tmp_path)
        panel.set_workbench_page(_FakePage([_running_target(None)]))
        assert "利用できません" in panel.status_footer_text()

    def test_footer_does_not_repeat_the_execution_log(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        panel.on_job_log_line("asdw-web#APP-001", "1.2", "ログ本文である")
        assert "ログ本文である" not in panel.status_footer_text()


class TestOverflowMenu:
    def test_secondary_actions_are_grouped(self, qapp, tmp_path: Path) -> None:
        panel = _make_panel(tmp_path)
        assert panel.overflow_menu_labels() == [
            "会話をクリア",
            "会話をコピー",
            "結果を Copilot で開く",
        ]

    def test_clearing_the_transcript_does_not_touch_pending_requests(
        self, qapp, tmp_path: Path
    ) -> None:
        panel, channel = _panel_with_running_job(tmp_path)
        panel.send_job_message("first")
        panel.clear_transcript()
        assert panel.job_log_text() == ""
        assert [r.text for r in list_pending_requests(channel, "1.2")] == ["first"]

    def test_copying_the_transcript_puts_it_on_the_clipboard(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        panel.send_job_message("コピー対象")
        panel.copy_transcript()
        assert "コピー対象" in QApplication.clipboard().text()

    def test_no_stop_action_is_offered_for_the_running_turn(self, qapp, tmp_path: Path) -> None:
        """FR-GUI-18: ジョブ全体停止を「応答の取り消し」として提示しない。"""
        panel = _make_panel(tmp_path)
        labels = panel.overflow_menu_labels()
        assert not any("停止" in label for label in labels)
        assert "stop_orchestrator" not in Path("hve/gui/copilot_chat_panel.py").read_text(
            encoding="utf-8"
        )


class TestTurnNavigation:
    """FR-GUI-18: 送信メッセージのターン位置表示と前後移動。"""

    def test_navigation_is_hidden_without_any_sent_message(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        assert panel._turn_nav_bar.isHidden() is True

    def test_navigation_appears_after_the_first_send(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        panel.send_job_message("最初の指示")
        assert panel._turn_nav_bar.isHidden() is False

    def test_position_shows_the_current_turn_over_the_total(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        panel.send_job_message("一つ目")
        assert panel.turn_position_text() == "1/1"
        panel.send_job_message("二つ目")
        panel.send_job_message("三つ目")
        assert panel.turn_position_text() == "3/3"

    def test_a_new_message_becomes_the_current_turn(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        panel.send_job_message("一つ目")
        panel.send_job_message("二つ目")
        panel.goto_previous_turn()
        panel.send_job_message("三つ目")
        assert panel.turn_position_text() == "3/3"

    def test_moving_to_the_previous_turn_updates_the_position(
        self, qapp, tmp_path: Path
    ) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        for text in ("一つ目", "二つ目", "三つ目"):
            panel.send_job_message(text)
        assert panel.goto_previous_turn() is True
        assert panel.turn_position_text() == "2/3"
        assert panel.turn_label_text() == "二つ目"

    def test_moving_to_the_next_turn_updates_the_position(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        for text in ("一つ目", "二つ目"):
            panel.send_job_message(text)
        panel.goto_previous_turn()
        assert panel.goto_next_turn() is True
        assert panel.turn_position_text() == "2/2"

    def test_previous_is_unavailable_on_the_first_turn(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        panel.send_job_message("一つ目")
        panel.send_job_message("二つ目")
        panel.goto_previous_turn()
        assert panel._turn_prev_btn.isEnabled() is False
        assert panel.goto_previous_turn() is False
        assert panel.turn_position_text() == "1/2"

    def test_next_is_unavailable_on_the_last_turn(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        panel.send_job_message("一つ目")
        panel.send_job_message("二つ目")
        assert panel._turn_next_btn.isEnabled() is False
        assert panel.goto_next_turn() is False
        assert panel.turn_position_text() == "2/2"

    def test_label_shows_only_the_message_body(self, qapp, tmp_path: Path) -> None:
        panel, channel = _panel_with_running_job(tmp_path)
        panel.select_action("いま割り込む")
        panel.send_job_message("本文だけ")
        request_id = list_pending_requests(channel, "1.2")[0].request_id
        write_ack(channel, request_id, "steer", "accepted")
        panel.poll_acks()
        assert panel.turn_label_text() == "本文だけ"

    def test_label_keeps_a_single_line(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        panel.send_job_message("一行目\n二行目\n三行目")
        label = panel.turn_label_text()
        assert "\n" not in label
        assert label.startswith("一行目")
        assert label.endswith("…")

    def test_label_elides_a_long_body(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        panel.send_job_message("あ" * 200)
        label = panel.turn_label_text()
        assert len(label) < 200
        assert label.endswith("…")

    def test_switching_the_target_resets_the_navigation(self, qapp, tmp_path: Path) -> None:
        channel = tmp_path / "ipc"
        channel.mkdir(exist_ok=True)
        panel = _make_panel(tmp_path)
        panel.set_workbench_page(_FakePage([_running_target(channel), _finished_target()]))
        panel.send_job_message("一つ目")
        panel._target_combo.setCurrentIndex(1)
        assert panel._turn_nav_bar.isHidden() is True
        assert panel.turn_position_text() == ""

    def test_clearing_the_transcript_hides_the_navigation(self, qapp, tmp_path: Path) -> None:
        panel, _ = _panel_with_running_job(tmp_path)
        panel.send_job_message("一つ目")
        panel.clear_transcript()
        assert panel._turn_nav_bar.isHidden() is True

    def test_navigation_controls_are_reachable_and_named(self, qapp, tmp_path: Path) -> None:
        from PySide6.QtCore import Qt

        panel, _ = _panel_with_running_job(tmp_path)
        for control in (panel._turn_prev_btn, panel._turn_next_btn):
            assert control.focusPolicy() != Qt.FocusPolicy.NoFocus
            assert control.accessibleName()

    def test_scrolling_the_conversation_updates_the_position(self, qapp, tmp_path: Path) -> None:
        """利用者のスクロールが位置表示へ反映される（配線の検証）。"""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QMainWindow

        panel, _ = _panel_with_running_job(tmp_path)
        # 実運用と同じくドックとして配置しないと、会話ビューへ実ジオメトリが行き渡らない。
        window = QMainWindow()
        window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, panel)
        window.resize(700, 400)
        panel._tabs.setCurrentIndex(1)
        window.show()
        QApplication.processEvents()

        for i in range(3):
            panel.send_job_message(f"指示 {i}")
            for j in range(40):
                panel.on_job_log_line("asdw-web#APP-001", "1.2", f"log {i}-{j}")
        # ログブロックの高さ確定 → スクロール範囲の再計算の順で 2 巡必要。
        QApplication.processEvents()
        QApplication.processEvents()

        bar = panel._transcript.verticalScrollBar()
        assert bar.maximum() > 0, "前提: 会話がスクロール可能な長さであること"
        bar.setValue(bar.maximum())
        assert panel.turn_position_text() == "3/3"
        bar.setValue(0)
        assert panel.turn_position_text() == "1/3"
        window.close()
