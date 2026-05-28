"""test_console_emit_step_context.py — Console の ContextVar 連携テスト。

並列 fanout で複数 child が同一 Console インスタンスを共有する場合に、
各 child の出力行に正しい step_id インラインマーカーが付与されることを検証する。
"""

from __future__ import annotations

import asyncio

import pytest

from hve.console import Console, _CURRENT_EMIT_STEP_ID, INLINE_CTX_PATTERN


class _RecordingWB:
    """append_body 行を全て記録する Workbench モック。"""

    def __init__(self) -> None:
        self.body_lines: list[str] = []

    def append_body(self, line: str) -> None:
        self.body_lines.append(line)

    def set_step_status(self, *_a, **_kw) -> None:  # noqa: D401
        pass

    def set_context(self, *_a, **_kw) -> None:  # noqa: D401
        pass


def _console() -> Console:
    return Console(verbosity=2, no_color=True, timestamp_style="off")


@pytest.fixture(autouse=True)
def _reset_ctx_step_id():
    token = _CURRENT_EMIT_STEP_ID.set(None)
    yield
    _CURRENT_EMIT_STEP_ID.reset(token)


def test_emit_without_context_has_no_inline_marker() -> None:
    """ContextVar 未設定時は行頭にマーカーが付かない。"""
    c = _console()
    wb = _RecordingWB()
    c.attach_workbench(wb)
    c._emit("hello")
    assert wb.body_lines == ["hello"]


def test_emit_with_context_adds_inline_marker() -> None:
    """ContextVar 設定時は行頭に ``[hve:ctx:<id>] `` が付く。"""
    c = _console()
    wb = _RecordingWB()
    c.attach_workbench(wb)
    _CURRENT_EMIT_STEP_ID.set("4.2/UC-03")
    c._emit("phase 1/1")
    assert wb.body_lines == ["[hve:ctx:4.2/UC-03] phase 1/1"]


def test_emit_skips_marker_for_stats_lines() -> None:
    """`[hve:stats]` 行にはマーカーを重ねない（GUI 受信側の互換性確保）。"""
    c = _console()
    wb = _RecordingWB()
    c.attach_workbench(wb)
    _CURRENT_EMIT_STEP_ID.set("step-1")
    c._emit('[hve:stats] {"kind":"step_status","step":"step-1"}', ts=False)
    assert wb.body_lines == ['[hve:stats] {"kind":"step_status","step":"step-1"}']


def test_cli_stdout_strips_marker(capsys) -> None:
    """CLI 単体（Workbench 未接続）時、stdout 出力にマーカーは含まれない（Q4=x）。"""
    c = _console()
    _CURRENT_EMIT_STEP_ID.set("step-1")
    c._emit("visible-line")
    captured = capsys.readouterr()
    assert "visible-line" in captured.out
    assert "[hve:ctx:" not in captured.out


def test_inline_ctx_pattern_matches_marker_format() -> None:
    """公開正規表現 `INLINE_CTX_PATTERN` が想定フォーマットに一致する。"""
    m = INLINE_CTX_PATTERN.match("[hve:ctx:4.2/UC-29] [11:18:10] body")
    assert m is not None
    assert m.group(1) == "4.2/UC-29"


def test_parallel_asyncio_tasks_each_get_own_context() -> None:
    """並列 asyncio タスクが各々独立した ContextVar を持つこと（取り違え防止）。

    `asyncio.create_task` は親 context をコピーするため、各タスク内での
    `_CURRENT_EMIT_STEP_ID.set()` は他タスクへ漏れない。これが並列 fanout の
    本文行（Phase 1/1: メインタスク等）が正しい child に帰属する根拠。
    """
    c = _console()
    wb = _RecordingWB()
    c.attach_workbench(wb)

    async def child(step_id: str, n: int) -> None:
        _CURRENT_EMIT_STEP_ID.set(step_id)
        for i in range(n):
            await asyncio.sleep(0)  # yield to other tasks
            c._emit(f"line-{step_id}-{i}")

    async def main() -> None:
        await asyncio.gather(
            child("UC-03", 3),
            child("UC-29", 3),
            child("UC-09", 3),
        )

    asyncio.run(main())

    # 各 step_id について 3 行ずつ存在し、行頭の step_id と本文の step_id が一致する。
    by_step: dict[str, list[str]] = {}
    for line in wb.body_lines:
        m = INLINE_CTX_PATTERN.match(line)
        assert m is not None, f"missing inline marker: {line!r}"
        sid = m.group(1)
        body = line[m.end():]
        # 本文 ``line-<sid>-<i>`` と行頭 marker が一致する
        assert f"line-{sid}-" in body, (
            f"step_id mismatch: marker={sid} body={body!r}"
        )
        by_step.setdefault(sid, []).append(body)
    assert sorted(by_step.keys()) == ["UC-03", "UC-09", "UC-29"]
    for sid, lines in by_step.items():
        assert len(lines) == 3, f"{sid}: got {len(lines)} lines"
