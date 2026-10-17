"""System tests for FR-1047 (AC-258..262), FR-1048 (AC-263..268), NFR-A11Y-001 (AC-269..274),
NFR-PERF-006 (AC-275, AC-276): Fluent 2 appearance of EABK Studio.

Expected values come only from the acceptance criteria in docs/requirements-definition.md and
PARAM-006/007/021/022/028..039.  The implementation is NOT the oracle.
AC-260 is BLOCKED (Q-015: whether the theme choice may be stored) and has no test here.
(Only its "does not store" half is covered by AC-259's default-follows-OS test being run on a fresh context.)

PROVISIONAL CONTRACT (仮置き。実装者が確認し、食い違えば CONFLICT として返す。この oracle は実装に合わせて直さない):
  - スタイル: EABK-Studio/web/*.css（index.html から読む全 CSS）。トークンは CSS カスタムプロパティで、
    色は --color-*（前景 --color-fg-*、背景 --color-bg-*、罫線 --color-border-*、フォーカス --color-focus*、
    状態色 --color-status-<success|warning|danger|info>[-fg|-bg|-icon]）、
    余白 --space-*、角丸 --radius-*、影 --shadow-*、罫線の太さ --stroke-*、長さ --duration-*、緩急 --ease-*、
    文字 --font-size-*、データ可視化・3D の例外色 --viz-* / --scene-*。
  - テーマ: <html data-theme="light|dark">（解決後の値）と data-theme-choice="light|dark|system"。
    切替は [data-testid="theme-toggle"] 内の [data-theme-choice=light|dark|system] ボタン（aria-pressed）。
    コマンド検索（#q）に「テーマ」「theme」を入れると選択肢が結果に出る。
  - 状態表示: [data-testid="state-panel"][data-state=empty|loading|error|stale] の中に
    [data-part=icon] [data-part=heading] [data-part=description] [data-part=action]。
  - 基準 commit 80c7cc55 の測定値: work/**/evidence/perf-baseline-80c7cc55.json
    {"env":{...},"samples":{"first_display":[ms,...],"zoom":[...],"select":[...]}}（操作ごと PARAM-038 回以上）。

    AC-276 の基準値の取得手順（実装者が、外観変更に着手する前に最初に行う。測定済みでなければ AC-276 は失敗する）:
      1. 基準 commit の worktree を作る:  git worktree add ../eabk-baseline-80c7cc55 80c7cc55
      2. この試験ファイル（と tests/system/e2e の補助モジュール）を、その worktree の同じ場所へ複製する（基準側に無ければ）。
      3. その worktree で実行:  EABK_RECORD_PERF_BASELINE=1 python -m pytest tests/system/e2e/test_studio_fluent_appearance_system.py
            -k test_ac276 -q   （PowerShell: $env:EABK_RECORD_PERF_BASELINE='1'）
         → work/runs/202610171403/evidence/perf-baseline-80c7cc55.json（env と samples）が書かれる。
      4. そのファイルを、run の作業ブランチ側の同じパスへ複製して commit する（測定環境と値を記録する）。
      5. 以後の通常実行（環境変数なし）は、この値と比べる。測定は同じ機器・同じ環境で行う。
    """
import json
import os
import platform
import re
import subprocess
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect

from entity_repo import make_large, make_zoom
from test_studio_system import ROOT, _management_fingerprints, _repository_files, page, studio_url  # noqa: F401
from test_studio_links_wrap_status_arch_system import _serve

WEB = ROOT / "EABK-Studio" / "web"
BASE = "80c7cc55"
NAV = ["dashboard", "implstatus", "map", "diagrams", "entities", "integrations", "source", "tables", "maintenance"]
P_BODY, P_SMALL, P_GRID, P_MOTION, P_RM = 14, 12, 4, 300, 1  # PARAM-035/036/030/032/037
P_TEXT, P_NONTEXT, P_TARGET, P_REFLOW = 4.5, 3.0, 24, 320  # PARAM-028/029/031/034
P_TOL, P_ZOOM_MS, P_FIRST_S, P_N = 1.10, 100, 3, 20  # PARAM-033/021/022/038
ICON_SIZES = {16, 20, 24}  # PARAM-039


# ---------------------------------------------------------------- helpers
def _css_files():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    names = re.findall(r'<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"', html)
    return [WEB / n for n in names if not n.startswith("http")]


def _css():
    text = "\n".join(p.read_text(encoding="utf-8") for p in _css_files())
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _decls(css):
    """(selector-context, property, value) for every declaration, nesting flattened."""
    out, stack, buf = [], [], ""
    for ch in css:
        if ch == "{":
            stack.append(buf.strip())
            buf = ""
        elif ch == "}":
            stack.pop() if stack else None
            buf = ""
        elif ch == ";":
            if ":" in buf:
                k, v = buf.split(":", 1)
                out.append((" ".join(stack), k.strip(), v.strip()))
            buf = ""
        else:
            buf += ch
    return out


def _tokens(prefix):
    return sorted({k for _, k, _ in _decls(_css()) if k.startswith(prefix)})


def _rgb(page, token_or_color):
    return page.evaluate(
        """(v) => { const d = document.createElement('div');
          d.style.color = v.startsWith('--') ? `var(${v})` : v; document.body.appendChild(d);
          const c = getComputedStyle(d).color; d.remove();
          const m = c.match(/[\\d.]+/g).map(Number); return m.slice(0, 4); }""", token_or_color)


def _lum(c):
    f = lambda x: (x / 255 / 12.92) if x / 255 <= 0.03928 else (((x / 255) + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def _ratio(a, b):
    la, lb = sorted([_lum(a), _lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _theme(page, choice):
    page.locator(f'[data-testid="theme-toggle"] [data-theme-choice="{choice}"]').click()


def _go(page, route):
    page.goto(page.url.split("#")[0] + f"#/{route}")
    page.wait_for_load_state("networkidle")


@pytest.fixture()
def large_url(tmp_path):
    proc, url = _serve(make_large(tmp_path / "large"))
    yield url
    proc.terminate()


# ---------------------------------------------------------------- FR-1047
# FR-1047 AC-258
def test_ac258_tokens_defined_once_and_no_raw_colors_outside_them():
    decls = _decls(_css())
    for prefix in ("--color-", "--font-size-", "--space-", "--radius-", "--shadow-", "--stroke-", "--duration-", "--ease-"):
        assert _tokens(prefix), f"トークン {prefix}* が無い"
    for kind in ("fg", "bg", "border", "status-success", "status-warning", "status-danger", "status-info"):
        assert any(t.startswith(f"--color-{kind}") for t in _tokens("--color-")), f"--color-{kind}* が無い"
    raw = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
    bad = [(s, k, v) for s, k, v in decls if raw.search(v) and not k.startswith(("--color-", "--viz-", "--scene-"))]
    assert not bad, f"トークン定義外の色の直値: {bad[:5]}"


# FR-1047 AC-258 (異常系: 色トークンはテーマの定義場所の外に重複して散らばらない)
def test_ac258_color_tokens_only_in_root_and_theme_blocks():
    stray = [(s, k) for s, k, _ in _decls(_css()) if k.startswith("--color-") and not re.search(r":root|\[data-theme|prefers-color-scheme|forced-colors", s)]
    assert not stray, f"色トークンを :root・テーマ以外で定義: {stray[:5]}"


# FR-1047 AC-259
def test_ac259_three_choices_default_system_and_follow_os_without_reload(browser, studio_url):
    ctx = browser.new_context(color_scheme="dark")
    page = ctx.new_page()
    page.goto(studio_url)
    page.wait_for_load_state("networkidle")
    page.evaluate("window.__marker = 1")
    choices = page.locator('[data-testid="theme-toggle"] [data-theme-choice]')
    assert sorted(choices.evaluate_all("els => els.map(e => e.dataset.themeChoice)")) == ["dark", "light", "system"]
    assert page.locator("html").get_attribute("data-theme-choice") == "system"
    assert page.locator("html").get_attribute("data-theme") == "dark"
    page.emulate_media(color_scheme="light")
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    assert page.evaluate("window.__marker") == 1, "OS 側の変更で再読込された"
    ctx.close()


# FR-1047 AC-259
def test_ac259_switch_keeps_input_selection_filter_and_layout_and_works_by_keyboard(page):
    _go(page, "tables?tab=reqs")
    page.locator("#q").fill("FR-001")
    page.evaluate("window.__marker = 1")
    before = page.evaluate("() => [location.hash, document.querySelector('#view').scrollTop, innerWidth]")
    page.locator('[data-testid="theme-toggle"] [data-theme-choice="dark"]').focus()
    page.keyboard.press("Enter")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    assert page.locator("#q").input_value() == "FR-001"
    assert page.evaluate("window.__marker") == 1
    assert page.evaluate("() => [location.hash, document.querySelector('#view').scrollTop, innerWidth]") == before
    _theme(page, "light")
    expect(page.locator("html")).to_have_attribute("data-theme", "light")


# FR-1047 AC-259 (PARAM-006: コマンド検索から選べる)
@pytest.mark.parametrize("word", ["テーマ", "theme"])
def test_ac259_theme_can_be_chosen_from_command_search(page, word):
    page.keyboard.press("/")
    page.locator("#q").fill(word)
    expect(page.locator("#results")).to_contain_text(re.compile("ダーク|Dark"))
    page.locator("#results").get_by_text(re.compile("ダーク|Dark")).first.click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")


# FR-1047 AC-259 (異常系: 全色トークンが両テーマに値を持つ)
def test_ac259_every_color_token_has_a_value_in_both_themes(page):
    names = _tokens("--color-")
    for choice in ("light", "dark"):
        _theme(page, choice)
        empty = page.evaluate(
            "(n) => n.filter(x => !getComputedStyle(document.documentElement).getPropertyValue(x).trim())", names)
        assert not empty, f"{choice}: 値の無い色トークン {empty}"


# FR-1047 AC-261
def test_ac261_system_font_stack_no_remote_fonts_and_type_ramp(page):
    css = _css()
    assert "@font-face" not in css
    families = [v for _, k, v in _decls(css) if k in ("font-family", "--font-family-base") or k.startswith("--font-family")]
    assert families and all(f.replace('"', "").replace("'", "").lower().startswith("segoe ui variable") for f in families if "inherit" not in f and "var(" not in f)
    assert page.evaluate("getComputedStyle(document.body).fontFamily").replace('"', "").lower().startswith("segoe ui variable")
    assert page.evaluate("parseFloat(getComputedStyle(document.body).fontSize)") == P_BODY
    for route in NAV:
        _go(page, route)
        smallest = page.evaluate("""() => Math.min(...[...document.querySelectorAll('#view *, header *')]
            .filter(e => e.childNodes.length && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) && e.offsetParent)
            .map(e => parseFloat(getComputedStyle(e).fontSize)))""")
        assert smallest >= P_SMALL, f"{route}: {smallest}px の文字"
    sizes = [(s, k, v) for s, k, v in _decls(css) if k == "font-size" and not v.startswith(("var(", "inherit"))]
    assert not sizes, f"文字の大きさがトークン参照でない: {sizes[:5]}"


# FR-1047 AC-261 (異常系: 外部から書体を取得しない)
def test_ac261_no_external_font_requests(browser, studio_url):
    ctx = browser.new_context()
    page = ctx.new_page()
    external = []
    page.on("request", lambda r: external.append(r.url) if not r.url.startswith((studio_url, "data:", "blob:")) else None)
    page.goto(studio_url)
    page.wait_for_load_state("networkidle")
    fonts = [u for u in external] + [r for r in page.evaluate("performance.getEntriesByType('resource').map(e=>e.name)") if re.search(r"\.(woff2?|ttf|otf)", r)]
    assert not fonts
    ctx.close()


# FR-1047 AC-262
def test_ac262_spacing_size_radius_tokens_are_multiples_of_grid():
    bad = []
    for _, k, v in _decls(_css()):
        if k.startswith(("--space-", "--size-", "--radius-")):
            for num in re.findall(r"(-?\d*\.?\d+)px", v):
                if float(num) % P_GRID and float(num) not in (1, 2):
                    bad.append((k, v))
    assert not bad, bad


# FR-1047 AC-262 (異常系: 部品スタイルの直値も 4px の倍数かトークン)
def test_ac262_component_px_values_are_tokens_or_grid_multiples():
    props = re.compile(r"^(padding|margin|gap|width|height|min-width|min-height|max-width|border-radius|row-gap|column-gap)(-.+)?$")
    bad = []
    for sel, k, v in _decls(_css()):
        if k.startswith("--") or not props.match(k) or "var(" in v or "calc(" in v:
            continue
        for num in re.findall(r"(?<![\w.])(\d*\.?\d+)px", v):
            if float(num) % P_GRID and float(num) not in (1, 2):
                bad.append((sel, k, v))
    assert not bad, bad[:10]


# ---------------------------------------------------------------- FR-1048
# FR-1048 AC-263
def test_ac263_elevation_levels_and_same_kind_same_value_on_all_screens(page):
    shadows = {k for k in _tokens("--shadow-")}
    assert len(shadows) >= 3
    seen = {}
    for route in NAV:
        _go(page, route)
        got = page.evaluate("""() => Object.fromEntries(['button','input','.card','.panel'].map(s => {
            const e = document.querySelector('#view ' + s) || document.querySelector(s);
            if (!e) return [s, null]; const c = getComputedStyle(e);
            return [s, [c.borderRadius, c.boxShadow, c.borderTopWidth]]; }))""")
        for sel, val in got.items():
            if val is not None:
                assert seen.setdefault(sel, val) == val, f"{route}: {sel} が他画面と異なる {val} != {seen[sel]}"
    assert page.evaluate("""() => { const d = document.getElementById('drawer'), m = document.getElementById('view');
        return parseInt(getComputedStyle(d).zIndex || 0) > parseInt(getComputedStyle(m).zIndex || 0) }"""), "ドロワーが本体より上でない"


# FR-1048 AC-264
def test_ac264_interactive_states_defined_and_selection_not_color_only(page):
    css = _css()
    for pseudo in (":hover", ":active", ":focus-visible", r":disabled|\[aria-disabled"):
        assert re.search(pseudo, css), f"{pseudo} のスタイルが無い"
    _go(page, "dashboard")
    diff = page.evaluate("""() => { const on = document.querySelector('#nav a[aria-current="page"]'),
        off = document.querySelector('#nav a:not([aria-current])'); const a = getComputedStyle(on), b = getComputedStyle(off);
        return ['fontWeight','textDecorationLine','borderBottomWidth','borderBottomStyle','outlineWidth','boxShadow'].filter(p => a[p] !== b[p]) }""")
    assert diff, "選択中のナビ項目が色以外で識別できない"


# FR-1048 AC-264 (異常系: 無効は色以外でも識別)
def test_ac264_disabled_is_not_color_only():
    non_color = {"border-style", "text-decoration", "text-decoration-line", "font-style", "outline", "box-shadow", "background-image", "border-width", "opacity"}
    rules = [(s, k) for s, k, _ in _decls(_css()) if re.search(r":disabled|\[aria-disabled|\[disabled", s) and k in non_color]
    assert rules, "無効の見た目が色以外で定義されていない"


# FR-1048 AC-265
def test_ac265_motion_uses_tokens_within_limit_and_no_endless_animation(page):
    for k in _tokens("--duration-"):
        v = page.evaluate("(k) => getComputedStyle(document.documentElement).getPropertyValue(k).trim()", k)
        ms = float(v[:-2]) if v.endswith("ms") else float(v[:-1]) * 1000
        assert ms <= P_MOTION, f"{k}={v}"
    raw = [(s, k, v) for s, k, v in _decls(_css()) if k in ("transition", "transition-duration", "animation", "animation-duration")
           and not k.startswith("--") and re.search(r"\d(ms|s)\b", re.sub(r"var\([^)]*\)", "", v))]
    assert not raw, f"モーショントークン以外の長さ: {raw[:5]}"
    for route in NAV:
        _go(page, route)
        endless = page.evaluate("""() => document.getAnimations().filter(a => a.effect.getComputedTiming().iterations === Infinity)
            .map(a => a.effect.target && a.effect.target.closest('[role=progressbar],progress,[data-state=loading],[aria-busy=true]') ? null : a.effect.target.tagName).filter(Boolean)""")
        assert not endless, f"{route}: 進行中表示以外の繰り返しアニメ {endless}"


# FR-1048 AC-266
def test_ac266_layers_fall_back_to_opaque_with_readable_text(browser, studio_url):
    css = _css()
    assert re.search(r"prefers-reduced-transparency|@supports not \(.*backdrop-filter", css)
    ctx = browser.new_context(forced_colors="active")
    page = ctx.new_page()
    page.goto(studio_url)
    page.wait_for_load_state("networkidle")
    for sel in ("header.top", "#nav", "#drawer", "main#view"):
        bg, fg = page.evaluate("""(s) => { const e = document.querySelector(s); const c = getComputedStyle(e);
            return [c.backgroundColor, c.color] }""", sel)
        nums = [float(x) for x in re.findall(r"[\d.]+", bg)]
        assert len(nums) == 3 or nums[3] == 1, f"{sel}: 背景が不透明でない {bg}"
        if sel != "#nav":
            # 強制色では system color が使われる。計算済みの色（used value）を直接読み、トークン経由の再解決はしない
            assert _ratio([float(x) for x in re.findall(r"[\d.]+", bg)][:3], [float(x) for x in re.findall(r"[\d.]+", fg)][:3]) >= P_TEXT, sel
    ctx.close()


# FR-1048 AC-267
@pytest.mark.parametrize("route", NAV)
def test_ac267_error_state_has_common_structure_and_keeps_input(browser, studio_url, route):
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(studio_url)
    page.wait_for_load_state("networkidle")
    page.locator("#q").fill("FR-001")
    page.route("**/api/model", lambda r: r.abort())
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    _go(page, route)
    panel = page.locator('[data-testid="state-panel"][data-state="error"]')
    expect(panel.first).to_be_visible()
    for part in ("icon", "heading", "description", "action"):
        expect(panel.first.locator(f'[data-part="{part}"]')).to_have_count(1)
    assert panel.first.locator('[data-part="description"]').inner_text().strip()
    assert page.locator("#q").input_value() == "FR-001"
    ctx.close()


# FR-1048 AC-267 (空: データ層はあるが対象が 0 件になる条件＝一致しない検索。データ層の無いリポジトリは Studio が起動を拒否する)
@pytest.mark.parametrize("route", NAV)
def test_ac267_empty_state_has_common_structure_and_text(studio_url, browser, route):
    page = browser.new_context().new_page()
    page.goto(studio_url)
    page.wait_for_load_state("networkidle")
    page.locator("#q").fill("zzzz-no-such-item-0000")
    _go(page, route)
    panel = page.locator('[data-testid="state-panel"]').first
    expect(panel).to_be_visible()
    assert panel.get_attribute("data-state") in ("empty", "stale", "error")
    for part in ("icon", "heading", "description", "action"):
        expect(panel.locator(f'[data-part="{part}"]')).to_have_count(1)
    page.context.close()


# FR-1048 AC-267
def test_ac267_loading_state_shows_progress_indicator(browser, studio_url):
    page = browser.new_context().new_page()
    page.route("**/api/model", lambda r: page.wait_for_timeout(1500) or r.continue_())
    page.goto(studio_url)
    loading = page.locator('[data-testid="state-panel"][data-state="loading"]').first
    expect(loading).to_be_visible()
    expect(loading.locator('[role="progressbar"],progress,[aria-busy="true"]').first).to_be_attached()
    assert loading.inner_text().strip()
    page.context.close()


# FR-1048 AC-268
def test_ac268_single_bundled_icon_set_allowed_sizes_and_accessible_names(page):
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"(src|href)=\"https?://", html)
    for route in NAV + ["map2d", "map3d"]:
        _go(page, route)
        # アイコン = svg.icon / svg[data-icon] / [data-part=icon] 内の svg（仮置き契約）。それ以外の svg はチャート等で、
        # 最大アイコンサイズより大きくなければならない（小さい無印 svg はアイコンの取りこぼしとして失敗）
        bad = page.evaluate("""(sizes) => [...document.querySelectorAll('svg')].filter(s => s.getBoundingClientRect().width && !s.closest('.brand')).flatMap(s => {
            const isIcon = s.matches('.icon, [data-icon]') || !!s.closest('[data-part="icon"]');
            if (!isIcon) { const q = s.getBoundingClientRect(); return Math.min(q.width, q.height) > Math.max(...sizes) ? [] : ['unmarked small svg ' + q.width + 'x' + q.height + ' ' + s.parentElement.outerHTML.slice(0, 60)]; }
            const r = s.getBoundingClientRect(), out = [];
            if (!sizes.includes(Math.round(r.width)) || !sizes.includes(Math.round(r.height))) out.push('size ' + r.width + 'x' + r.height);
            const named = s.getAttribute('aria-label') || s.querySelector('title') || (s.parentElement.innerText || '').trim() || s.closest('[aria-label],[title]');
            const hidden = s.getAttribute('aria-hidden') === 'true';
            if (!named && !hidden) out.push('unnamed'); return out.map(m => m + ' ' + s.parentElement.outerHTML.slice(0, 60)); })""", sorted(ICON_SIZES))
        assert not bad, f"{route}: {bad[:5]}"


# FR-1048 AC-268 (FR-1040 の切替アイコン)
def test_ac268_dim_toggle_icons_follow_rule(page):
    _go(page, "map2d")
    icons = page.locator('[data-testid="dim-toggle"] svg')
    assert icons.count() >= 1
    for i in range(icons.count()):
        w = icons.nth(i).evaluate("e => Math.round(e.getBoundingClientRect().width)")
        assert w in ICON_SIZES
    for b in page.locator('[data-testid="dim-toggle"] button').all():
        assert b.get_attribute("aria-label") or b.inner_text().strip()


# ---------------------------------------------------------------- NFR-A11Y-001
# NFR-A11Y-001 AC-269
@pytest.mark.parametrize("choice", ["light", "dark"])
def test_ac269_token_contrast_ratios_meet_wcag_aa_and_are_reported(page, choice, capsys):
    _theme(page, choice)
    toks = _tokens("--color-")
    fg = [t for t in toks if t.startswith("--color-fg-") and "disabled" not in t]
    bg = [t for t in toks if t.startswith("--color-bg-")]
    nontext = [t for t in toks if t.startswith(("--color-border-strong", "--color-focus")) or t.endswith("-icon")]
    assert fg and bg and nontext
    fails, report = [], []
    for f in fg:
        for b in bg:
            r = _ratio(_rgb(page, f), _rgb(page, b))
            report.append((choice, f, b, round(r, 2)))
            if r < P_TEXT:
                fails.append((f, b, round(r, 2)))
    for n in nontext:
        for b in bg:
            r = _ratio(_rgb(page, n), _rgb(page, b))
            report.append((choice, n, b, round(r, 2)))
            if r < P_NONTEXT:
                fails.append((n, b, round(r, 2)))
    for row in report:
        print("contrast", *row)
    for s in ("success", "warning", "danger", "info"):
        r = _ratio(_rgb(page, f"--color-status-{s}-fg"), _rgb(page, f"--color-status-{s}-bg"))
        print("contrast status", choice, s, round(r, 2))
        assert r >= P_TEXT, f"{choice} {s}: {r:.2f}"
    assert not fails, fails[:10]


# NFR-A11Y-001 AC-270
def test_ac270_focus_visible_on_keyboard_not_on_mouse_and_no_bare_outline_none(page):
    bare = [(s, v) for s, k, v in _decls(_css()) if k == "outline" and re.fullmatch(r"(none|0)", v) and ":focus-visible" not in s
            and not re.search(r":focus:not\(:focus-visible\)|:focus-within", s)]
    assert not bare, f"代替なしの outline:none {bare[:5]}"
    for route in NAV:
        _go(page, route)
        page.locator("body").click(position={"x": 1, "y": 1})
        seen = 0
        for _ in range(12):
            page.keyboard.press("Tab")
            info = page.evaluate("""() => { const e = document.activeElement; if (!e || e === document.body) return null;
                const c = getComputedStyle(e); const r = e.getBoundingClientRect();
                const top = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
                return { vis: e.matches(':focus-visible'), ring: (c.outlineStyle !== 'none' && parseFloat(c.outlineWidth) > 0) || c.boxShadow !== 'none',
                         covered: !(top && (top === e || e.contains(top))), w: Math.max(parseFloat(c.outlineWidth) || 0, 0) } }""")
            if info is None:
                continue
            seen += 1
            assert info["vis"] and info["ring"], f"{route}: キーボードでフォーカス表示が無い {info}"
        assert seen >= 3, f"{route}: キーボードで到達できる部品が少ない"
    _go(page, "dashboard")
    page.locator("#nav a").first.click()
    assert not page.evaluate("document.activeElement.matches(':focus-visible')"), "マウスでフォーカス表示が出た"


# NFR-A11Y-001 AC-270 (フォーカス表示の色は背景に 3:1)
@pytest.mark.parametrize("choice", ["light", "dark"])
def test_ac270_focus_ring_contrast_against_background(page, choice):
    _theme(page, choice)
    page.keyboard.press("Tab")
    r = page.evaluate("""() => { const c = getComputedStyle(document.activeElement); return [c.outlineColor, getComputedStyle(document.body).backgroundColor] }""")
    assert _ratio(_rgb(page, r[0]), _rgb(page, r[1])) >= P_NONTEXT


# NFR-A11Y-001 AC-271
def test_ac271_forced_colors_defined_and_state_visible(browser, studio_url):
    assert re.search(r"@media[^{]*forced-colors:\s*active", _css())
    ctx = browser.new_context(forced_colors="active")
    page = ctx.new_page()
    page.goto(studio_url)
    page.wait_for_load_state("networkidle")
    diff = page.evaluate("""() => { const on = document.querySelector('#nav a[aria-current="page"]'), off = document.querySelector('#nav a:not([aria-current])');
        const a = getComputedStyle(on), b = getComputedStyle(off);
        return ['borderBottomWidth','borderTopWidth','outlineWidth','textDecorationLine','fontWeight','backgroundColor','color'].filter(p => a[p] !== b[p]) }""")
    assert diff, "強制色で選択が識別できない"
    assert page.evaluate("""() => [...document.querySelectorAll('.bg, .bg *')].every(e => getComputedStyle(e).display === 'none' || getComputedStyle(e).backgroundImage === 'none')""")
    ctx.close()


# NFR-A11Y-001 AC-272
def test_ac272_reduced_motion_stops_animations_on_all_screens(browser, studio_url):
    ctx = browser.new_context(reduced_motion="reduce")
    page = ctx.new_page()
    page.goto(studio_url)
    page.wait_for_load_state("networkidle")
    for route in NAV:
        _go(page, route)
        bad = page.evaluate("""(lim) => [...document.querySelectorAll('*')].filter(e => { const c = getComputedStyle(e);
            const d = (s) => Math.max(...s.split(',').map(x => parseFloat(x) * (x.trim().endsWith('ms') ? 1 : 1000)));
            return d(c.transitionDuration) > lim || (c.animationName !== 'none' && d(c.animationDuration) > lim) || c.scrollBehavior === 'smooth'; })
            .slice(0, 5).map(e => e.tagName + '.' + e.className)""", P_RM)
        assert not bad, f"{route}: 動きが残る {bad}"
    _go(page, "dashboard")
    assert page.locator("body").inner_text().strip()
    ctx.close()


# NFR-A11Y-001 AC-272 (進行中表示は文言でも伝わる)
def test_ac272_loading_is_conveyed_without_motion(browser, studio_url):
    ctx = browser.new_context(reduced_motion="reduce")
    page = ctx.new_page()
    page.route("**/api/model", lambda r: page.wait_for_timeout(1000) or r.continue_())
    page.goto(studio_url)
    loading = page.locator('[data-testid="state-panel"][data-state="loading"]').first
    expect(loading).to_be_visible()
    assert loading.inner_text().strip()
    assert page.evaluate("document.getAnimations().length") == 0
    ctx.close()


# NFR-A11Y-001 AC-273
def test_ac273_pointer_target_size_at_least_24px(page):
    for route in NAV:
        _go(page, route)
        small = page.evaluate("""(m) => [...document.querySelectorAll('button, [role=button], input, select, header a, #nav a, [role=tab]')]
            .filter(e => e.offsetParent && !e.closest('p')).map(e => [e, e.getBoundingClientRect()])
            .filter(([e, r]) => (r.width < m || r.height < m)).map(([e]) => e.outerHTML.slice(0, 70))""", P_TARGET)
        assert not small, f"{route}: {small[:5]}"


# NFR-A11Y-001 AC-273 (異常系: 320px 幅と文字 200% で欠けず・横スクロールなし)
@pytest.mark.parametrize("route", NAV)
@pytest.mark.parametrize("zoom", ["reflow", "text200"])
def test_ac273_reflow_and_text_zoom_without_horizontal_scroll(browser, studio_url, route, zoom):
    page = browser.new_context(viewport={"width": P_REFLOW, "height": 800} if zoom == "reflow" else {"width": 1280, "height": 800}).new_page()
    page.goto(studio_url + f"/#/{route}")
    page.wait_for_load_state("networkidle")
    if zoom == "text200":
        page.evaluate("document.documentElement.style.fontSize = '200%'")
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), "横スクロールが要る"
    expect(page.locator('[data-testid="theme-toggle"]')).to_be_attached()
    _theme_btn = page.locator('[data-testid="theme-toggle"] [data-theme-choice]').first
    _theme_btn.scroll_into_view_if_needed()
    expect(_theme_btn).to_be_visible()
    page.context.close()


# NFR-A11Y-001 AC-274
def test_ac274_theme_toggle_keyboard_reachable_with_name_role_state_and_announced(page):
    reached = False
    for _ in range(40):
        page.keyboard.press("Tab")
        if page.evaluate("!!document.activeElement.closest('[data-testid=\"theme-toggle\"]')"):
            reached = True
            break
    assert reached, "キーボードだけでテーマ切替に到達できない"
    for b in page.locator('[data-testid="theme-toggle"] [data-theme-choice]').all():
        assert (b.get_attribute("aria-label") or b.inner_text()).strip()
        assert b.get_attribute("aria-pressed") in ("true", "false") or b.get_attribute("role") == "radio"
    page.locator('[data-testid="theme-toggle"] [data-theme-choice="dark"]').click()
    dark = page.locator('[data-testid="theme-toggle"] [data-theme-choice="dark"]')
    for _ in range(20):  # 状態反映の待ち（最大約 2 秒）
        if "true" in (dark.get_attribute("aria-pressed"), dark.get_attribute("aria-checked")):
            break
        page.wait_for_timeout(100)
    assert "true" in (dark.get_attribute("aria-pressed"), dark.get_attribute("aria-checked")), \
        "選択後に aria-pressed / aria-checked のどちらも true にならない"
    live = page.locator('[role="status"], [aria-live]:not([aria-live="off"])')
    expect(live.first).to_be_attached()


# NFR-A11Y-001 AC-274 (異常系: 状態は色だけで示さない)
@pytest.mark.parametrize("choice", ["light", "dark"])
def test_ac274_states_not_conveyed_by_color_alone(browser, studio_url, choice):
    page = browser.new_context().new_page()
    page.route("**/api/model", lambda r: r.abort())
    page.goto(studio_url)
    page.wait_for_load_state("networkidle")
    _theme(page, choice)
    panel = page.locator('[data-testid="state-panel"]').first
    expect(panel).to_be_visible()
    assert panel.locator('[data-part="heading"]').inner_text().strip()
    assert panel.locator('[data-part="icon"]').count() == 1
    assert panel.get_attribute("role") in ("alert", "status") or panel.locator("[role=alert],[role=status]").count() >= 1
    page.context.close()


# ---------------------------------------------------------------- NFR-PERF-006
def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout


# NFR-PERF-006 AC-275
def test_ac275_nav_items_and_legacy_urls_identical_to_baseline_commit(page):
    base_app = _git("show", f"{BASE}:EABK-Studio/web/js/app.js")
    base_nav = re.search(r"const NAV = \[([^\]]*)\]", base_app).group(1)
    base_nav = re.findall(r"'([^']+)'", base_nav)
    assert base_nav == NAV
    now = page.evaluate("[...document.querySelectorAll('#nav a')].map(a => a.dataset.nav)")
    assert now == base_nav
    for legacy in ("map2d", "map3d", "placement"):
        _go(page, legacy)
        assert page.locator("#view").inner_text().strip()
        assert not re.search(r"見つかりません|not found|Traceback", page.locator("#view").inner_text(), re.I)


# NFR-PERF-006 AC-275
def test_ac275_screen_manifest_ids_unchanged_and_baseline_tests_untouched():
    name = "users-guide/studio/screen-images.json"
    base = json.loads(_git("show", f"{BASE}:{name}"))
    now = json.loads((ROOT / name).read_text(encoding="utf-8"))
    assert [s["id"] if "id" in s else s.get("screen") for s in now["screens"]] == [s["id"] if "id" in s else s.get("screen") for s in base["screens"]]
    # 追加（A）と台帳 ledger.json の正規の更新は許す。既存テストファイルの変更・削除・改名は許さない
    changed = [l for l in _git("diff", "--name-status", BASE, "--", "tests/system").splitlines()
               if not l.startswith("A") and not l.rstrip().endswith("tests/system/ledger.json")]
    assert not changed, f"基準 commit からの既存 System Test の変更・削除: {changed}"


# NFR-PERF-006 AC-275 (異常系: コンソールエラー・外部通信・リポジトリ変更なし)
def test_ac275_no_console_errors_no_external_requests_and_repo_untouched(browser, studio_url):
    before_m, before_r = _management_fingerprints(), _repository_files()
    page = browser.new_context().new_page()
    errors, external = [], []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("request", lambda r: external.append(r.url) if not r.url.startswith((studio_url, "data:", "blob:")) else None)
    page.goto(studio_url)
    page.wait_for_load_state("networkidle")
    for route in NAV + ["map2d", "map3d", "placement"]:
        _go(page, route)
    for choice in ("light", "dark", "system"):
        _theme(page, choice)
    assert not errors, errors[:5]
    assert not external, external[:5]
    assert _management_fingerprints() == before_m
    assert _repository_files() == before_r
    page.context.close()


def _p95(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(0.95 * len(xs) + 0.5)) - 1)]


def _measure(browser, url, n):
    first, zoom, select = [], [], []
    for _ in range(n):
        page = browser.new_context(viewport={"width": 1400, "height": 900}).new_page()
        t0 = time.perf_counter()
        page.goto(f"{url}/#/map2d")
        page.wait_for_selector('[data-testid="semantic-zoom"][data-ready="true"]', timeout=30000)
        first.append((time.perf_counter() - t0) * 1000)
        for scale in (0.5, 2.0):
            ms = page.evaluate("""async (s) => { const t = performance.now(); window.eabkView.setScale(s);
                await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); return performance.now() - t }""", scale)
            zoom.append(ms)
        ent = page.locator("[data-entity]").first
        if ent.count():
            ms = page.evaluate("""async () => { const e = document.querySelector('[data-entity]'); const t = performance.now(); e.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); return performance.now() - t }""")
            select.append(ms)
        page.context.close()
    return {"first_display": first, "zoom": zoom, "select": select}


# NFR-PERF-006 AC-276
def test_ac276_render_p95_within_tolerance_of_baseline_and_absolute_limits(browser, large_url):
    if os.environ.get("EABK_RECORD_PERF_BASELINE") == "1":
        out = ROOT / "work" / "runs" / "202610171403" / "evidence" / "perf-baseline-80c7cc55.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        env = {"commit": subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], cwd=ROOT, capture_output=True,
                                        text=True).stdout.strip(), "platform": platform.platform(),
               "python": platform.python_version(), "n": P_N, "viewport": "1400x900", "dataset": "make_large"}
        out.write_text(json.dumps({"env": env, "samples": _measure(browser, large_url, P_N)}), encoding="utf-8")
        return
    files = list((ROOT / "work").glob("**/evidence/perf-baseline-80c7cc55.json"))
    assert files, "基準 commit 80c7cc55 の測定値（evidence）が無い。実装前に測って残す"
    base = json.loads(files[0].read_text(encoding="utf-8"))
    assert base.get("env"), "測定環境が記録されていない"
    for op, xs in base["samples"].items():
        assert len(xs) >= P_N, f"基準の {op} の回数が {len(xs)} < PARAM-038"
    now = _measure(browser, large_url, P_N)
    print("env", base["env"])
    for op, xs in now.items():
        p, b = _p95(xs), _p95(base["samples"][op])
        print("p95", op, "now", round(p, 1), "baseline", round(b, 1))
        assert p <= b * P_TOL, f"{op}: {p:.1f} > {b:.1f} × {P_TOL}"
    # 絶対値（PARAM-021・022）は参考の目標で非必須（AC-276）。超過しても fail にせず記録のみ。
    ref = {"zoom_over_PARAM-021": _p95(now["zoom"]) > P_ZOOM_MS, "select_over_PARAM-021": _p95(now["select"]) > P_ZOOM_MS,
           "first_display_over_PARAM-022": _p95(now["first_display"]) > P_FIRST_S * 1000}
    print("reference-only absolute limits exceeded:", ref)
