"""ChainState 状態機械テスト（Qt 非依存）。"""

from __future__ import annotations

import pytest

from hve.gui.autopilot.chain_runner import (
    ChainEvent,
    ChainState,
    ChainSummary,
    summarize,
)


def test_chain_state_requires_non_empty() -> None:
    with pytest.raises(ValueError):
        ChainState(chain=[])


def test_chain_state_initial_current() -> None:
    s = ChainState(chain=["aad-web", "asdw-web"])
    assert s.current() == "aad-web"
    assert not s.is_terminal()


def test_chain_state_advances_on_success() -> None:
    s = ChainState(chain=["aad-web", "asdw-web"])
    assert s.on_stage_finished(0) == ChainEvent.ADVANCED
    assert s.current() == "asdw-web"
    assert s.index == 1


def test_chain_state_completes_on_final_success() -> None:
    s = ChainState(chain=["aad-web", "asdw-web"])
    assert s.on_stage_finished(0) == ChainEvent.ADVANCED
    assert s.on_stage_finished(0) == ChainEvent.COMPLETED
    assert s.completed is True
    assert s.current() is None
    assert s.is_terminal()


def test_chain_state_aborts_on_nonzero() -> None:
    s = ChainState(chain=["aad-web", "asdw-web"])
    assert s.on_stage_finished(2) == ChainEvent.ABORTED
    assert s.aborted_code == 2
    assert s.current() is None
    assert s.is_terminal()


def test_chain_state_abort_at_second_stage() -> None:
    s = ChainState(chain=["adfd", "adfdv"])
    assert s.on_stage_finished(0) == ChainEvent.ADVANCED
    assert s.on_stage_finished(1) == ChainEvent.ABORTED
    summary = summarize(s)
    assert summary == ChainSummary(
        chain=["adfd", "adfdv"], completed=False,
        aborted_at="adfdv", aborted_code=1,
    )


def test_chain_state_repeated_call_after_terminal_is_idempotent() -> None:
    s = ChainState(chain=["aad-web"])
    assert s.on_stage_finished(0) == ChainEvent.COMPLETED
    assert s.on_stage_finished(0) == ChainEvent.COMPLETED
    assert s.completed is True


def test_chain_state_summary_for_success() -> None:
    s = ChainState(chain=["aad-web", "asdw-web"])
    s.on_stage_finished(0)
    s.on_stage_finished(0)
    assert summarize(s) == ChainSummary(
        chain=["aad-web", "asdw-web"], completed=True,
        aborted_at=None, aborted_code=None,
    )
