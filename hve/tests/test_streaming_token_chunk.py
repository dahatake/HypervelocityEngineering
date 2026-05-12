"""ADR-0002 T3C: Streaming イベントから stderr JSON への転送テスト。

実 Copilot SDK 接続は不要。``_handle_session_event`` にダミーイベントを流し、
``console.token_chunk()`` 経由で stderr に JSON が出力されることを確認する。
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from hve.runner import StepRunner
from hve.config import SDKConfig
from hve.console import Console


def _make_event(type_value: str, *, delta_content: str = "") -> SimpleNamespace:
    """SessionEvent モック。runner._handle_session_event は ``event.type.value`` と
    ``event.data`` を参照する。``_get`` は ``getattr`` で属性アクセスするため
    ``data`` も SimpleNamespace で渡す必要がある。
    """
    return SimpleNamespace(
        type=SimpleNamespace(value=type_value),
        data=SimpleNamespace(delta_content=delta_content),
    )


def test_streaming_delta_emits_token_chunk_to_stderr(capfd):
    config = SDKConfig(model="Auto", run_id="test-streaming")
    # ADR-0002 改訂 (2026-05-12): token_chunk は verbosity>=3 のみ出力
    console = Console(verbosity=3)
    console.set_run_id("test-streaming")
    runner = StepRunner(config=config, console=console)
    runner._current_step_id = "1/D01"

    runner._handle_session_event(_make_event("assistant.message_delta", delta_content="Hello"))
    runner._handle_session_event(_make_event("assistant.message_delta", delta_content=" world"))

    err_lines = capfd.readouterr().err.splitlines()
    token_chunks = [
        json.loads(l) for l in err_lines
        if l.startswith("{") and '"event": "token_chunk"' in l
    ]
    # 2 件の message delta が記録される
    assert len(token_chunks) == 2
    for tc in token_chunks:
        assert tc["step_id"] == "1/D01"
        assert tc["kind"] == "message"
        assert tc["fanout_key"] == "D01"
        assert tc["parent_step_id"] == "1"
    assert token_chunks[0]["length"] == len("Hello")
    assert token_chunks[1]["length"] == len(" world")


def test_reasoning_delta_emits_token_chunk_with_kind_reasoning(capfd):
    config = SDKConfig(model="Auto", run_id="test-reasoning")
    # ADR-0002 改訂 (2026-05-12): token_chunk は verbosity>=3 のみ出力
    console = Console(verbosity=3)
    console.set_run_id("test-reasoning")
    runner = StepRunner(config=config, console=console)
    runner._current_step_id = "2"

    runner._handle_session_event(_make_event("assistant.reasoning_delta", delta_content="thinking..."))

    err_lines = capfd.readouterr().err.splitlines()
    token_chunks = [
        json.loads(l) for l in err_lines
        if l.startswith("{") and '"event": "token_chunk"' in l
    ]
    assert len(token_chunks) == 1
    assert token_chunks[0]["kind"] == "reasoning"
    assert token_chunks[0]["step_id"] == "2"
    # fanout_key 無しの step_id では parent_step_id / fanout_key は含まれない
    assert "fanout_key" not in token_chunks[0]


def test_empty_delta_does_not_emit_token_chunk(capfd):
    """空のトークンは出力されない。"""
    config = SDKConfig(model="Auto", run_id="test-empty")
    # ADR-0002 改訂 (2026-05-12): token_chunk は verbosity>=3 のみ出力
    console = Console(verbosity=3)
    runner = StepRunner(config=config, console=console)
    runner._current_step_id = "1/D02"

    runner._handle_session_event(_make_event("assistant.message_delta", delta_content=""))

    err_lines = capfd.readouterr().err.splitlines()
    token_chunks = [
        l for l in err_lines
        if l.startswith("{") and '"event": "token_chunk"' in l
    ]
    assert len(token_chunks) == 0


# ----------------------------------------------------------------------
# ADR-0002 改訂 (2026-05-12): token_chunk は verbosity>=3 (verbose) 限定
# ----------------------------------------------------------------------


@pytest.mark.parametrize("verbosity", [0, 1, 2])
def test_token_chunk_not_emitted_below_verbose(capfd, verbosity):
    """verbosity が 3 未満では token_chunk は stderr に出力されない。

    デフォルト (verbosity=1 compact) を含め、verbose 未満では抑止される。
    """
    config = SDKConfig(model="Auto", run_id=f"test-v{verbosity}")
    console = Console(verbosity=verbosity)
    console.set_run_id(f"test-v{verbosity}")
    runner = StepRunner(config=config, console=console)
    runner._current_step_id = "1/D03"

    runner._handle_session_event(_make_event("assistant.message_delta", delta_content="Hello"))
    runner._handle_session_event(_make_event("assistant.reasoning_delta", delta_content="thinking"))

    err_lines = capfd.readouterr().err.splitlines()
    token_chunks = [
        l for l in err_lines
        if l.startswith("{") and '"event": "token_chunk"' in l
    ]
    assert token_chunks == [], (
        f"verbosity={verbosity} では token_chunk は出力されないはず: {token_chunks}"
    )


def test_token_chunk_suppressed_in_final_only_even_when_verbose(capfd):
    """final_only=True では verbosity に関わらず token_chunk は抑止される。"""
    config = SDKConfig(model="Auto", run_id="test-final-only")
    console = Console(verbosity=3, final_only=True)
    console.set_run_id("test-final-only")
    runner = StepRunner(config=config, console=console)
    runner._current_step_id = "1/D04"

    runner._handle_session_event(_make_event("assistant.message_delta", delta_content="Hello"))

    err_lines = capfd.readouterr().err.splitlines()
    token_chunks = [
        l for l in err_lines
        if l.startswith("{") and '"event": "token_chunk"' in l
    ]
    assert token_chunks == []
