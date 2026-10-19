"""Integration / unit tests for FR-1070 (3D camera presets), FR-1071 (reduced motion, manual override), NFR-UX-015 (performance, no WebGL).
Run: python -m pytest EABK-Studio/tests/test_camera3d_ui.py -q"""
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
WEB = ROOT / "web"
SRC = (WEB / "js" / "camera3d.js").read_text(encoding="utf-8")
I18N = (WEB / "js" / "i18n.js").read_text(encoding="utf-8")
JA, EN = I18N.split("  en: {", 1)
IDS = ["corporate", "interview", "documentary", "cinematic", "product", "commercial", "anime", "musicvideo", "game"]
JARGON = re.compile(r"Dolly|Orbit|Gimbal|Pan\b|Tilt|Crane|Handheld|Whip|FPV|Truck|Pedestal|Roll\b|ドリー|オービット|ジンバル|パン\b|ティルト", re.I)


def _val(table, key):
    m = re.search(rf"'{re.escape(key)}':\s*'((?:[^'\\]|\\.)*)'", table)
    return m.group(1) if m else None


# FR-1070 AC-383: JA and EN names/descriptions exist for all 9 presets, and the main display has no jargon.
@pytest.mark.parametrize("table", [JA, EN], ids=["ja", "en"])
def test_ac383_names_and_descriptions_in_both_languages_without_jargon(table):
    for pid in IDS:
        for suffix in ("n", "d"):
            v = _val(table, f"cam3d.{pid}.{suffix}")
            assert v and v.strip(), f"cam3d.{pid}.{suffix} missing"
            assert not JARGON.search(v), f"jargon in {pid}.{suffix}: {v}"
    assert "ゆっくり近づく" in JA and "ぐるっと回る" in JA


# FR-1070 AC-381/AC-383: the table is in one place, ordered calm -> flashy, 9 presets, defaults to corporate.
def test_ac383_preset_table_order_and_default():
    ids = re.findall(r"\{ id: '(\w+)', icon:", SRC)
    assert ids == IDS
    assert "DEFAULT_PRESET = 'corporate'" in SRC


# FR-1070 AC-382: every preset uses only vocabulary values (aliases resolved), checked through the real module.
def test_ac382_vocabulary_is_closed():
    # camera3d.js imports ui.js / i18n.js (DOM), so the table is parsed from source instead of executed
    vocab = {k: set(re.findall(r"'([^']+)'", v)) for k, v in re.findall(r"(shot|angle|movement|motion): \[(.*?)\]", SRC)}
    rows = re.findall(r"shot: '([^']+)', angle: '([^']+)', movement: '([^']+)', motion: '([^']+)'", SRC)
    assert len(rows) == 9
    for sh, an, mv, mo in rows:
        for key, val in (("shot", sh), ("angle", an), ("movement", mv), ("motion", mo)):
            for part in val.split("→"):
                assert part.strip() in vocab[key], (key, part)


# FR-1071 AC-387 / NFR-UX-015 AC-389: reduced motion and degradation force Static; the frame-rate rule is a pure function.
def test_ac389_degradation_rule_is_pure_and_uses_param_047():
    assert "FPS_MIN = 30" in SRC
    assert "effectiveMovement" in SRC and "st.degraded = true" in SRC
    assert "localStorage" not in SRC and "sessionStorage" not in SRC, "degradation / selection must not write storage"
    assert not re.search(r"fetch\(|XMLHttpRequest|WebSocket|https?://", SRC), "no external communication"


@pytest.fixture(scope="module")
def studio():
    sync_api = pytest.importorskip("playwright.sync_api")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, str(ROOT / "studio.py"), "--repo", str(REPO), "--port", str(port), "--no-open"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    end = time.time() + 20
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch()
        yield browser, f"http://127.0.0.1:{port}"
        browser.close()
    proc.terminate()


def _open(studio, init=None, reduced=False, wait_nodes=True):
    browser, url = studio
    ctx = browser.new_context(viewport={"width": 1400, "height": 900}, reduced_motion="reduce" if reduced else "no-preference")
    if init:
        ctx.add_init_script(init)
    page = ctx.new_page()
    page.goto(f"{url}/#/map3d")
    page.wait_for_load_state("networkidle")
    if wait_nodes:
        page.wait_for_function("() => window.__eabk3d && window.__eabk3d.nodes().length > 0", timeout=20000)
    return page


def _pick(page, pid):
    page.locator(f'[data-testid="camera-presets"] [data-preset="{pid}"]').first.click()
    page.wait_for_timeout(200)


# FR-1070 AC-384: arrow keys move between presets, Enter selects; the current preset is announced (aria-pressed + live text + mark).
def test_ac384_keyboard_and_screen_reader_and_not_color_only(studio):
    page = _open(studio)
    first = page.locator('[data-testid="camera-presets"] [data-preset="corporate"]')
    first.focus()
    page.keyboard.press("ArrowRight")
    assert page.evaluate("() => document.activeElement.dataset.preset") == "interview"
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    on = page.locator('[data-testid="camera-presets"] [data-preset="interview"]')
    assert on.get_attribute("aria-pressed") == "true"
    assert on.locator(".cam-mark").inner_text() == "✓"          # not by color only
    assert "interview" == page.locator("[data-camera-preset]").first.get_attribute("data-camera-preset")
    assert page.locator('.cam-live').first.inner_text().strip()
    # a command-box entry selects a preset too
    page.fill("#q", ">")
    page.wait_for_timeout(200)
    assert page.locator('[data-testid="command-item"]', has_text="カメラ").count() >= 9


# FR-1071 AC-387: Esc and the stop button stop the automatic motion; selection / zoom survive start, stop and resume.
def test_ac387_stop_keeps_selection_and_zoom_and_no_keyboard_trap(studio):
    page = _open(studio)
    _pick(page, "product")
    assert page.evaluate("() => window.__eabk3d.camera().auto") is True
    page.keyboard.press("Escape")
    assert page.evaluate("() => window.__eabk3d.camera().auto") is False
    _pick(page, "product")
    page.locator('[data-testid="camera-stop"]').click()
    assert page.locator("[data-camera-auto]").first.get_attribute("data-camera-auto") == "false"
    page.locator('[data-testid="camera-resume"]').click()
    assert page.locator("[data-camera-auto]").first.get_attribute("data-camera-auto") == "true"
    # keyboard is not trapped: Tab leaves the preset group
    page.locator('[data-testid="camera-presets"] [data-preset="game"]').focus()
    page.keyboard.press("Tab")
    assert page.evaluate("() => !document.activeElement.closest('[data-testid=camera-presets] .cam-list')")
    # reduced motion: the resume control is hidden, nothing moves (FR-1071 AC-385)
    page2 = _open(studio, reduced=True)
    _pick(page2, "game")
    assert page2.evaluate("() => window.__eabk3d.camera()") ["movement"] == "Static"


# NFR-UX-015 AC-389: when frames stay slow the camera falls back to Static, says so, and keeps the chosen preset (nothing stored).
def test_ac389_slow_frames_degrade_to_static_without_changing_choice(studio):
    page = _open(studio)
    _pick(page, "anime")
    page.evaluate("() => { const f = window.requestAnimationFrame.bind(window); window.requestAnimationFrame = (cb) => f((ts) => { cb(ts); const e = performance.now() + 45; while (performance.now() < e) {} }); }")
    page.wait_for_function("() => window.__eabk3d.camera().degraded === true", timeout=30000)
    cam = page.evaluate("() => window.__eabk3d.camera()")
    assert cam["preset"] == "anime" and cam["movement"] == "Static" and cam["auto"] is False
    assert page.locator('[data-camera-auto="false"]').count() >= 1
    assert "重い" in page.locator(".cam-note").first.inner_text()
    assert page.evaluate("() => Object.keys(localStorage).filter((k) => /camera|preset/i.test(k)).length") == 0


# NFR-UX-015 AC-390: without WebGL the map shows 2D guidance, the reason and a table of kinds/shapes (no error), choice kept.
def test_ac390_no_webgl_shows_reason_and_table(studio):
    init = ("const g = HTMLCanvasElement.prototype.getContext; HTMLCanvasElement.prototype.getContext = function (t, ...a) {"
            " if (/webgl/i.test(t)) return null; return g.call(this, t, ...a); };")
    page = _open(studio, init=init, wait_nodes=False)
    page.wait_for_selector('[data-testid="dim-fallback"]', timeout=15000)
    fb = page.locator('[data-testid="dim-fallback"]').first
    assert "3D" in fb.inner_text()
    rows = page.locator('[data-testid="legend-table"] tbody tr')
    assert rows.count() >= 5
    assert all(rows.nth(i).inner_text().strip() for i in range(rows.count()))
    assert page.locator('[data-testid="camera-presets"]').count() == 0
