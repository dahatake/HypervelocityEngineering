"""Integration / unit tests for FR-1068 (3D object per kind + legend) and FR-1069 (3D style toggle).
Run: python -m pytest EABK-Studio/tests/test_obj3d_ui.py -q"""
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
SRC = (WEB / "js" / "shapes3d.js").read_text(encoding="utf-8")
I18N = (WEB / "js" / "i18n.js").read_text(encoding="utf-8")


def _shape_table():
    body = re.search(r"export const SHAPE_OF = Object\.freeze\(\{(.*?)\}\);", SRC, re.S).group(1)
    return dict(re.findall(r"(\w+):\s*'(\w+)'", body))


# FR-1068 AC-374: the kind -> shape table is defined in exactly one place and gives different shapes to different kinds.
def test_ac374_shape_table_is_single_and_distinguishes_main_kinds():
    table = _shape_table()
    main = ["goal", "req", "ac", "entity", "part", "api", "table", "param", "question", "file", "case", "screen", "module", "state"]
    shapes = [table[k] for k in main]
    assert len(set(shapes)) == len(shapes), "main kinds must not share a shape"
    assert "default" not in shapes
    for name in ("map3d.js", "dgm3d.js", "sz3d.js", "maptiers.js"):
        assert "SHAPE_OF" not in (WEB / "js" / name).read_text(encoding="utf-8"), f"{name} must use shapeOf() not a second table"
    # shape examples from the requirement: data = cylinder DB, API = gate, screen = display plate, requirement = scroll, state = signal
    assert (table["table"], table["api"], table["screen"], table["req"], table["state"]) == ("database", "gate", "display", "scroll", "signal")


# FR-1068 AC-374: every shape has parts built from three.js standard geometries only (no external model / texture / font).
def test_ac374_every_shape_has_parts_and_no_external_assets():
    shapes = set(_shape_table().values()) | {"default"}
    parts = re.search(r"export const SHAPE_PARTS = \{(.*?)\n\};", SRC, re.S).group(1)
    for s in shapes:
        assert re.search(rf"\b{s}:\s*\[", parts), f"no parts for shape {s}"
    assert not re.search(r"GLTFLoader|OBJLoader|FontLoader|TextureLoader|fetch\(|\.glb|\.gltf|\.png|\.jpg", SRC)


# FR-1068 AC-376: kind names, shape words, legend and style words exist in JA and EN.
def test_ac376_words_exist_in_ja_and_en():
    ja, en = I18N.split("  en: {", 1)
    keys = ["legend3d.title", "style3d.label", "style3d.engineering", "style3d.entertainment", "shape3d.other", "shape3d.default"]
    keys += [f"shape3d.{s}" for s in set(_shape_table().values())] + [f"type.{k}" for k in _shape_table() if k not in ("nfr", "test")]
    for k in keys:
        assert f"'{k}'" in ja, f"{k} missing in ja"
        assert f"'{k}'" in en, f"{k} missing in en"


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


def _open(studio, lang=None, init=None, reduced=False):
    browser, url = studio
    ctx = browser.new_context(viewport={"width": 1400, "height": 900}, reduced_motion="reduce" if reduced else "no-preference")
    if init:
        ctx.add_init_script(init)
    page = ctx.new_page()
    page.goto(f"{url}/#/map3d")
    page.wait_for_load_state("networkidle")
    if lang:
        page.evaluate("l => localStorage.setItem('eabk-studio.lang', l)", lang)
        page.reload()
        page.wait_for_load_state("networkidle")
    page.wait_for_function("() => window.__eabk3d && window.__eabk3d.nodes().length > 0", timeout=20000)
    return page


# FR-1068 AC-376: JA and EN legends show a word per kind (not color only); rows are keyboard reachable and select the kind.
@pytest.mark.parametrize("lang,other", [(None, "その他"), ("en", "Other")])
def test_ac376_legend_rows_have_words_shapes_and_keyboard_focus(studio, lang, other):
    page = _open(studio, lang)
    rows = page.locator('[data-testid="legend-3d"] [data-kind]')
    assert rows.count() >= 2
    for i in range(rows.count()):
        r = rows.nth(i)
        assert r.locator(".lg-name").inner_text().strip() and r.locator(".lg-shape").inner_text().strip()
        assert r.locator("svg[data-shape]").count() == 1
    first = rows.first
    first.focus()
    page.keyboard.press("Enter")
    assert page.locator('[data-testid="legend-3d"] [data-kind][aria-pressed="true"]').count() == 1
    page.keyboard.press("Enter")
    assert page.locator('[data-testid="legend-3d"] [aria-pressed="true"]').count() == 0
    page.context.close()


# FR-1068 AC-377: an unknown kind gets the default shape and is listed as "Other" (JA and EN), without an error.
@pytest.mark.parametrize("lang,other", [(None, "その他"), ("en", "Other")])
def test_ac377_unknown_kind_uses_default_shape_and_other_label(studio, lang, other):
    page = _open(studio, lang)
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    got = page.evaluate("""async () => { const m = await import('/js/shapes3d.js');
      const leg = m.buildLegend([{ kind: 'zzz-unknown', color: '#888', count: 2 }]);
      return { shape: m.shapeOf('zzz-unknown'), known: m.isKnownKind('zzz-unknown'), row: leg.querySelector('[data-kind]').dataset.kind,
               svg: leg.querySelector('svg').dataset.shape, name: leg.querySelector('.lg-name').textContent }; }""")
    assert got == {"shape": "default", "known": False, "row": "zzz-unknown", "svg": "default", "name": other}
    assert not errs
    page.context.close()


# FR-1069 AC-380: the chosen style survives a reload, only the style name is stored, and switching keeps content and camera.
def test_ac380_style_persists_stores_only_name_and_keeps_state(studio):
    page = _open(studio, reduced=True)   # 自動回転なし・初回の飛行が終わってから比べる
    page.wait_for_timeout(3000)
    before = page.evaluate("() => JSON.stringify(window.eabkView.getState().map3d.points.map(p => [p.id, Math.round(p.x), Math.round(p.y)]))")
    page.locator('[data-testid="style-toggle"] [data-style-value="entertainment"]').click()
    after = page.evaluate("() => JSON.stringify(window.eabkView.getState().map3d.points.map(p => [p.id, Math.round(p.x), Math.round(p.y)]))")
    assert after == before, "switching style must not move the camera or rebuild the scene"
    stored = page.evaluate("() => Object.entries(localStorage).filter(([k]) => /style3d/.test(k))")
    assert stored == [["eabk-studio.style3d", "entertainment"]]
    page.reload()
    page.wait_for_function("() => window.__eabk3d && window.__eabk3d.nodes().length > 0", timeout=20000)
    assert page.locator('[data-testid="style-toggle"]').get_attribute("data-current") == "entertainment"
    page.context.close()


# FR-1069 AC-380: where storage is unavailable the view still works with Software Engineering and no error.
def test_ac380_storage_unavailable_falls_back_to_engineering(studio):
    init = ("const g = Storage.prototype.getItem, s = Storage.prototype.setItem;"
            "Storage.prototype.getItem = function (k) { if (k === 'eabk-studio.style3d') throw new Error('denied'); return g.call(this, k); };"
            "Storage.prototype.setItem = function (k, v) { if (k === 'eabk-studio.style3d') throw new Error('denied'); return s.call(this, k, v); };")
    page = _open(studio, init=init)
    assert page.locator('[data-testid="style-toggle"]').get_attribute("data-current") == "engineering"
    page.locator('[data-testid="style-toggle"] [data-style-value="entertainment"]').click()
    assert page.locator('[data-testid="style-toggle"]').get_attribute("data-current") == "entertainment"
    page.context.close()
