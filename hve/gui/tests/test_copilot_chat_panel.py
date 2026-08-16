"""FR-GUI-10/12/13/14: Copilot ドックパネルのタブ構成とジョブ連携テスト。

旧実装（送信ごとに `copilot -p` を spawn する使い捨て非対話モード）は FR-GUI-10 で
禁止されたため、当該挙動を固定していたテストは削除し本ファイルへ置き換えた。

QtWebEngine を読み込まないよう、端末ビューと対話セッションは注入可能なファクトリで
差し替える。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget

from hve.gui.copilot_chat_panel import CopilotChatPanel
from hve.gui.copilot_interactive_session import CopilotInteractiveSessionError
from hve.gui.job_interaction_model import JobTarget
from hve.job_interaction_ipc import list_acks, list_pending_requests, write_ack


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _FakeSession:
    """`CopilotInteractiveSession` 互換の最小フェイク。"""

    def __init__(self, *, fail: bool = False) -> None:
        self.starts: List[Optional[str]] = []
        self.stops = 0
        self.repo_roots: List[Path] = []
        self._running = False
        self._fail = fail

    def start(self, *, initial_prompt: Optional[str] = None) -> None:
        if self._fail:
            raise CopilotInteractiveSessionError("copilot が見つかりません。setup-hve を実行してください。")
        self.starts.append(initial_prompt)
        self._running = True

    def stop(self) -> None:
        self.stops += 1
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def set_repo_root(self, repo_root: Path) -> None:
        self.repo_roots.append(Path(repo_root))


class _FakePage:
    """`WorkbenchPage` のジョブ対話 API 部分だけを持つフェイク。"""

    def __init__(self, targets: List[JobTarget], *, work_root: Optional[Path] = None) -> None:
        self._targets = targets
        self._work_root = work_root
        self.snapshots = {"": []}

    def job_targets(self) -> List[JobTarget]:
        return list(self._targets)

    def job_log_snapshot(self, target: JobTarget) -> List[str]:
        return list(self.snapshots.get(target.step_id or "", []))

    def session_work_root(self) -> Optional[Path]:
        return self._work_root

    def session_artifacts(self):
        return []


def _make_panel(qapp, tmp_path: Path, *, session: Optional[_FakeSession] = None) -> CopilotChatPanel:
    session = session or _FakeSession()
    panel = CopilotChatPanel(
        repo_root=tmp_path,
        terminal_factory=lambda: QWidget(),
        session_factory=lambda view, repo_root: session,
    )
    panel._test_session = session  # type: ignore[attr-defined]
    return panel


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


# ---------------------------------------------------------------------------
# FR-GUI-10: 対話 CLI タブ
# ---------------------------------------------------------------------------


def test_panel_has_a_cli_tab_and_a_job_tab(qapp, tmp_path: Path) -> None:
    panel = _make_panel(qapp, tmp_path)
    assert panel.tab_titles() == ["Copilot CLI", "実行ジョブ"]


def test_panel_does_not_spawn_a_one_shot_prompt_process(qapp, tmp_path: Path) -> None:
    """FR-GUI-10: 送信ごとの使い捨て `copilot -p` 経路を持たない。"""
    source = Path("hve/gui/copilot_chat_panel.py").read_text(encoding="utf-8")
    assert "QProcess" not in source
    assert "--allow-all-tools" not in source
    assert "--no-ask-user" not in source


def test_panel_has_no_workflow_resume_api(qapp, tmp_path: Path) -> None:
    """FR-GUI-15: HVE ワークフロー再開 API を復活させない。"""
    panel = _make_panel(qapp, tmp_path)
    assert not hasattr(panel, "resume_workflow")
    source = Path("hve/gui/copilot_chat_panel.py").read_text(encoding="utf-8")
    assert "resume_session" not in source


def test_primary_controls_are_reachable_and_named_for_assistive_tech(
    qapp, tmp_path: Path
) -> None:
    """FR-GUI-10 / FR-GUI-12 / FR-GUI-18: 主要操作がキーボードで到達でき、読み上げ名を持つ。"""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication

    panel = _make_panel(qapp, tmp_path)
    controls = [
        panel._cli_start_btn,
        panel._cli_stop_btn,
        panel._target_combo,
        panel._overflow_btn,
        panel._input_box.action_combo(),
        panel._input_box.attach_button(),
        panel._input_box.text_edit(),
        panel._input_box.send_button(),
    ]
    for control in controls:
        assert control.focusPolicy() != Qt.FocusPolicy.NoFocus
        assert control.accessibleName()

    # 送信は Enter だけで完了できる（ボタンへ移動しなくてよい）。
    channel = tmp_path / "keyboard-ipc"
    channel.mkdir()
    panel.set_workbench_page(_FakePage([_running_target(channel)]))
    panel._input_box.set_text("キーボードだけで送る")
    QApplication.sendEvent(
        panel._input_box.text_edit(),
        QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Return,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    pending = list_pending_requests(channel, "1.2")
    assert [request.text for request in pending] == ["キーボードだけで送る"]


def test_starting_the_cli_session_uses_the_persistent_session(qapp, tmp_path: Path) -> None:
    session = _FakeSession()
    panel = _make_panel(qapp, tmp_path, session=session)
    assert panel.start_cli_session() is True
    assert session.starts == [None]


def test_cli_session_failure_shows_setup_guidance(qapp, tmp_path: Path) -> None:
    """FR-GUI-10: 解決できない場合は使い捨てモードへ退避せず、案内を表示する。"""
    session = _FakeSession(fail=True)
    panel = _make_panel(qapp, tmp_path, session=session)
    assert panel.start_cli_session() is False
    assert "setup-hve" in panel.cli_status_text()


def test_set_repo_root_propagates_to_the_session(qapp, tmp_path: Path) -> None:
    session = _FakeSession()
    panel = _make_panel(qapp, tmp_path, session=session)
    panel.start_cli_session()
    other = tmp_path / "other"
    other.mkdir()
    panel.set_repo_root(other)
    assert session.repo_roots[-1] == other


def test_shutdown_stops_the_session(qapp, tmp_path: Path) -> None:
    session = _FakeSession()
    panel = _make_panel(qapp, tmp_path, session=session)
    panel.start_cli_session()
    panel.shutdown()
    assert session.stops == 1


# ---------------------------------------------------------------------------
# FR-GUI-13: ジョブ宛先とログ
# ---------------------------------------------------------------------------


def test_job_targets_are_listed_from_the_workbench_page(qapp, tmp_path: Path) -> None:
    channel = tmp_path / "ipc"
    channel.mkdir()
    panel = _make_panel(qapp, tmp_path)
    panel.set_workbench_page(_FakePage([_running_target(channel), _finished_target()]))
    assert panel.target_labels() == [
        "ASDW-WEB (APP-001) / 1.2 Data Implementation",
        "AAD-WEB (APP-001)",
    ]


def test_selecting_a_target_loads_its_log_snapshot(qapp, tmp_path: Path) -> None:
    channel = tmp_path / "ipc"
    channel.mkdir()
    page = _FakePage([_running_target(channel)])
    page.snapshots["1.2"] = ["line-a", "line-b"]
    panel = _make_panel(qapp, tmp_path)
    panel.set_workbench_page(page)
    assert panel.job_log_text().splitlines() == ["line-a", "line-b"]


def test_incremental_log_is_appended_only_for_the_selected_target(
    qapp, tmp_path: Path
) -> None:
    channel = tmp_path / "ipc"
    channel.mkdir()
    panel = _make_panel(qapp, tmp_path)
    panel.set_workbench_page(_FakePage([_running_target(channel)]))
    panel.on_job_log_line("asdw-web#APP-001", "1.2", "mine")
    panel.on_job_log_line("asdw-web#APP-001", "9.9", "other-step")
    panel.on_job_log_line("other#APP-002", "1.2", "other-instance")
    assert panel.job_log_text().splitlines() == ["mine"]


# ---------------------------------------------------------------------------
# FR-GUI-12: 送信アクション
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,expected_action",
    [
        ("キューに追加", "queue"),
        ("いま割り込む", "steer"),
        ("中断して送信", "stop_and_send"),
    ],
)
def test_send_writes_the_selected_action(
    qapp, tmp_path: Path, label: str, expected_action: str
) -> None:
    channel = tmp_path / "ipc"
    channel.mkdir()
    panel = _make_panel(qapp, tmp_path)
    panel.set_workbench_page(_FakePage([_running_target(channel)]))
    panel.select_action(label)
    assert panel.send_job_message("進捗を教えて") is True

    pending = list_pending_requests(channel, "1.2")
    assert len(pending) == 1
    assert pending[0].action == expected_action
    assert pending[0].text == "進捗を教えて"


def test_send_is_rejected_for_a_finished_job(qapp, tmp_path: Path) -> None:
    panel = _make_panel(qapp, tmp_path)
    panel.set_workbench_page(_FakePage([_finished_target()]))
    assert panel.send_job_message("hello") is False
    assert "送信できません" in panel.job_log_text()


def test_send_is_rejected_without_a_registered_channel(qapp, tmp_path: Path) -> None:
    panel = _make_panel(qapp, tmp_path)
    panel.set_workbench_page(_FakePage([_running_target(None)]))
    assert panel.send_job_message("hello") is False


def test_oversized_input_is_rejected(qapp, tmp_path: Path) -> None:
    channel = tmp_path / "ipc"
    channel.mkdir()
    panel = _make_panel(qapp, tmp_path)
    panel.set_workbench_page(_FakePage([_running_target(channel)]))
    assert panel.send_job_message("あ" * 9000) is False
    assert list_pending_requests(channel, "1.2") == []


def test_ack_is_surfaced_to_the_operator(qapp, tmp_path: Path) -> None:
    """FR-GUI-12: 受理/失敗の状態を利用者が確認できる。"""
    channel = tmp_path / "ipc"
    channel.mkdir()
    panel = _make_panel(qapp, tmp_path)
    panel.set_workbench_page(_FakePage([_running_target(channel)]))
    panel.send_job_message("hello")
    request_id = list_pending_requests(channel, "1.2")[0].request_id
    write_ack(channel, request_id, "steer", "failed", detail="RuntimeError")

    panel.poll_acks()
    text = panel.job_log_text()
    assert "failed" in text
    # ACK 表示にプロンプト本文を再掲しない（ACK ファイル自体にも含まれない）。
    assert "hello" not in json.dumps(list_acks(channel), ensure_ascii=False)


# ---------------------------------------------------------------------------
# FR-GUI-14: 実行後の結果参照
# ---------------------------------------------------------------------------


def test_open_result_starts_a_new_session_with_path_context(qapp, tmp_path: Path) -> None:
    work_root = tmp_path / "run" / "20260813T000000-abcdef"
    work_root.mkdir(parents=True)
    (work_root / "console-log.txt").write_text("log", encoding="utf-8")

    session = _FakeSession()
    panel = _make_panel(qapp, tmp_path, session=session)
    panel.set_workbench_page(_FakePage([_finished_target()], work_root=work_root))

    assert panel.open_selected_job_result() is True
    prompt = session.starts[-1]
    assert "20260813T000000-abcdef" in prompt
    assert str(work_root / "console-log.txt") in prompt
    assert "終了コード: 1" in prompt
    assert "log" not in prompt.replace("console-log.txt", "")


def test_open_result_without_a_work_root_is_reported(qapp, tmp_path: Path) -> None:
    session = _FakeSession()
    panel = _make_panel(qapp, tmp_path, session=session)
    panel.set_workbench_page(_FakePage([_finished_target()], work_root=None))
    assert panel.open_selected_job_result() is False
    assert session.starts == []


def test_open_result_does_not_kill_a_running_session_without_consent(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    work_root = tmp_path / "run" / "20260813T000000-abcdef"
    work_root.mkdir(parents=True)

    session = _FakeSession()
    panel = _make_panel(qapp, tmp_path, session=session)
    panel.start_cli_session()
    panel.set_workbench_page(_FakePage([_finished_target()], work_root=work_root))

    monkeypatch.setattr(panel, "_confirm_session_restart", lambda: False)
    assert panel.open_selected_job_result() is False
    assert session.stops == 0
    assert session.starts == [None]

    monkeypatch.setattr(panel, "_confirm_session_restart", lambda: True)
    assert panel.open_selected_job_result() is True
    assert session.stops == 1
    assert len(session.starts) == 2
