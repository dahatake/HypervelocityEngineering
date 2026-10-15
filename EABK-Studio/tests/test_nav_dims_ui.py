"""Integration tests for FR-1040 (2D / 3D for every diagram) and FR-1041 (MECE navigation with one-line descriptions)."""
import re

import pytest

from test_links_wrap_status_ui import ROOT, REPO, studio, _open, sync_api  # noqa: F401

NAV_KEYS = ["dashboard", "implstatus", "map", "diagrams", "entities", "integrations", "source", "tables", "maintenance"]


def _nav(page):
    return page.locator("#nav a")


# FR-1041 AC-224: nine items, each with a tooltip; the screen opens with the same sentence; no two items share one.
@pytest.mark.parametrize("lang", [None, "en"])
def test_ac224_every_nav_item_has_unique_description_in_tooltip_and_screen_header(studio, lang):
    page = _open(studio, "dashboard", lang=lang)
    links = _nav(page)
    assert links.count() == len(NAV_KEYS)
    titles = [links.nth(i).get_attribute("title") for i in range(links.count())]
    assert all(titles) and len(set(titles)) == len(titles)
    for i in range(links.count()):
        links.nth(i).click()
        page.wait_for_function("t => document.getElementById('navDesc').textContent === t", arg=titles[i])
        assert page.locator("#navDesc").inner_text().strip() == titles[i]
    assert any(re.search(r"データ|record|data|graph|グラフ|図|diagram", x, re.I) for x in titles)
    page.context.close()


# FR-1041 AC-224 / FR-1042 AC-230: a repository without an integration catalog shows "no integrations", not a blank page.
def test_ac224_integrations_item_has_a_place_with_a_provisional_empty_view(studio):
    page = _open(studio, "integrations")
    assert page.get_by_test_id("integrations-none").is_visible()
    page.context.close()


# FR-1040 AC-222: icons are drawn inline with the words "2D" / "3D"; labelled for screen readers; nothing is fetched from outside.
def test_ac222_toggle_has_icon_words_accessible_names_and_no_external_requests(studio):
    page = _open(studio, "diagrams?kind=ctx&dim=2d")
    hosts = []
    page.on("request", lambda r: hosts.append(r.url))
    toggle = page.get_by_test_id("dim-toggle")
    for d in ("2d", "3d"):
        b = toggle.locator(f'[data-dim="{d}"]')
        assert b.locator("svg").count() == 1
        assert d.upper() in b.inner_text()
        assert b.get_attribute("aria-label")
    assert toggle.locator('[data-dim="2d"]').get_attribute("aria-pressed") == "true"
    assert "3D" in toggle.locator('[data-dim="3d"]').get_attribute("aria-label")  # tells where it switches to
    toggle.locator('[data-dim="3d"]').focus()
    page.keyboard.press("Enter")
    page.wait_for_function("() => document.querySelector('[data-testid=dim-toggle]')?.dataset.current === '3d'")
    assert "3D" in toggle.locator('[data-dim="3d"]').get_attribute("aria-label")
    assert toggle.locator('[data-dim="3d"]').get_attribute("aria-pressed") == "true"
    assert not [u for u in hosts if not u.startswith(page.url.split("#")[0])]
    page.context.close()


# FR-1040 AC-222: the icon motion stops under "reduce motion"; the command box switches the dimension too.
def test_ac222_reduced_motion_stops_icon_and_command_box_switches_dimension(studio):
    page = _open(studio, "diagrams?kind=ctx&dim=2d")
    page.emulate_media(reduced_motion="reduce")
    assert page.evaluate("() => getComputedStyle(document.querySelector('.dim-btn.on .dim-ico')).animationName") == "none"
    page.emulate_media(reduced_motion="no-preference")
    assert page.evaluate("() => getComputedStyle(document.querySelector('.dim-btn.on .dim-ico')).animationName") != "none"
    page.locator("#q").fill(">2D")
    page.locator("#q").press("Enter")
    page.wait_for_function("() => document.querySelector('[data-testid=dim-toggle]')?.dataset.current === '3d'")
    page.context.close()


# FR-1040 AC-221: the selected object, the kind and the typed filter survive 2D <-> 3D.
def test_ac221_selection_kind_and_search_text_survive_dimension_switch(studio):
    page = _open(studio, "diagrams?kind=goals&dim=2d")
    page.locator("#q").fill("FR-001")
    page.locator('.dgm [data-id="FR-001"]').first.click()
    page.wait_for_selector("#drawer:not([hidden])")
    toggle = page.get_by_test_id("dim-toggle")
    toggle.locator('[data-dim="3d"]').click()
    page.wait_for_function("() => document.querySelector('[data-testid=dim-toggle]')?.dataset.current === '3d'")
    state = page.evaluate("() => window.eabkView.getState().diagram")
    assert state["kind"] == "goals" and state["dim"] == "3d"
    assert "FR-001" in page.locator("#drawer").inner_text()
    assert page.locator("#q").input_value() == "FR-001"
    toggle.locator('[data-dim="2d"]').click()
    page.wait_for_selector('.dgm [data-id="FR-001"]')
    assert "FR-001" in page.locator("#drawer").inner_text()
    page.context.close()


# FR-1040 AC-220: the 3D scene really draws the published elements (a canvas exists with a table alternative).
def test_ac220_3d_view_has_canvas_and_table_alternative_with_same_ids(studio):
    page = _open(studio, "diagrams?kind=entities&dim=3d")
    page.wait_for_selector('[data-testid="dgm-3d-stage"] canvas')
    ids = {e["id"] for e in page.evaluate("() => window.eabkView.getState().diagram.elements")}
    page.locator("details.sz-alt summary").click()
    rows = set(page.locator("details.sz-alt tr[data-id]").evaluate_all("els => els.map(e => e.dataset.id)"))
    assert ids and rows == ids
    page.context.close()


# FR-1040 AC-223: without WebGL, 2D is shown with the reason and a table; the page is not broken and the selection stays.
def test_ac223_without_webgl_falls_back_to_2d_with_reason_and_table(studio):
    page = _open(studio, "diagrams?kind=components&dim=2d")
    page.evaluate("""() => {
      const orig = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (type, ...a) { return /webgl/i.test(type) ? null : orig.call(this, type, ...a); };
    }""")
    page.locator("#q").fill("FR-001")
    page.get_by_test_id("dim-toggle").locator('[data-dim="3d"]').click()
    page.wait_for_selector('[data-testid="dim-fallback"]')
    assert page.get_by_test_id("dim-toggle").get_attribute("data-current") == "2d"
    assert page.locator('[data-testid="dim-fallback"] tr[data-id]').count() >= 1
    assert page.locator("#q").input_value() == "FR-001"
    page.context.close()


# FR-1040 FR-1041 AC-221 AC-226: the map is one item; 2D / 3D move between the old routes and keep ?q.
def test_ac226_map_dimension_switch_keeps_query_and_nav_stays_on_map_item(studio):
    page = _open(studio, "map2d?q=FR-002")
    toggle = page.get_by_test_id("dim-toggle")
    assert toggle.get_attribute("data-current") == "2d"
    toggle.locator('[data-dim="3d"]').click()
    page.wait_for_function("() => location.hash.startsWith('#/map3d') && location.hash.includes('q=FR-002')")
    page.wait_for_function("() => document.querySelector('[data-testid=dim-toggle]')?.dataset.current === '3d'")
    assert page.locator('#nav a[data-nav="map"]').get_attribute("aria-current") == "page"
    page.goto(page.url.split("#")[0] + "#/dashboard")
    page.locator('#nav a[data-nav="map"]').click()
    page.wait_for_function("() => location.hash.startsWith('#/map3d')")  # the map opens in the dimension used last
    page.context.close()


# FR-1041 AC-226: the old placement URL lands on the placement diagram (layers) and keeps the runtime / matrix views.
@pytest.mark.parametrize("old,needle", [("placement?kind=runtime", "view=runtime"), ("placement?tab=data", "view=matrix")])
def test_ac226_placement_alias_moves_to_layers_diagram(studio, old, needle):
    page = _open(studio, old)
    page.wait_for_function("() => location.hash.startsWith('#/diagrams')")
    assert "kind=layers" in page.evaluate("() => location.hash") and needle in page.evaluate("() => location.hash")
    assert page.evaluate("() => window.eabkView.getState().diagram.kind") == "layers"
    page.context.close()


# FR-1041 AC-225: README and the user guide carry the data-kind -> main place table that matches the navigation definition.
def test_ac225_docs_list_exactly_the_navigation_items_of_the_app():
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    nav = re.search(r"const NAV = \[(.*?)\];", app, re.S).group(1)
    keys = re.findall(r"'(\w+)'", nav)
    assert keys == NAV_KEYS
    i18n = (ROOT / "web" / "js" / "i18n.js").read_text(encoding="utf-8")
    names = [re.search(rf"'nav\.{k}': '([^']+)'", i18n).group(1) for k in keys]
    for doc in (ROOT / "README.md", REPO / "users-guide" / "studio" / "02-screens.md"):
        text = doc.read_text(encoding="utf-8")
        assert "主な閲覧場所" in text, doc
        for name in names:
            assert name in text, (doc, name)
        for kind in ("目的", "要求", "受入基準", "試験ケース", "共通部品", "API", "テーブル", "ファイル", "PARAM", "質問", "用語", "ペルソナ", "エンティティ", "外部連携", "決定記録", "監査指摘", "出典", "実行履歴"):
            assert re.search(rf"^\|\s*{kind}\s*\|", text, re.M), (doc, kind)
