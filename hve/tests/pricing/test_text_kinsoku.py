"""Wave 4 GUI: text_kinsoku ヘルパのテスト (Qt 非依存)。"""

from __future__ import annotations

from hve.gui.text_kinsoku import (
    ZWSP,
    apply_cjk_kinsoku,
    format_cost,
    format_elapsed,
    join_items,
    wrap_nowrap_unit,
)


def test_wrap_nowrap_unit_basic() -> None:
    html = wrap_nowrap_unit("Cost", "$0.40", label_color="#000", value_color="#666")
    assert "Cost:" in html
    assert "$0.40" in html
    assert "white-space:nowrap" in html


def test_wrap_nowrap_unit_escapes_html() -> None:
    html = wrap_nowrap_unit("<x>", "&y", label_color="#000", value_color="#000")
    assert "<x>" not in html
    assert "&lt;x&gt;" in html
    assert "&amp;y" in html


def test_join_items_inserts_zwsp_around_separator() -> None:
    parts = ["A", "B", "C"]
    out = join_items(parts)
    assert out.count(ZWSP) >= 4  # 2 セパレータ × ZWSP 前後
    assert "|" in out
    assert out.startswith("A")
    assert out.endswith("C")


def test_apply_cjk_kinsoku_removes_zwsp_before_forbidden_start_char() -> None:
    # ZWSP の直後に「。」 (行頭禁則) が来る場合、ZWSP を削除する
    text = f"abc{ZWSP}。def"
    out = apply_cjk_kinsoku(text)
    assert ZWSP not in out
    assert out == "abc。def"


def test_apply_cjk_kinsoku_keeps_other_zwsp() -> None:
    text = f"abc{ZWSP}def"
    out = apply_cjk_kinsoku(text)
    assert out == text


def test_format_elapsed() -> None:
    assert format_elapsed(0) == "00:00:00"
    assert format_elapsed(59) == "00:00:59"
    assert format_elapsed(60) == "00:01:00"
    assert format_elapsed(3661) == "01:01:01"
    assert format_elapsed(-5) == "00:00:00"
    assert format_elapsed(float("nan")) == "00:00:00"


def test_format_cost_none_returns_dash() -> None:
    assert format_cost(None, None) == "-"


def test_format_cost_usd_only() -> None:
    assert format_cost(0.12, None, currency="usd") == "$0.1200"
    assert format_cost(1.234, None, currency="usd") == "$1.23"


def test_format_cost_jpy_only() -> None:
    assert format_cost(1.0, 150.0, currency="jpy") == "¥150"
    assert format_cost(1.0, 1234.5, currency="jpy") == "¥1,234"  # banker round → 1234


def test_format_cost_both() -> None:
    out = format_cost(0.4, 60.0, currency="both")
    assert "$" in out
    assert "¥60" in out
    assert "(" in out and ")" in out


def test_format_cost_auto_ja_uses_both() -> None:
    out = format_cost(0.4, 60.0, currency="auto", locale="ja")
    assert "¥60" in out and "$" in out


def test_format_cost_auto_en_uses_usd() -> None:
    out = format_cost(0.4, 60.0, currency="auto", locale="en")
    assert "¥" not in out
    assert "$" in out
