"""hve.gui.markdown_preview.code_highlighter のユニットテスト。"""

from __future__ import annotations

from pathlib import Path

from hve.gui.markdown_preview.code_highlighter import (
    CodeHighlighter,
    get_style_css,
)


def test_python_highlight_contains_style_and_highlight_div() -> None:
    h = CodeHighlighter()
    out = h.highlight_file(Path("a.py"), "print('hi')\n")
    assert '<style>' in out
    assert 'class="highlight"' in out


def test_unknown_filename_falls_back_to_plain_pre() -> None:
    h = CodeHighlighter()
    # 拡張子も内容も lexer 推定不能（短い空白）
    out = h.highlight_file(Path("x.unknownXYZ"), "   ")
    # Pygments は短い文字列でも lexer を guess することがあるため、いずれの場合も
    # <pre> 要素は含まれる（plain fallback または highlight 出力）
    assert "<pre" in out


def test_style_css_is_cached() -> None:
    css1 = get_style_css()
    css2 = get_style_css()
    assert css1 is css2  # 同一オブジェクト返却（キャッシュ）


def test_html_escapes_special_chars_in_plain_fallback() -> None:
    h = CodeHighlighter()
    out = h.highlight_file(Path("x.unknownXYZ"), "<script>alert(1)</script>")
    assert "<script>" not in out
    # エスケープされていれば &lt; が含まれる
    assert "&lt;script&gt;" in out or "&lt;/script&gt;" in out
