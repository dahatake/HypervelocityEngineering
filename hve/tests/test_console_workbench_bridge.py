"""test_console_workbench_bridge.py — Console から WorkbenchController への橋渡しテスト。"""

from __future__ import annotations

from hve.console import Console


class _MockWB:
    """WorkbenchController のモック。呼ばれた API を記録する。"""

    def __init__(self) -> None:
        self.body_lines: list[str] = []
        self.statuses: list[tuple[str, str]] = []
        self.contexts: list[tuple[int, int, int]] = []

    def append_body(self, line: str) -> None:
        self.body_lines.append(line)

    def set_step_status(self, step_id: str, status: str) -> None:
        self.statuses.append((step_id, status))

    def set_context(self, current: int, limit: int, msgs: int) -> None:
        self.contexts.append((current, limit, msgs))


def _console() -> Console:
    # final_only=False, verbosity=2 で確定行が _emit を通る
    return Console(verbosity=2, no_color=True, timestamp_style="off")


def test_emit_routes_to_workbench(capsys) -> None:
    c = _console()
    wb = _MockWB()
    c.attach_workbench(wb)
    c._emit("hello")
    # Workbench に渡る
    assert wb.body_lines == ["hello"]
    # stdout には書かれない
    captured = capsys.readouterr()
    assert "hello" not in captured.out


def test_emit_back_to_stdout_after_detach(capsys) -> None:
    c = _console()
    wb = _MockWB()
    c.attach_workbench(wb)
    c.detach_workbench()
    c._emit("after detach")
    captured = capsys.readouterr()
    assert "after detach" in captured.out


def test_step_start_updates_workbench_running() -> None:
    c = _console()
    wb = _MockWB()
    c.attach_workbench(wb)
    c.step_start("3", "ServiceSpec")
    assert ("3", "running") in wb.statuses
    assert c._current_step_id == "3"


def test_step_end_maps_status() -> None:
    c = _console()
    wb = _MockWB()
    c.attach_workbench(wb)
    c.step_start("3", "ServiceSpec")
    c.step_end("3", "success", elapsed=1.2)
    assert ("3", "done") in wb.statuses
    assert c._current_step_id is None

    c.step_start("4", "X")
    c.step_end("4", "failed", elapsed=0.5)
    assert ("4", "failed") in wb.statuses


def test_context_usage_updates_workbench() -> None:
    c = _console()
    wb = _MockWB()
    c.attach_workbench(wb)
    c.context_usage("3", current_tokens=100, token_limit=1000, msgs=4)
    assert (100, 1000, 4) in wb.contexts


def test_spinner_start_noop_when_workbench_attached() -> None:
    c = _console()
    wb = _MockWB()
    c.attach_workbench(wb)
    # _is_tty を強制 True
    c._is_tty = True
    c.spinner_start("loading")
    # スピナースレッドは起動しない
    assert c._spinner_thread is None


def test_workbench_exception_does_not_block_emit(capsys) -> None:
    c = _console()

    class _Boom:
        def append_body(self, line):
            raise RuntimeError("boom")

    c.attach_workbench(_Boom())
    c._emit("recovered")
    captured = capsys.readouterr()
    # フォールバックで stdout に出力される
    assert "recovered" in captured.out
