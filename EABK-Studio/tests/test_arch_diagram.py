"""Tests for FR-1034 (architecture diagram + entity model with data location). Run: python -m pytest EABK-Studio/tests -q"""
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(REPO / "tests" / "system"))
import eabk_model as m  # noqa: E402
from entity_repo import make_zoom, CAT  # noqa: E402

sync_api = pytest.importorskip("playwright.sync_api")

SECTION = (
    "\n## 配置先\n"
    "- 配置先: PC / フォルダ: data/orders / データ: 注文\n"
    "- 配置先: ブラウザー / Local Storage: eabk.filters / データ: 絞り込み\n"
    "- 配置先: Power Platform / 環境: 開発 / データ: 顧客\n"
    "- 配置先: Azure / サービス: Azure SQL / アプリ: 注文API（.NET MAUI on Windows） / データ: 商品\n"
    "- 通信: 注文API → Azure SQL（送信）\n"
    "- 通信: 幻のサービス → どこか（受信）\n"
)


def _doc(tmp_path, text):
    p = tmp_path / "catalog.md"
    p.write_text(text, encoding="utf-8")
    return m.parse_document(p, "catalog.md")


# FR-1034 AC-199: folder / Local Storage name / environment / service units, apps, data and link direction are parsed.
def test_parse_placements_units_apps_data_and_links(tmp_path):
    pl = m.parse_placements(_doc(tmp_path, "# カタログ\n" + SECTION))
    locs = {(l["kind"], l["name"]): l for l in pl["locations"]}
    assert set(locs) == {("PC", "data/orders"), ("ブラウザー", "eabk.filters"), ("Power Platform", "開発"), ("Azure", "Azure SQL")}
    az = locs[("Azure", "Azure SQL")]
    assert az["data"] == ["商品"] and az["apps"] == ["注文API（.NET MAUI on Windows）"]
    assert az["links"] == [{"to": "Azure SQL", "direction": "送信"}]


# FR-1034 AC-202: nothing is invented; a link whose ends are not listed stays unresolved; no section means no locations.
def test_parse_placements_does_not_guess(tmp_path):
    pl = m.parse_placements(_doc(tmp_path, "# カタログ\n" + SECTION))
    bad = [x for x in pl["links"] if x["from"] == "幻のサービス"][0]
    assert bad["resolved"] is False and all(not l["links"] or l["name"] == "Azure SQL" for l in pl["locations"])
    assert m.parse_placements(_doc(tmp_path, "# カタログ\n## 機能\n")) == {"locations": [], "links": []}
    assert m.parse_placements(None) == {"locations": [], "links": []}


@pytest.fixture(scope="module")
def studio(tmp_path_factory):
    repo = make_zoom(tmp_path_factory.mktemp("arch") / "r")
    cat = repo / CAT
    cat.write_text(cat.read_text(encoding="utf-8") + SECTION, encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, str(ROOT / "studio.py"), "--repo", str(repo), "--port", str(port), "--no-open"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    end = time.time() + 15
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


def _arch(studio, route="map2d", lang=None):
    browser, url = studio
    page = browser.new_context(viewport={"width": 1400, "height": 900}).new_page()
    if lang:
        page.add_init_script(f"localStorage.setItem('eabk-studio.lang','{lang}')")
    page.goto(f"{url}/#/{route}?view=arch")
    page.wait_for_selector('[data-testid="semantic-zoom"][data-ready="true"]')
    return page


# FR-1034 AC-201 AC-202: each entity shows where it is stored; unlisted ones show "なし" (never guessed).
@pytest.mark.parametrize("route", ["map2d", "map3d"])
def test_entity_storage_is_listed_or_none(studio, route):
    page = _arch(studio, route)
    st = page.evaluate("() => window.eabkView.getState()")
    assert st["arch"] is True
    assert st["storage"]["注文"] == ["PC · data/orders"]
    assert st["storage"]["在庫"] == "なし"
    page.context.close()


# FR-1034 AC-201: selection and level survive the 2D <-> 3D switch.
def test_selection_and_scale_are_kept_between_2d_and_3d(studio):
    page = _arch(studio, "map2d")
    page.evaluate("() => { window.eabkView.setScale(3); window.eabkView.select('注文'); }")
    page.evaluate("() => { location.hash = '#/map3d?view=arch'; }")
    page.wait_for_function("() => window.eabkView && window.eabkView.mode === 'map3d'")
    st = page.evaluate("() => window.eabkView.getState()")
    assert st["selected"] == "注文" and st["level"] == "mid" and st["scale"] == 3
    page.context.close()


# FR-1034 AC-203: a table lists location / app / data / link / storage; keys zoom; the words exist in JA and EN.
@pytest.mark.parametrize("lang,word", [(None, "実行場所"), ("en", "Execution locations")])
def test_text_list_and_keyboard_zoom_in_both_languages(studio, lang, word):
    page = _arch(studio, "map2d", lang)
    page.locator('[data-testid="sz-alt"] summary').click()
    page.wait_for_selector("[data-alt-location]", state="attached")
    body = page.locator('[data-testid="sz-alt"] .sz-alt-body')
    assert word in body.inner_text()
    assert page.locator("[data-alt-location]").count() == 4
    assert "Azure SQL" in page.locator('[data-alt-location="Azure|Azure SQL"]').inner_text()
    assert ("なし" if lang is None else "None") in page.locator('[data-alt-storage="在庫"]').inner_text()   # FR-011: the word follows the UI language
    before = page.evaluate("() => window.eabkView.getState().scale")
    page.locator('[data-testid="semantic-zoom"] [tabindex="0"]').first.focus()
    page.keyboard.press("+")
    assert page.evaluate("() => window.eabkView.getState().scale") > before
    page.context.close()
