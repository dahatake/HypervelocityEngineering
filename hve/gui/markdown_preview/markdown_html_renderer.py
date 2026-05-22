"""hve.gui.markdown_preview.markdown_html_renderer — Markdown → HTML 変換。

責務:
    - ``markdown-it-py`` で CommonMark を HTML に変換する。
    - fenced code block の ``lang == "mermaid"`` を ``<div class="mermaid">`` に変換し、
      preview.html 側の Mermaid JS でレンダリングできるようにする。
    - 他言語の fenced code block は ``CodeHighlighter`` (Pygments) でハイライトする。
    - インライン/ブロック数式 (``$...$`` / ``$$...$$``) は raw のまま残し、
      preview.html 側の KaTeX auto-render でレンダリングする。
    - 完成 HTML を ``preview.html`` テンプレートの ``{{CONTENT}}`` 部分に埋め込む。

責務外:
    - ファイル読込は ``MarkdownLoader`` の役割。
    - QWebEngineView への描画は ``MarkdownPreviewPanel`` の役割。
"""

from __future__ import annotations

import html as _html
from importlib.resources import files
from pathlib import Path
from typing import Optional

from markdown_it import MarkdownIt

from .code_highlighter import CodeHighlighter, get_style_css


_TEMPLATE_PACKAGE = "hve.gui.markdown_preview"
_TEMPLATE_FILE = "assets/preview.html"


def _load_template() -> str:
    """``preview.html`` テンプレートを読み込む。"""
    return files(_TEMPLATE_PACKAGE).joinpath(_TEMPLATE_FILE).read_text(encoding="utf-8")


class MarkdownHtmlRenderer:
    """Markdown 文字列を完成 HTML（preview.html テンプレート埋込済）に変換する。"""

    def __init__(self) -> None:
        self._md = MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": False})
        self._highlighter = CodeHighlighter()
        self._install_fence_rule()
        self._template = _load_template()

    def _install_fence_rule(self) -> None:
        """fence ルールを上書きして Mermaid 変換と Pygments ハイライトを適用する。"""
        highlighter = self._highlighter

        def render_fence(self_renderer, tokens, idx, options, env):
            # markdown-it-py の add_render_rule は内部で self（RendererHTML）を
            # 第 1 引数として渡すため、5 引数シグネチャが必要。
            token = tokens[idx]
            info = (token.info or "").strip()
            content = token.content
            lang = info.split(None, 1)[0] if info else ""

            if lang.lower() == "mermaid":
                escaped = _html.escape(content)
                return f'<div class="mermaid">{escaped}</div>\n'

            if lang:
                # 言語指定 fence は Pygments でハイライト。
                # 不明言語は highlight_text 内部で ClassNotFound を処理し <pre> フォールバックされる。
                return highlighter.highlight_text(lang, content) + "\n"

            # フォールバック: プレーン <pre><code>
            escaped = _html.escape(content)
            return f'<pre><code class="language-{_html.escape(lang)}">{escaped}</code></pre>\n'

        self._md.add_render_rule("fence", render_fence)

    def render_body(self, markdown_text: str) -> str:
        """Markdown 本文だけを HTML に変換する（テンプレート埋込なし）。"""
        return self._md.render(markdown_text)

    def render_full(self, markdown_text: str) -> str:
        """preview.html テンプレートに埋込済の完成 HTML を返す。"""
        body_html = self.render_body(markdown_text)
        # Pygments の style CSS をテンプレ末尾近くに inline で差し込むため、{{CONTENT}} 置換時に同梱
        injected = f"<style>{get_style_css()}</style>\n{body_html}"
        return self._template.replace("{{CONTENT}}", injected)

    def wrap_html_in_template(self, inner_html: str) -> str:
        """任意の HTML（例: CodeHighlighter 出力）を preview.html テンプレートに埋め込む。"""
        return self._template.replace("{{CONTENT}}", inner_html)
