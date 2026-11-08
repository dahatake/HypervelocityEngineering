"""FR-1047 / NFR-A11Y-001: the design tokens, checked from the style sheet text alone (no browser).

Expected values come from the acceptance criteria and PARAM-028/029/030/035/036; the System Tests
(tests/system/e2e/test_studio_fluent_appearance_system.py) check the same in a real browser.
"""
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"
TOKENS = (WEB / "tokens.css").read_text(encoding="utf-8")
THEME_JS = (WEB / "js" / "theme.js").read_text(encoding="utf-8")
P_TEXT, P_NONTEXT, P_GRID = 4.5, 3.0, 4  # PARAM-028 / 029 / 030


def _block(selector_start):
    i = TOKENS.index(selector_start)
    j = TOKENS.index("}", i)
    return TOKENS[i:j]


def _colors(block):
    return {k: v.strip() for k, v in re.findall(r"(--color-[\w-]+):\s*([^;]+);", block)}


def _lum(hexv):
    h = hexv.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    f = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2]


def _ratio(a, b):
    hi, lo = sorted([_lum(a), _lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


LIGHT = _colors(_block(":root {"))
DARK = {**LIGHT, **_colors(_block(':root[data-theme="dark"]'))}


# FR-1047 AC-259: every colour token has a value in both themes
def test_ac259_dark_theme_overrides_every_opaque_light_colour_token():
    dark_only = _colors(_block(':root[data-theme="dark"]'))
    missing = [k for k in LIGHT if k not in dark_only]
    assert not missing, missing


# NFR-A11Y-001 AC-269: foreground/background pairs >= 4.5:1, non-text >= 3:1, in both themes
def test_ac269_token_contrast_meets_wcag_aa_in_both_themes():
    for name, theme in (("light", LIGHT), ("dark", DARK)):
        fg = [k for k in theme if k.startswith("--color-fg-") and "disabled" not in k]
        bg = [k for k in theme if k.startswith("--color-bg-")]
        nontext = [k for k in theme if k.startswith(("--color-border-strong", "--color-focus")) or k.endswith("-icon")]
        for f in fg:
            for b in bg:
                r = _ratio(theme[f], theme[b])
                print("contrast", name, f, b, round(r, 2))
                assert r >= P_TEXT, (name, f, b, r)
        for n in nontext:
            for b in bg:
                assert _ratio(theme[n], theme[b]) >= P_NONTEXT, (name, n, b)
        for s in ("success", "warning", "danger", "info"):
            assert _ratio(theme[f"--color-status-{s}-fg"], theme[f"--color-status-{s}-bg"]) >= P_TEXT, (name, s)


# FR-1047 AC-262: spacing / size / radius tokens are multiples of the 4px grid (1px and 2px strokes excepted)
def test_ac262_space_size_radius_tokens_are_multiples_of_grid():
    for k, v in re.findall(r"(--(?:space|size|radius)-[\w-]+):\s*([^;]+);", TOKENS):
        for num in re.findall(r"(\d+(?:\.\d+)?)px", v):
            assert float(num) % P_GRID == 0 or float(num) in (1, 2), (k, v)


# FR-1047 AC-261: body 14px, smallest caption 12px, system fonts only
def test_ac261_type_ramp_and_system_fonts():
    assert "--font-size-body: 14px;" in TOKENS and "--font-size-caption: 12px;" in TOKENS
    base = re.search(r"--font-family-base:\s*([^;]+);", TOKENS).group(1)
    assert base.startswith('"Segoe UI Variable"')
    assert "@font-face" not in TOKENS and "url(" not in TOKENS


# FR-1047 AC-260: only the theme name is stored in localStorage; invalid values fall back to system
def test_ac260_theme_choice_is_persisted_as_name_only():
    assert "localStorage" in THEME_JS and "CHOICES.indexOf(saved) >= 0" in THEME_JS and "sessionStorage" not in THEME_JS and "cookie" not in THEME_JS
    assert "var choice = 'system'" in THEME_JS
