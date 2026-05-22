"""hve.gui.markdown_preview.markdown_html_renderer のユニットテスト。"""

from __future__ import annotations

from hve.gui.markdown_preview.markdown_html_renderer import MarkdownHtmlRenderer


def test_basic_markdown_renders_to_html() -> None:
    r = MarkdownHtmlRenderer()
    body = r.render_body("# Hello\n\nThis is **bold**.")
    assert "<h1>Hello</h1>" in body
    assert "<strong>bold</strong>" in body


def test_mermaid_fence_becomes_div() -> None:
    """```mermaid ... ``` が <div class="mermaid"> に変換される（敵対的レビュー #4）。"""
    r = MarkdownHtmlRenderer()
    src = "```mermaid\ngraph TD; A-->B\n```\n"
    body = r.render_body(src)
    assert '<div class="mermaid">' in body
    # Mermaid 本文は HTML エスケープされる
    assert "graph TD; A--&gt;B" in body
    # <pre><code class="language-mermaid"> 形式に戻っていないこと
    assert 'language-mermaid' not in body


def test_python_fence_uses_pygments_highlight() -> None:
    """言語指定 fence は Pygments でハイライトされる。"""
    r = MarkdownHtmlRenderer()
    body = r.render_body("```python\nprint('hi')\n```\n")
    assert 'class="highlight"' in body


def test_inline_math_is_preserved_for_katex() -> None:
    """インライン数式 $a^2$ は raw のまま保持される（KaTeX auto-render が DOM 処理）。"""
    r = MarkdownHtmlRenderer()
    body = r.render_body("inline $a^2$ formula\n")
    assert "$a^2$" in body


def test_block_math_is_preserved_for_katex() -> None:
    r = MarkdownHtmlRenderer()
    body = r.render_body("text\n\n$$x = 1$$\n")
    assert "$$x = 1$$" in body


def test_render_full_embeds_into_template() -> None:
    """render_full() の出力は preview.html テンプレートに埋込済。"""
    r = MarkdownHtmlRenderer()
    out = r.render_full("# T")
    assert "<!DOCTYPE html>" in out
    assert "<h1>T</h1>" in out
    # Mermaid / KaTeX 読込スクリプトがテンプレートに含まれる
    assert "mermaid.min.js" in out
    assert "katex.min.js" in out
    # Pygments スタイルが injected されている
    assert "<style>" in out


def test_wrap_html_in_template_works_for_arbitrary_html() -> None:
    r = MarkdownHtmlRenderer()
    out = r.wrap_html_in_template("<p>arbitrary</p>")
    assert "<p>arbitrary</p>" in out
    assert "<!DOCTYPE html>" in out


def test_unknown_lang_fence_falls_back_to_pre() -> None:
    r = MarkdownHtmlRenderer()
    body = r.render_body("```\nplain text\n```\n")
    assert "<pre>" in body
    assert "<code" in body
