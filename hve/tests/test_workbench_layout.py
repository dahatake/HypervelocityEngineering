"""test_workbench_layout.py — Layout 構造とサイズ計算のテスト。"""

from __future__ import annotations

from hve.workbench.layout import (
    HEADER2_MAX_LINES,
    make_layout,
    render_body,
    render_footer,
    render_header1,
    render_header2,
    update_layout,
)
from hve.workbench.state import StepView, WorkbenchState


def _state(body_window: int = 12) -> WorkbenchState:
    return WorkbenchState(
        workflow_id="aad",
        run_id="r1",
        model="claude-opus-4.7",
        steps=[
            StepView(id="1", title="DataModel", status="done"),
            StepView(id="2", title="Catalog", status="running"),
            StepView(id="3", title="ServiceSpec", status="pending"),
        ],
        body_window=body_window,
    )


def test_layout_has_four_panes() -> None:
    # 狭端末フォールバックを強制して従来 4 ペインを検証
    layout4 = make_layout(body_window=12, console_height=10)
    names = {child.name for child in layout4.children}
    assert names == {"header1", "header2", "body", "footer"}


def test_layout_has_six_panes_when_tall_enough() -> None:
    """高さ十分な端末では tasktree / useractions / userinteraction を含む 7 ペイン。"""
    layout = make_layout(body_window=12, console_height=200)
    names = {child.name for child in layout.children}
    assert names == {"header1", "header2", "body", "tasktree", "useractions", "userinteraction", "footer"}


def test_layout_body_size_includes_panel_border() -> None:
    layout = make_layout(body_window=12)
    body = layout["body"]
    # body_window + 2（Panel 枠 上下）
    assert body.size == 14


def test_layout_body_size_for_min_window() -> None:
    layout = make_layout(body_window=10)
    assert layout["body"].size == 12


def test_layout_body_size_for_max_window() -> None:
    layout = make_layout(body_window=15)
    assert layout["body"].size == 17


def test_header2_size_constant() -> None:
    layout = make_layout(body_window=12)
    assert layout["header2"].size == HEADER2_MAX_LINES


def test_render_header1_contains_workflow_and_run() -> None:
    s = _state()
    t = render_header1(s)
    assert "HVE CLI Orchestrator" in t.plain
    assert "aad" in t.plain
    assert "r1" in t.plain


def test_render_header1_shows_workflow_name_with_id() -> None:
    """workflow_name が設定されていれば `<name> (<id>)` で表示される。"""
    s = WorkbenchState(
        workflow_id="aad",
        workflow_name="Architecture Design",
        run_id="r1",
        model="claude-opus-4.7",
    )
    plain = render_header1(s).plain
    assert "Architecture Design" in plain
    assert "(aad)" in plain


def test_render_header1_falls_back_to_id_when_name_empty() -> None:
    s = WorkbenchState(workflow_id="aad", workflow_name="", run_id="r1", model="m")
    plain = render_header1(s).plain
    assert "aad" in plain
    assert "(aad)" not in plain


def test_render_footer_shows_model_and_context() -> None:
    s = _state()
    s.set_context(100, 1000, 5)
    t = render_footer(s)
    plain = t.plain
    assert "claude-opus-4.7" in plain
    assert "100" in plain
    assert "1,000" in plain or "1000" in plain
    assert "10%" in plain


def test_render_footer_no_context_shows_dashes() -> None:
    s = _state()
    t = render_footer(s)
    assert "-/-" in t.plain


def test_render_body_pads_short_buffer() -> None:
    s = _state(body_window=10)
    s.append_body("hello")
    panel = render_body(s)
    # Panel.renderable は Text、改行で 10 行になる
    text = panel.renderable
    lines = text.plain.split("\n")
    assert len(lines) == 10
    assert lines[0] == "hello"


def test_render_header2_renders_without_error() -> None:
    s = _state()
    g = render_header2(s)
    # 例外が出ず Group が返ること
    assert g is not None


def test_update_layout_does_not_raise() -> None:
    s = _state()
    layout = make_layout(body_window=12)
    update_layout(layout, s)  # 例外が出なければ OK


def test_update_layout_with_fanout_summary() -> None:
    s = _state()
    s.expand_steps("3", [f"k{i}" for i in range(21)])
    layout = make_layout(body_window=12)
    update_layout(layout, s)
