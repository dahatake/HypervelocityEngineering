"""hve.gui.theme のトークン契約テスト。

検証観点:
1. 全トークンが light / dark 双方の値を持ち、書式が妥当であること
2. ``build_palette`` が 21 の ColorRole すべてを埋めること
3. ``build_stylesheet`` が ``ROLES`` すべての規則を含むこと
4. 主要な前景×背景ペアが WCAG 2.1 AA を満たすこと
5. 実描画したチェックボックス／ラジオが状態を判別でき、背景と識別できること
6. 色リテラルが theme.py の外へ再混入していないこと
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QPalette  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QLabel,
    QRadioButton,
    QStyleFactory,
    QWidget,
)

from hve.gui import theme  # noqa: E402


_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_RGBA = re.compile(r"^rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(,\s*[\d.]+\s*)?\)$")

# WCAG 2.1 SC 1.4.3 (Contrast Minimum) — 通常サイズの本文。
_MIN_TEXT = 4.5
# WCAG 2.1 SC 1.4.11 (Non-text Contrast) — UI コンポーネント。
_MIN_COMPONENT = 3.0
# SC 1.4.3 / 1.4.11 はいずれも inactive component を除外するが、
# 「そこに何があるか」は見える必要があるため独自に下限を設ける。
_MIN_DISABLED_COMPONENT = 2.0

# 実際に前景と背景として重なるトークンの組み合わせ。
_TEXT_PAIRS = [
    ("foreground", "palette.window"),
    ("descriptionForeground", "palette.window"),
    ("descriptionForeground", "panel.background"),
    ("disabledForeground", "palette.window"),
    ("disabledForeground", "palette.base"),
    ("errorForeground", "palette.window"),
    ("warningForeground", "palette.window"),
    ("successForeground", "palette.window"),
    ("accentForeground", "palette.window"),
    ("accentForeground", "palette.base"),
    ("palette.windowText", "palette.window"),
    ("palette.text", "palette.base"),
    ("palette.buttonText", "palette.button"),
    ("palette.placeholderText", "palette.base"),
    ("palette.highlightedText", "palette.highlight"),
    ("palette.toolTipText", "palette.toolTipBase"),
    ("palette.link", "palette.base"),
    ("palette.linkVisited", "palette.base"),
    ("banner.info.foreground", "banner.info.background"),
    ("banner.hint.foreground", "banner.hint.background"),
    ("button.primary.foreground", "button.primary.background"),
    ("status.pending", "palette.window"),
    ("status.running", "palette.window"),
    ("status.done", "palette.window"),
    ("status.failed", "palette.window"),
    ("status.skipped", "palette.window"),
    ("status.blocked", "palette.window"),
    ("git.addedForeground", "palette.base"),
    ("git.modifiedForeground", "palette.base"),
]

# 無効表示の組み合わせ（WCAG 免除だが判別可能であること）。
_DISABLED_PAIRS = [
    ("palette.disabledText", "palette.window"),
    ("button.primary.disabledForeground", "button.primary.disabledBackground"),
]

_ALL_ROLES = [
    QPalette.ColorRole.WindowText,
    QPalette.ColorRole.Button,
    QPalette.ColorRole.Light,
    QPalette.ColorRole.Midlight,
    QPalette.ColorRole.Dark,
    QPalette.ColorRole.Mid,
    QPalette.ColorRole.Text,
    QPalette.ColorRole.BrightText,
    QPalette.ColorRole.ButtonText,
    QPalette.ColorRole.Base,
    QPalette.ColorRole.Window,
    QPalette.ColorRole.Shadow,
    QPalette.ColorRole.Highlight,
    QPalette.ColorRole.HighlightedText,
    QPalette.ColorRole.Link,
    QPalette.ColorRole.LinkVisited,
    QPalette.ColorRole.AlternateBase,
    QPalette.ColorRole.ToolTipBase,
    QPalette.ColorRole.ToolTipText,
    QPalette.ColorRole.PlaceholderText,
    QPalette.ColorRole.Accent,
]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _relative_luminance(value: str) -> float:
    color = QColor(value)

    def channel(raw: int) -> float:
        v = raw / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.red())
        + 0.7152 * channel(color.green())
        + 0.0722 * channel(color.blue())
    )


def contrast_ratio(fg: str, bg: str) -> float:
    a, b = _relative_luminance(fg), _relative_luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


# ---------------------------------------------------------------------------
# 1. トークン網羅性
# ---------------------------------------------------------------------------
def test_every_token_defines_both_themes():
    for name, values in theme.TOKENS.items():
        assert set(values) == set(theme.THEMES), f"{name} は light/dark 両方が必要"


def test_every_token_value_is_wellformed():
    for name, values in theme.TOKENS.items():
        for variant, value in values.items():
            assert _HEX.match(value) or _RGBA.match(value), (
                f"{name}.{variant} の書式が不正: {value!r}"
            )


def test_token_rejects_unknown_name():
    with pytest.raises(KeyError):
        theme.token("no.such.token")


def test_token_uses_current_theme_by_default():
    previous = theme.current_theme()
    try:
        theme.set_current_theme("dark")
        assert theme.token("foreground") == theme.TOKENS["foreground"]["dark"]
        theme.set_current_theme("light")
        assert theme.token("foreground") == theme.TOKENS["foreground"]["light"]
    finally:
        theme.set_current_theme(previous)


def test_unknown_theme_falls_back_to_default():
    assert theme.normalize_theme("solarized") == theme.DEFAULT_THEME
    assert theme.normalize_theme(None) == theme.DEFAULT_THEME


# ---------------------------------------------------------------------------
# 2. QPalette
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", theme.THEMES)
def test_build_palette_sets_every_color_role(qapp, name):
    palette = theme.build_palette(name)
    unset = [
        role.name
        for role in _ALL_ROLES
        if not palette.isBrushSet(QPalette.ColorGroup.Active, role)
    ]
    assert not unset, f"{name}: 未設定ロールはシステム配色へフォールバックする: {unset}"


@pytest.mark.parametrize("name", theme.THEMES)
def test_disabled_group_differs_from_active(qapp, name):
    palette = theme.build_palette(name)
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.ButtonText,
    ):
        active = palette.color(QPalette.ColorGroup.Active, role).name()
        disabled = palette.color(QPalette.ColorGroup.Disabled, role).name()
        assert active != disabled, f"{name}/{role.name} が Disabled と同色"


# ---------------------------------------------------------------------------
# 3. スタイルシート
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", theme.THEMES)
def test_stylesheet_covers_every_role(name):
    qss = theme.build_stylesheet(name)
    missing = [role for role in theme.ROLES if f'hveRole="{role}"' not in qss]
    assert not missing, f"{name}: hveRole の規則が無い: {missing}"


@pytest.mark.parametrize("name", theme.THEMES)
def test_stylesheet_defines_checked_and_disabled_states(name):
    qss = theme.build_stylesheet(name)
    # サブコントロールを 1 つでも指定するとネイティブ描画が止まるため、
    # 状態別の指定が欠けると checked/unchecked が判別できなくなる。
    for selector in (
        "QCheckBox::indicator:checked",
        "QCheckBox::indicator:disabled",
        "QRadioButton::indicator:checked",
        "QRadioButton::indicator:disabled",
    ):
        assert selector in qss, f"{name}: {selector} が未定義"


def test_indicator_icons_exist():
    for filename in ("check.svg", "radio-dot.svg"):
        assert (theme._ICON_DIR / filename).is_file(), f"{filename} が無い"


# ---------------------------------------------------------------------------
# 4. コントラスト比
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", theme.THEMES)
def test_text_pairs_meet_wcag_aa(name):
    failures = []
    for fg, bg in _TEXT_PAIRS:
        ratio = contrast_ratio(theme.token(fg, name), theme.token(bg, name))
        if ratio < _MIN_TEXT:
            failures.append(f"{fg} on {bg} = {ratio:.2f}:1")
    assert not failures, f"{name}: WCAG AA ({_MIN_TEXT}:1) 未達 -> {failures}"


@pytest.mark.parametrize("name", theme.THEMES)
def test_disabled_pairs_remain_distinguishable(name):
    failures = []
    for fg, bg in _DISABLED_PAIRS:
        ratio = contrast_ratio(theme.token(fg, name), theme.token(bg, name))
        if ratio < _MIN_COMPONENT:
            failures.append(f"{fg} on {bg} = {ratio:.2f}:1")
    assert not failures, f"{name}: {_MIN_COMPONENT}:1 未達 -> {failures}"


# ---------------------------------------------------------------------------
# 5. 実描画
# ---------------------------------------------------------------------------
def _dominant_colors(widget: QWidget, size: int = 20) -> list[str]:
    image = widget.grab().toImage()
    counts: dict[str, int] = {}
    for y in range(min(size, image.height())):
        for x in range(min(size, image.width())):
            key = QColor(image.pixelColor(x, y)).name()
            counts[key] = counts.get(key, 0) + 1
    return [k for k, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:5]]


@pytest.fixture
def themed_app(qapp, request):
    name = request.param
    previous_theme = theme.current_theme()
    previous_style = qapp.style().objectName()
    qapp.setStyle(QStyleFactory.create("Fusion"))
    theme.set_current_theme(name)
    qapp.setPalette(theme.build_palette(name))
    qapp.setStyleSheet(theme.build_stylesheet(name))
    yield name
    qapp.setStyleSheet("")
    restored = QStyleFactory.create(previous_style)
    if restored is not None:
        qapp.setStyle(restored)
    theme.set_current_theme(previous_theme)


@pytest.mark.parametrize("themed_app", theme.THEMES, indirect=True)
def test_indicators_are_visible_and_state_is_distinguishable(themed_app):
    name = themed_app
    window_color = theme.token("palette.window", name)

    host = QWidget()
    host.resize(220, 140)
    unchecked = QCheckBox("u", host)
    unchecked.setGeometry(0, 0, 200, 22)
    checked = QCheckBox("c", host)
    checked.setGeometry(0, 24, 200, 22)
    checked.setChecked(True)
    disabled = QCheckBox("d", host)
    disabled.setGeometry(0, 48, 200, 22)
    disabled.setEnabled(False)
    radio_off = QRadioButton("u", host)
    radio_off.setGeometry(0, 72, 200, 22)
    radio_on = QRadioButton("c", host)
    radio_on.setGeometry(0, 96, 200, 22)
    radio_on.setChecked(True)
    host.ensurePolished()

    cases = [
        ("checkbox unchecked", unchecked, _MIN_COMPONENT),
        ("checkbox checked", checked, _MIN_COMPONENT),
        ("checkbox disabled", disabled, _MIN_DISABLED_COMPONENT),
        ("radio unchecked", radio_off, _MIN_COMPONENT),
        ("radio checked", radio_on, _MIN_COMPONENT),
    ]
    for label, widget, minimum in cases:
        colors = _dominant_colors(widget)
        best = max(contrast_ratio(c, window_color) for c in colors)
        assert best >= minimum, (
            f"{name}/{label}: 背景 {window_color} との最大コントラストが "
            f"{best:.2f}:1 で {minimum}:1 未満"
        )

    assert _dominant_colors(unchecked) != _dominant_colors(checked), (
        f"{name}: チェックボックスの ON/OFF が同一描画"
    )
    assert _dominant_colors(radio_off) != _dominant_colors(radio_on), (
        f"{name}: ラジオの ON/OFF が同一描画"
    )


@pytest.mark.parametrize("themed_app", theme.THEMES, indirect=True)
def test_hve_role_color_applies_even_with_widget_local_stylesheet(themed_app):
    name = themed_app
    host = QWidget()
    host.resize(200, 60)
    label = QLabel("description", host)
    label.setGeometry(0, 0, 180, 24)
    label.setProperty("hveRole", "description")
    # 色を含まない自前 QSS はアプリ全体 QSS の色指定と共存できる。
    label.setStyleSheet("padding: 2px; font-size: 9pt;")
    host.ensurePolished()

    expected = theme.token("descriptionForeground", name).lower()
    assert expected in _dominant_colors(label, size=180)


# ---------------------------------------------------------------------------
# 6. 色リテラルの再混入防止
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCAN_ROOTS = ("hve/gui", "mdq/gui", "cq/gui")
_SCAN_SKIP = ("__pycache__", "xterm_assets", "/assets/", "/tests/")
# 色の定義そのものを持ってよいモジュール。
# status_banner / dag_status_widget は独自に light/dark 両値を持つ既存実装で、
# 症状が出ていないため今回のトークン移行の対象外とした。
_COLOR_LITERAL_ALLOWLIST = (
    "hve/gui/theme.py",
    "hve/gui/status_banner.py",
    "hve/gui/widgets/dag_status_widget.py",
)
# ``&#NNN;`` is an HTML numeric entity, not a CSS colour literal.
_COLOR_LITERAL = re.compile(r"(?<!&)#[0-9a-fA-F]{3,8}\b|\brgba?\(")


def _iter_source_files():
    for root in _SCAN_ROOTS:
        base = _REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(_REPO_ROOT).as_posix()
            if any(token_ in f"/{rel}" for token_ in _SCAN_SKIP):
                continue
            yield rel, path


def test_no_hardcoded_color_literals_outside_theme_module():
    offenders = []
    for rel, path in _iter_source_files():
        if rel in _COLOR_LITERAL_ALLOWLIST:
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8-sig").splitlines(), 1
        ):
            if line.lstrip().startswith("#"):
                continue
            if _COLOR_LITERAL.search(line):
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert not offenders, (
        "色リテラルは hve/gui/theme.py に集約すること。"
        f" 検出 {len(offenders)} 件 -> {offenders[:10]}"
    )


def _literal_calls(path: Path, func_name: str, arg_index: int = 0):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        if name != func_name or len(node.args) <= arg_index:
            continue
        arg = node.args[arg_index]
        if isinstance(arg, ast.Constant):
            yield node.lineno, arg.value, node


def test_hve_role_values_are_known():
    offenders = []
    for rel, path in _iter_source_files():
        for lineno, key, node in _literal_calls(path, "setProperty"):
            if key != "hveRole":
                continue
            value = node.args[1]
            if not isinstance(value, ast.Constant) or value.value not in theme.ROLES:
                shown = getattr(value, "value", "<non-literal>")
                offenders.append(f"{rel}:{lineno}: {shown!r}")
    assert not offenders, f"未定義の hveRole -> {offenders}"


def test_token_names_are_known():
    offenders = []
    for rel, path in _iter_source_files():
        for lineno, value, _node in _literal_calls(path, "token"):
            if value not in theme.TOKENS:
                offenders.append(f"{rel}:{lineno}: {value!r}")
    assert not offenders, f"未定義のトークン名 -> {offenders}"
