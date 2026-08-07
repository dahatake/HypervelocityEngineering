"""hve.gui.theme — GUI 全体のセマンティックカラートークン。

VS Code の色レジストリ（``registerColor(id, {light, dark, ...})``）に倣い、
**すべてのトークンが light / dark 双方の値を必ず持つ** 単一のテーブルを持つ。
各ウィジェットはリテラル色を書かず、次のいずれかでトークンを参照する。

1. **動的プロパティ ``hveRole``**（推奨）
   ``widget.setProperty("hveRole", "description")`` と書くだけでよい。実際の色は
   :func:`build_stylesheet` が生成するアプリ全体スタイルシートが与えるため、
   テーマ切替時に**再起動なしで追従**する。ウィジェット自前の
   ``setStyleSheet()`` は色を含まない指定（padding / font 等）に限ること。
   色を含めるとウィジェット側が優先され、テーマ追従が壊れる。

2. :func:`token` による直接取得
   HTML 文字列（``<span style='color:...'>``）や ``QColor`` 生成など、
   スタイルシートで到達できない箇所のみで使う。

``QApplication`` へは :func:`build_palette` と :func:`build_stylesheet` の結果を
``hve.gui.app.apply_theme_to_application`` が適用する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Mapping

from PySide6.QtGui import QColor, QPalette


THEMES = ("light", "dark")
DEFAULT_THEME = "light"

_ICON_DIR = Path(__file__).parent / "icons"


# ---------------------------------------------------------------------------
# トークン定義
# ---------------------------------------------------------------------------
# すべてのエントリが "light" と "dark" の両方を持つこと（test_theme_tokens が検証）。
TOKENS: Dict[str, Dict[str, str]] = {
    # --- QPalette ロール -----------------------------------------------
    "palette.window": {"light": "#f3f3f3", "dark": "#1f2328"},
    "palette.windowText": {"light": "#1f2328", "dark": "#e6edf3"},
    "palette.base": {"light": "#ffffff", "dark": "#0d1117"},
    "palette.alternateBase": {"light": "#f6f8fa", "dark": "#161b22"},
    "palette.text": {"light": "#1f2328", "dark": "#e6edf3"},
    "palette.button": {"light": "#f3f3f3", "dark": "#21262d"},
    "palette.buttonText": {"light": "#1f2328", "dark": "#e6edf3"},
    "palette.brightText": {"light": "#ffffff", "dark": "#ffffff"},
    "palette.highlight": {"light": "#0969da", "dark": "#58a6ff"},
    "palette.highlightedText": {"light": "#ffffff", "dark": "#0d1117"},
    "palette.toolTipBase": {"light": "#ffffff", "dark": "#21262d"},
    "palette.toolTipText": {"light": "#1f2328", "dark": "#e6edf3"},
    "palette.placeholderText": {"light": "#6e7781", "dark": "#8b949e"},
    "palette.link": {"light": "#0969da", "dark": "#58a6ff"},
    "palette.linkVisited": {"light": "#8250df", "dark": "#bc8cff"},
    "palette.light": {"light": "#ffffff", "dark": "#30363d"},
    "palette.midlight": {"light": "#f0f2f4", "dark": "#2a3038"},
    "palette.dark": {"light": "#8c959f", "dark": "#010409"},
    "palette.mid": {"light": "#afb8c1", "dark": "#484f58"},
    "palette.shadow": {"light": "#d0d7de", "dark": "#010409"},
    "palette.accent": {"light": "#0969da", "dark": "#58a6ff"},
    "palette.disabledText": {"light": "#818b95", "dark": "#6e7681"},
    # --- 前景 ----------------------------------------------------------
    "foreground": {"light": "#1f2328", "dark": "#e6edf3"},
    "descriptionForeground": {"light": "#57606a", "dark": "#9198a1"},
    "disabledForeground": {"light": "#656d76", "dark": "#8b949e"},
    "errorForeground": {"light": "#cf222e", "dark": "#ff7b72"},
    "warningForeground": {"light": "#8b5f00", "dark": "#d29922"},
    "successForeground": {"light": "#1a7f37", "dark": "#3fb950"},
    "accentForeground": {"light": "#0969da", "dark": "#58a6ff"},
    # --- 面・境界 ------------------------------------------------------
    "panel.background": {"light": "#f6f8fa", "dark": "#161b22"},
    "panel.border": {"light": "#d0d7de", "dark": "#30363d"},
    "separator.foreground": {"light": "#e0e3e8", "dark": "#30363d"},
    # --- バナー --------------------------------------------------------
    "banner.info.background": {"light": "#e3f2fd", "dark": "#0d2847"},
    "banner.info.foreground": {"light": "#0d47a1", "dark": "#a5d6ff"},
    "banner.info.border": {"light": "#90caf9", "dark": "#1f4d80"},
    "banner.hint.background": {"light": "#fffde7", "dark": "#2d2a17"},
    "banner.hint.foreground": {"light": "#424242", "dark": "#e6dfc4"},
    "banner.hint.border": {"light": "#fbc02d", "dark": "#7d6a1f"},
    # --- ボタン --------------------------------------------------------
    "button.primary.background": {"light": "#1976d2", "dark": "#1f6feb"},
    "button.primary.foreground": {"light": "#ffffff", "dark": "#ffffff"},
    "button.primary.disabledBackground": {"light": "#d0d7de", "dark": "#30363d"},
    "button.primary.disabledForeground": {"light": "#6e7781", "dark": "#8b949e"},
    "toolButton.hoverBackground": {
        "light": "rgba(0, 0, 0, 0.08)",
        "dark": "rgba(255, 255, 255, 0.10)",
    },
    "toolButton.checkedBackground": {
        "light": "rgba(0, 0, 0, 0.12)",
        "dark": "rgba(255, 255, 255, 0.16)",
    },
    "toolButton.checkedBorder": {
        "light": "rgba(0, 0, 0, 0.20)",
        "dark": "rgba(255, 255, 255, 0.30)",
    },
    # --- チェックボックス / ラジオ --------------------------------------
    "checkbox.background": {"light": "#ffffff", "dark": "#0d1117"},
    "checkbox.border": {"light": "#6e7781", "dark": "#8b949e"},
    "checkbox.checkedBackground": {"light": "#0969da", "dark": "#1f6feb"},
    "checkbox.disabledBackground": {"light": "#f0f2f4", "dark": "#21262d"},
    # 無効時も「そこに部品がある」ことは見える必要があるため 3:1 を確保する。
    "checkbox.disabledBorder": {"light": "#8c959f", "dark": "#6e7681"},
    # --- 実行ステータス ------------------------------------------------
    "status.pending": {"light": "#57606a", "dark": "#8b949e"},
    "status.running": {"light": "#8b5f00", "dark": "#d29922"},
    "status.done": {"light": "#1a7f37", "dark": "#3fb950"},
    "status.failed": {"light": "#cf222e", "dark": "#ff7b72"},
    "status.skipped": {"light": "#0969da", "dark": "#39c5cf"},
    "status.blocked": {"light": "#8250df", "dark": "#b07ed5"},
    # --- Git 装飾 ------------------------------------------------------
    "git.addedForeground": {"light": "#1a7f37", "dark": "#3fb950"},
    "git.modifiedForeground": {"light": "#8b5f00", "dark": "#d29922"},
}


# ``hveRole`` として指定できる値。build_stylesheet が規則を生成する。
ROLES = (
    "description",
    "muted",
    "error",
    "warning",
    "success",
    "accent",
    "panel",
    "noteBox",
    "sectionHeader",
    "bordered",
    "separator",
    "infoBanner",
    "hintPopup",
    "dropArea",
    "primaryButton",
    "toolToggle",
)


_current_theme = DEFAULT_THEME


def normalize_theme(theme: str | None) -> str:
    """未知の値・None を :data:`DEFAULT_THEME` へ丸める。"""
    return theme if theme in THEMES else DEFAULT_THEME


def set_current_theme(theme: str | None) -> str:
    """:func:`token` の既定テーマを更新し、正規化後の名前を返す。"""
    global _current_theme
    _current_theme = normalize_theme(theme)
    return _current_theme


def current_theme() -> str:
    return _current_theme


def token(name: str, theme: str | None = None) -> str:
    """トークン名から色文字列を返す。

    Args:
        name: :data:`TOKENS` のキー。
        theme: ``"light"`` / ``"dark"``。省略時は :func:`current_theme`。

    Raises:
        KeyError: 未定義のトークン名（typo を早期に落とすため fail-closed）。
    """
    try:
        entry = TOKENS[name]
    except KeyError:
        raise KeyError(f"unknown theme token: {name!r}") from None
    return entry[normalize_theme(theme) if theme is not None else _current_theme]


# ---------------------------------------------------------------------------
# QPalette
# ---------------------------------------------------------------------------
_PALETTE_ROLES: Mapping[str, QPalette.ColorRole] = {
    "palette.window": QPalette.ColorRole.Window,
    "palette.windowText": QPalette.ColorRole.WindowText,
    "palette.base": QPalette.ColorRole.Base,
    "palette.alternateBase": QPalette.ColorRole.AlternateBase,
    "palette.text": QPalette.ColorRole.Text,
    "palette.button": QPalette.ColorRole.Button,
    "palette.buttonText": QPalette.ColorRole.ButtonText,
    "palette.brightText": QPalette.ColorRole.BrightText,
    "palette.highlight": QPalette.ColorRole.Highlight,
    "palette.highlightedText": QPalette.ColorRole.HighlightedText,
    "palette.toolTipBase": QPalette.ColorRole.ToolTipBase,
    "palette.toolTipText": QPalette.ColorRole.ToolTipText,
    "palette.placeholderText": QPalette.ColorRole.PlaceholderText,
    "palette.link": QPalette.ColorRole.Link,
    "palette.linkVisited": QPalette.ColorRole.LinkVisited,
    "palette.light": QPalette.ColorRole.Light,
    "palette.midlight": QPalette.ColorRole.Midlight,
    "palette.dark": QPalette.ColorRole.Dark,
    "palette.mid": QPalette.ColorRole.Mid,
    "palette.shadow": QPalette.ColorRole.Shadow,
    "palette.accent": QPalette.ColorRole.Accent,
}

# Disabled グループだけ別色にするロール。2 引数版 setColor は全 ColorGroup を
# 同色にするため、これを補わないと「グレーアウト」の視覚的手掛かりが消える。
# HighlightedText は Highlight 上に載るため薄くすると逆に読めなくなる。含めない。
_DISABLED_ROLES = (
    QPalette.ColorRole.Text,
    QPalette.ColorRole.WindowText,
    QPalette.ColorRole.ButtonText,
)


def build_palette(theme: str) -> QPalette:
    """21 の ColorRole すべてを埋めた :class:`QPalette` を返す。

    未設定ロールを残すとシステムパレット（OS の外観）から解決され、
    テーマが混色するため、全ロールを明示する。
    """
    theme = normalize_theme(theme)
    palette = QPalette()
    for name, role in _PALETTE_ROLES.items():
        palette.setColor(role, QColor(token(name, theme)))
    disabled_text = QColor(token("palette.disabledText", theme))
    for role in _DISABLED_ROLES:
        palette.setColor(QPalette.ColorGroup.Disabled, role, disabled_text)
    return palette


# ---------------------------------------------------------------------------
# アプリ全体スタイルシート
# ---------------------------------------------------------------------------
def _icon_url(filename: str) -> str:
    """QSS の ``url()`` へ埋め込める文字列を返す。

    インストール先にスペースを含み得るため、POSIX 区切りにしたうえで引用する。
    """
    return '"' + _ICON_DIR.joinpath(filename).as_posix() + '"'


def build_stylesheet(theme: str) -> str:
    """``QApplication.setStyleSheet()`` へ渡すテーマ依存の QSS を組み立てる。

    ネイティブスタイルを使わない前提（``Fusion`` 固定）で、Fusion が
    パレットから導出できない部分だけを補う:

    - チェックボックス / ラジオの indicator（Fusion 既定は暗いテーマで
      背景とのコントラストが 1.20:1 まで落ちる）
    - ``hveRole`` プロパティによるセマンティック配色
    """
    theme = normalize_theme(theme)
    t = {name: token(name, theme) for name in TOKENS}
    check_url = _icon_url("check.svg")
    dot_url = _icon_url("radio-dot.svg")

    return f"""
/* ---- 前景ロール ---- */
*[hveRole="description"] {{ color: {t['descriptionForeground']}; }}
*[hveRole="muted"] {{ color: {t['disabledForeground']}; }}
*[hveRole="error"] {{ color: {t['errorForeground']}; }}
*[hveRole="warning"] {{ color: {t['warningForeground']}; }}
*[hveRole="success"] {{ color: {t['successForeground']}; }}
*[hveRole="accent"] {{ color: {t['accentForeground']}; }}

/* ---- 面・境界ロール ---- */
*[hveRole="panel"] {{
    background-color: {t['panel.background']};
    border: 1px solid {t['panel.border']};
    border-radius: 4px;
}}
*[hveRole="noteBox"] {{
    color: {t['descriptionForeground']};
    background-color: {t['panel.background']};
    border-left: 3px solid {t['panel.border']};
}}
*[hveRole="sectionHeader"] {{
    color: {t['foreground']};
    border-bottom: 1px solid {t['panel.border']};
}}
*[hveRole="bordered"] {{ border: 1px solid {t['panel.border']}; }}
*[hveRole="separator"] {{ color: {t['separator.foreground']}; }}

/* ---- バナー ---- */
*[hveRole="infoBanner"] {{
    background-color: {t['banner.info.background']};
    border: 1px solid {t['banner.info.border']};
    border-radius: 6px;
}}
*[hveRole="infoBanner"] QLabel {{
    color: {t['banner.info.foreground']};
    background-color: transparent;
}}
*[hveRole="hintPopup"] {{
    background-color: {t['banner.hint.background']};
    border: 1px solid {t['banner.hint.border']};
    border-radius: 6px;
}}
*[hveRole="hintPopup"] QLabel {{
    color: {t['banner.hint.foreground']};
    background-color: transparent;
}}
*[hveRole="dropArea"] {{
    color: {t['banner.info.foreground']};
    background-color: {t['banner.info.background']};
    border: 2px dashed {t['banner.info.border']};
    border-radius: 6px;
}}

/* ---- ボタン ---- */
QPushButton[hveRole="primaryButton"] {{
    background-color: {t['button.primary.background']};
    color: {t['button.primary.foreground']};
    border: none;
    border-radius: 4px;
}}
QPushButton[hveRole="primaryButton"]:disabled {{
    background-color: {t['button.primary.disabledBackground']};
    color: {t['button.primary.disabledForeground']};
}}
QToolButton[hveRole="toolToggle"] {{
    background: transparent;
    border: 1px solid transparent;
}}
QToolButton[hveRole="toolToggle"]:hover {{
    background-color: {t['toolButton.hoverBackground']};
}}
QToolButton[hveRole="toolToggle"]:checked {{
    background-color: {t['toolButton.checkedBackground']};
    border: 1px solid {t['toolButton.checkedBorder']};
}}

/* ---- チェックボックス / ラジオ ----
   Qt はサブコントロールを 1 つでも指定するとネイティブ描画をやめるため、
   checked / disabled も併せて定義しないと状態が判別できなくなる。 */
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {t['checkbox.border']};
    background-color: {t['checkbox.background']};
}}
QCheckBox::indicator {{ border-radius: 3px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {t['accentForeground']};
}}
QCheckBox::indicator:checked {{
    background-color: {t['checkbox.checkedBackground']};
    border-color: {t['checkbox.checkedBackground']};
    image: url({check_url});
}}
QRadioButton::indicator:checked {{
    background-color: {t['checkbox.checkedBackground']};
    border-color: {t['checkbox.checkedBackground']};
    image: url({dot_url});
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    background-color: {t['checkbox.disabledBackground']};
    border-color: {t['checkbox.disabledBorder']};
}}
QCheckBox::indicator:checked:disabled, QRadioButton::indicator:checked:disabled {{
    background-color: {t['checkbox.disabledBorder']};
    border-color: {t['checkbox.disabledBorder']};
}}
""".strip()
