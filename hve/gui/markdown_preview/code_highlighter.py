"""hve.gui.markdown_preview.code_highlighter — Pygments を使った HTML 生成。

責務:
    - パスから lexer 推定 → ``HtmlFormatter`` で HTML 化。
    - lexer 未検出時はプレーン ``<pre>`` フォールバック。
    - スタイル CSS は class-level キャッシュ。

Note:
    モジュール変数 ``_FORMATTER`` / ``_STYLE_CSS`` の初期化はスレッド非安全。
    GUI メインスレッドからのみ呼び出される前提。
"""

from __future__ import annotations

import html as _html
from pathlib import Path
from typing import Optional

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer_for_filename
from pygments.util import ClassNotFound


_STYLE_NAME = "default"
_FORMATTER: Optional[HtmlFormatter] = None
_STYLE_CSS: Optional[str] = None


def _get_formatter() -> HtmlFormatter:
    global _FORMATTER
    if _FORMATTER is None:
        _FORMATTER = HtmlFormatter(style=_STYLE_NAME, cssclass="highlight", nowrap=False)
    return _FORMATTER


def get_style_css() -> str:
    """Pygments スタイルの CSS を返す（初回のみ生成、以降キャッシュ）。"""
    global _STYLE_CSS
    if _STYLE_CSS is None:
        _STYLE_CSS = _get_formatter().get_style_defs(".highlight")
    return _STYLE_CSS


class CodeHighlighter:
    """ファイル内容をシンタックスハイライト HTML に変換する。"""

    def highlight_file(self, path: Path, raw_text: str) -> str:
        """ファイルパスと内容から HTML 文字列を返す。

        Returns:
            ``<style>...</style><div class="highlight"><pre>...</pre></div>`` 形式の HTML。
            lexer 未検出時は ``<pre>`` でエスケープ済テキストを返す。
        """
        p = Path(path)
        try:
            lexer = guess_lexer_for_filename(str(p), raw_text)
        except ClassNotFound:
            escaped = _html.escape(raw_text)
            return f'<pre class="plain">{escaped}</pre>'

        body = highlight(raw_text, lexer, _get_formatter())
        style = get_style_css()
        return f"<style>{style}</style>{body}"

    def highlight_text(self, lang: str, raw_text: str) -> str:
        """言語名を明示してハイライトする（fenced code block 用）。

        Pygments の 不明言語は ``ClassNotFound`` となり、<pre> フォールバック。
        """
        try:
            lexer = get_lexer_by_name(lang)
        except ClassNotFound:
            escaped = _html.escape(raw_text)
            return f'<pre class="plain">{escaped}</pre>'

        body = highlight(raw_text, lexer, _get_formatter())
        style = get_style_css()
        return f"<style>{style}</style>{body}"