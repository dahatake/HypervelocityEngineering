"""test_workbench_buffer.py — RingBuffer の単体テスト。"""

from __future__ import annotations

import pytest

from hve.workbench.buffer import RingBuffer


def test_append_and_len() -> None:
    rb = RingBuffer(capacity=5)
    assert len(rb) == 0
    rb.append("a")
    rb.append("b")
    assert len(rb) == 2


def test_overflow_drops_oldest() -> None:
    rb = RingBuffer(capacity=3)
    for c in ["a", "b", "c", "d"]:
        rb.append(c)
    assert len(rb) == 3
    assert rb.view(window=3, offset=0) == ["b", "c", "d"]


def test_view_tail_follow() -> None:
    rb = RingBuffer(capacity=10)
    for i in range(5):
        rb.append(str(i))
    assert rb.view(window=3, offset=0) == ["2", "3", "4"]


def test_view_with_offset() -> None:
    rb = RingBuffer(capacity=10)
    for i in range(5):
        rb.append(str(i))
    # offset=2: 末尾から 2 戻る → end=3 → window=3 → start=0
    assert rb.view(window=3, offset=2) == ["0", "1", "2"]


def test_view_pads_when_short() -> None:
    rb = RingBuffer(capacity=10)
    rb.append("x")
    out = rb.view(window=4, offset=0)
    assert out == ["x", "", "", ""]
    assert len(out) == 4


def test_view_empty_buffer() -> None:
    rb = RingBuffer(capacity=5)
    assert rb.view(window=3, offset=0) == ["", "", ""]


def test_view_window_zero() -> None:
    rb = RingBuffer(capacity=5)
    rb.append("a")
    assert rb.view(window=0, offset=0) == []


def test_max_offset() -> None:
    rb = RingBuffer(capacity=10)
    for i in range(7):
        rb.append(str(i))
    # 7 行、window=3 → 4 行スクロール可能
    assert rb.max_offset(window=3) == 4
    assert rb.max_offset(window=10) == 0


def test_append_multiline_splits() -> None:
    rb = RingBuffer(capacity=10)
    rb.append("a\nb\nc")
    assert len(rb) == 3
    assert rb.view(window=3, offset=0) == ["a", "b", "c"]


def test_invalid_capacity() -> None:
    with pytest.raises(ValueError):
        RingBuffer(capacity=0)


def test_invalid_view_args() -> None:
    rb = RingBuffer(capacity=5)
    with pytest.raises(ValueError):
        rb.view(window=-1, offset=0)
    with pytest.raises(ValueError):
        rb.view(window=3, offset=-1)


def test_clear() -> None:
    rb = RingBuffer(capacity=5)
    rb.append("a")
    rb.clear()
    assert len(rb) == 0
