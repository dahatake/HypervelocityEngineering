"""hve.gui.tests.test_copilot_chat_panel_steering

``CopilotChatPanel`` の Steering（実行中ワークフローへの割り込み送信）機能の回帰テスト。

T14（T13: hve/gui/copilot_chat_panel.py — Steering トグル・送信ロジック追加 に対応するテスト）。

実 ``copilot`` CLI プロセスは一切起動しない。``write_steering_request`` は
``unittest.mock.patch`` でモック化して呼び出し引数のみ検証する。
"""

from __future__ import annotations

import os
import unittest.mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.copilot_chat_panel import CopilotChatPanel  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def panel(qapp, tmp_path):
    p = CopilotChatPanel(repo_root=tmp_path)
    yield p
    p.shutdown()


class _FakeWorkbenchPage:
    """``resolve_active_main_step_id`` / ``active_steering_ipc_dir`` のみ実装する
    duck-typed フェイク。
    """

    def __init__(self, *, step_id: str | None, ipc_dir: str | None) -> None:
        self._step_id = step_id
        self._ipc_dir = ipc_dir

    def resolve_active_main_step_id(self) -> str | None:
        return self._step_id

    def active_steering_ipc_dir(self) -> str | None:
        return self._ipc_dir


def test_checkbox_disabled_by_default(panel: CopilotChatPanel) -> None:
    """WorkbenchPage 未設定時はチェックボックスが無効。"""
    assert panel._steering_checkbox.isEnabled() is False
    assert panel._steering_checkbox.isChecked() is False


def test_checkbox_enabled_when_step_and_dir_available(panel: CopilotChatPanel, tmp_path) -> None:
    """step_id と ipc_dir が両方揃っている場合のみ有効化される。"""
    panel.set_workbench_page(
        _FakeWorkbenchPage(step_id="1.1", ipc_dir=str(tmp_path))
    )
    assert panel._steering_checkbox.isEnabled() is True


def test_checkbox_disabled_when_step_id_missing(panel: CopilotChatPanel, tmp_path) -> None:
    """step_id が None（並列実行中 or 未実行）の場合は無効のまま。"""
    panel.set_workbench_page(_FakeWorkbenchPage(step_id=None, ipc_dir=str(tmp_path)))
    assert panel._steering_checkbox.isEnabled() is False


def test_checkbox_disabled_when_ipc_dir_missing(panel: CopilotChatPanel) -> None:
    """ipc_dir が None（生成失敗等）の場合は無効のまま。"""
    panel.set_workbench_page(_FakeWorkbenchPage(step_id="1.1", ipc_dir=None))
    assert panel._steering_checkbox.isEnabled() is False


def test_send_with_steering_checked_writes_ipc_and_skips_qprocess(
    panel: CopilotChatPanel, tmp_path
) -> None:
    """トグル ON での送信は write_steering_request のみ呼ばれ、QProcess は起動しない。"""
    panel.set_workbench_page(
        _FakeWorkbenchPage(step_id="1.1", ipc_dir=str(tmp_path))
    )
    panel._steering_checkbox.setChecked(True)
    panel._input.setText("Actually, stop using Synapse.")

    with unittest.mock.patch(
        "hve.gui.copilot_chat_panel.write_steering_request"
    ) as mock_write:
        panel._on_send()

    mock_write.assert_called_once()
    call_args = mock_write.call_args
    assert str(call_args.args[0]) == str(tmp_path)
    assert call_args.args[1] == "1.1"
    assert call_args.args[2] == "Actually, stop using Synapse."
    # QProcess 経路には入らない（使い捨てプロセスが起動されていない）。
    assert panel._process is None


def test_send_with_steering_unchecked_uses_existing_path(
    panel: CopilotChatPanel, tmp_path
) -> None:
    """トグル OFF（既定）の送信は copilot バイナリ不在時、既存の
    「copilot CLI が利用できません」メッセージ経路のまま（Steering 経路には入らない）。
    """
    panel._copilot_path = None  # copilot バイナリ未検出を模擬
    panel.set_workbench_page(
        _FakeWorkbenchPage(step_id="1.1", ipc_dir=str(tmp_path))
    )
    # available だがチェックはしない（既定 OFF）
    assert panel._steering_checkbox.isChecked() is False
    panel._input.setText("hello")

    with unittest.mock.patch(
        "hve.gui.copilot_chat_panel.write_steering_request"
    ) as mock_write:
        panel._on_send()

    mock_write.assert_not_called()
    assert "copilot CLI が利用できません" in panel._history.toPlainText()
