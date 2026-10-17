"""Integration tests for FR-1053 / FR-1054 / FR-1055 / NFR-UX-012 (EABK Studio RPG-style map).
Run: python -m pytest EABK-Studio/tests/test_rpg_mode_ui.py -q   (AC-293 is a manual check: docs/rpg-originality.md)"""
import socket
import subprocess
import sys
import time

import pytest

from test_links_wrap_status_ui import ROOT, studio, _open, sync_api  # noqa: F401
from entity_repo import make_large

DIRS = {"ArrowUp": (0, -1), "ArrowDown": (0, 1), "ArrowLeft": (-1, 0), "ArrowRight": (1, 0)}


def _state(page):
    return page.evaluate("() => window.eabkView.getState()")


def _rpg(page):
    return _state(page)["rpg"]


def _press(page, key):
    page.keyboard.press(key)
    page.wait_for_timeout(300)


def _walk_to(page, target):
    rpg = _rpg(page)
    blocked = {tuple(b) for b in rpg["map"]["blocked"]}
    w, h = rpg["map"]["width"], rpg["map"]["height"]
    start = (rpg["player"]["x"], rpg["player"]["y"])
    prev, queue = {start: None}, [start]
    while queue:
        cur = queue.pop(0)
        for key, (dx, dy) in DIRS.items():
            n = (cur[0] + dx, cur[1] + dy)
            if 0 <= n[0] < w and 0 <= n[1] < h and n not in blocked and n not in prev:
                prev[n] = (cur, key)
                queue.append(n)
    keys, cur = [], target
    assert target in prev
    while prev[cur]:
        cur, key = prev[cur][0], prev[cur][1]
        keys.append(key)
    for key in reversed(keys):
        _press(page, key)


def _view(studio, **kw):
    page = _open(studio, "maprpg", **kw)
    page.wait_for_selector('[data-testid="rpg-view"][data-ready="true"]')
    page.get_by_test_id("rpg-view").focus()
    return page


# FR-1053 AC-287: one castle per goal, one town per entity, each with name and ID; roads only between related places.
def test_ac287_castles_and_towns_match_the_data_and_roads_connect_only_related_places(studio):
    page = _view(studio)
    rpg = _rpg(page)
    kinds = {}
    for p in rpg["places"]:
        kinds.setdefault(p["kind"], []).append(p)
        assert p["name"] and p["id"]
    assert len(kinds["town"]) == 2 and len(kinds["castle"]) == 1 and kinds["castle"][0]["id"] == "G-001"
    towns = {p["id"]: p for p in kinds["town"]}
    assert "town:none" in towns and towns["town:none"]["name"] == "関係なしの街"   # 在庫 has no relation
    res = rpg["residents"]
    assert {r["name"] for r in res} == {"注文", "顧客", "商品", "在庫"} and len(res) == 4   # residents = entities
    assert {r["name"]: r["town"] for r in res}["在庫"] == "town:none" and len({r["town"] for r in res if r["name"] != "在庫"}) == 1
    assert len({p["id"] for p in rpg["places"] + res}) == len(rpg["places"]) + len(res)   # no duplicates
    ids = {p["id"] for p in rpg["places"] + res}
    pairs = {frozenset((r["from"], r["to"])) for r in rpg["roads"]}
    assert all(r["from"] in ids and r["to"] in ids for r in rpg["roads"])
    assert frozenset(("ent:注文", "ent:顧客")) in pairs and frozenset(("ent:注文", "ent:商品")) in pairs
    assert frozenset(("ent:在庫", "ent:注文")) not in pairs and frozenset(("ent:在庫", "ent:顧客")) not in pairs
    other = next(i for i in towns if i != "town:none")
    assert frozenset(("G-001", "town:none")) in pairs and frozenset(("G-001", other)) in pairs   # goal -> requirement -> entity's town
    page.context.close()


# FR-1053 AC-288 / AC-289: the talk window types out, A shows it all, IDs are links; the same content is readable without the picture.
def test_ac288_ac289_dialog_text_links_and_alternative_representations(studio):
    page = _view(studio)
    resident = next(p for p in _rpg(page)["residents"] if p["id"] == "ent:注文")
    town = resident
    _walk_to(page, (town["x"], town["y"]))
    page.keyboard.press("Enter")
    dlg = page.get_by_test_id("rpg-dialog")
    assert dlg.is_visible()
    page.keyboard.press("Enter")                       # A while typing = show everything
    assert _rpg(page)["dialog"]["complete"] is True
    txt = dlg.inner_text()
    assert "注文" in txt and "ent:注文" in txt and "関連する要求: 1 件" in txt and "FR-001" in txt
    assert dlg.locator("a").count() >= 1               # FR-1031 link
    live = page.get_by_test_id("rpg-live").inner_text()
    assert "注文" in live and "FR-001" in live         # screen reader gets the full text
    assert "注文" in page.get_by_test_id("rpg-pos").inner_text()
    page.locator("summary", has_text="同じ内容を表で見る").click()
    assert page.locator('[data-testid="rpg-alt"] tbody tr').count() == 7   # 1 castle + 2 towns + 4 residents
    page.keyboard.press("Escape")
    assert (_rpg(page)["player"]["x"], _rpg(page)["player"]["y"]) == (town["x"], town["y"])
    assert _state(page)["selected"] == "注文"
    page.context.close()


# FR-1053 AC-288: talking at a town entrance shows the grouping (name, description, related requirements).
def test_ac288_town_entrance_dialog_shows_the_grouping(studio):
    page = _view(studio)
    town = next(p for p in _rpg(page)["places"] if p["id"] == "town:none")
    _walk_to(page, (town["x"], town["y"]))
    page.keyboard.press("Enter")
    page.keyboard.press("Enter")
    txt = page.get_by_test_id("rpg-dialog").inner_text()
    assert "関係なしの街" in txt and "town:none" in txt and "関連する要求" in txt
    page.keyboard.press("Escape")
    assert page.get_by_test_id("rpg-dialog").is_hidden()
    assert (_rpg(page)["player"]["x"], _rpg(page)["player"]["y"]) == (town["x"], town["y"])
    page.context.close()


# FR-1053 AC-290: browsing is read-only (nothing but GET requests, even after talking at a town).
def test_ac290_browsing_is_read_only(studio):
    browser, url = studio
    page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
    methods = []
    page.on("request", lambda r: methods.append(r.method))
    page.goto(f"{url}/#/maprpg")
    page.wait_for_selector('[data-testid="rpg-view"][data-ready="true"]')
    page.get_by_test_id("rpg-view").focus()
    town = next(p for p in _rpg(page)["places"] if p["kind"] == "town")
    _walk_to(page, (town["x"], town["y"]))
    page.keyboard.press("Enter")
    assert set(methods) <= {"GET"}                     # reading never writes (FR-013, NFR-SEC-002)
    page.context.close()


# FR-1053 AC-290: no goals / no entities -> the 2D map with the reason and a table, never an error.
def test_ac290_zero_goals_or_entities_shows_2d_not_an_error(studio, tmp_path):
    from entity_repo import make_zoom, build_doc, DOC
    repo = make_zoom(tmp_path / "e")
    (repo / DOC).write_text(build_doc({}, [], []), encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, str(ROOT / "studio.py"), "--repo", str(repo), "--port", str(port), "--no-open"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        end = time.time() + 15
        while time.time() < end:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        if True:
            browser = studio[0]
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/#/maprpg")
            page.wait_for_selector('[data-testid="dim-toggle"]')
            page.wait_for_selector('[data-testid="rpg-fallback"]')
            assert "2D" in page.get_by_test_id("rpg-fallback").inner_text()
            assert page.get_by_test_id("dim-toggle").get_attribute("data-current") == "rpg"   # the chosen mode is kept
            assert not errors
    finally:
        proc.terminate()

# FR-1054 AC-291 / AC-292 / AC-294: sound is off at first, nothing is fetched from outside, characters are drawn, scenes change.
def test_ac291_ac292_ac294_muted_at_first_no_external_requests_characters_and_scene_music(studio):
    browser, url = studio
    page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
    urls = []
    page.on("request", lambda r: urls.append(r.url))
    page.goto(f"{url}/#/maprpg")
    page.wait_for_selector('[data-testid="rpg-view"][data-ready="true"]')
    page.get_by_test_id("rpg-view").focus()
    rpg = _rpg(page)
    assert rpg["muted"] is True and rpg["audio"]["started"] is False        # no AudioContext before the user asks (AC-294)
    assert "オフ" in page.get_by_test_id("rpg-sound").inner_text() and "🔇" in page.get_by_test_id("rpg-sound").inner_text()
    roles = {c["kind"] for c in rpg["characters"]}
    assert {"hero", "villager", "guide"} <= roles and all(c["role"] for c in rpg["characters"])   # named by role, not only by colour
    town = next(p for p in rpg["places"] if p["kind"] == "town")
    castle = next(p for p in rpg["places"] if p["kind"] == "castle")
    _walk_to(page, (castle["x"], castle["y"]))
    _walk_to(page, (town["x"], town["y"]))
    _press(page, "ArrowDown")
    assert {"castle", "town", "field"} <= set(_rpg(page)["audio"]["scenes"] + [_rpg(page)["audio"]["scene"]])
    page.keyboard.press("Shift")
    page.keyboard.press("Enter")                                           # Select -> sound on
    st = _rpg(page)
    assert st["muted"] is False and st["audio"]["started"] is True
    assert "オン" in page.get_by_test_id("rpg-sound").inner_text()
    _press(page, "ArrowUp")
    for name in ("move", "confirm"):
        assert st["audio"]["requested"].get(name, 0) >= 1
    page.get_by_test_id("rpg-sound").click()                                # one operation back to mute
    assert _rpg(page)["muted"] is True
    assert all(u.startswith(url) or u.startswith("data:") for u in urls), [u for u in urls if not u.startswith(url)]
    assert not [u for u in urls if u.endswith((".png", ".jpg", ".gif", ".mp3", ".wav", ".ogg", ".woff", ".woff2", ".ttf"))]
    page.context.close()


# FR-1055 AC-296: the key assignment is always on screen (JA and EN), a held key never repeats a button, the same operation is a command.
@pytest.mark.parametrize("lang,word", [(None, "セレクト"), ("en", "Select")])
def test_ac296_legend_menu_help_and_held_keys(studio, lang, word):
    page = _view(studio, lang=lang)
    assert word in page.get_by_test_id("rpg-legend").inner_text()
    page.keyboard.press("Space")
    menu = page.get_by_test_id("rpg-menu")
    assert menu.is_visible()
    page.keyboard.press("Enter")                                           # first item = controls
    keys = page.get_by_test_id("rpg-keys")
    assert keys.is_visible() and word in keys.inner_text()
    page.keyboard.press("Escape")
    assert not menu.is_visible()
    town = next(p for p in _rpg(page)["places"] if p["kind"] == "castle")
    _walk_to(page, (town["x"], town["y"]))
    page.keyboard.down("Enter")
    for _ in range(5):
        page.keyboard.down("Enter")                                        # auto-repeat of a held key
    page.keyboard.up("Enter")
    assert _rpg(page)["dialog"]["open"] is True                            # not read through / closed by the repeat
    page.keyboard.press("Escape")
    page.context.close()


def test_ac296_rpg_is_a_command(studio):
    page = _open(studio, "map2d")
    page.keyboard.press("Control+k")
    page.get_by_test_id("command-search").type("RPG")
    page.keyboard.press("Enter")
    page.wait_for_selector('[data-testid="rpg-view"]')
    page.context.close()


# FR-1055 AC-297: typing, browser shortcuts and the search shortcuts are not taken.
def test_ac297_typing_and_shortcuts_are_left_alone(studio):
    page = _view(studio)
    before = _rpg(page)["player"]
    page.locator("#q").focus()
    for k in ("w", "a", "s", "d", "z", " "):
        page.keyboard.type(k)
    assert _rpg(page)["player"] == before and page.locator("#q").input_value() == "wasdz "
    assert _rpg(page)["dialog"]["open"] is False and _rpg(page)["menu"]["open"] is False
    page.get_by_test_id("rpg-view").focus()
    page.keyboard.press("Control+ArrowLeft")
    page.keyboard.press("Alt+ArrowLeft")
    assert _rpg(page)["player"] == before
    page.keyboard.press("/")                                                # PARAM-006 search shortcut still works
    assert page.evaluate("() => document.activeElement.id") == "q"
    page.context.close()


# NFR-UX-012 AC-298: reduced motion stops the movement; Tab / Shift+Tab / Esc leave the map and come back.
def test_ac298_reduced_motion_and_no_keyboard_trap(studio):
    browser, url = studio
    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, reduced_motion="reduce")
    page = ctx.new_page()
    page.goto(f"{url}/#/maprpg")
    page.wait_for_selector('[data-testid="rpg-view"][data-ready="true"]')
    page.get_by_test_id("rpg-view").focus()
    assert _rpg(page)["reducedMotion"] is True
    castle = next(p for p in _rpg(page)["places"] if p["kind"] == "castle")
    _walk_to(page, (castle["x"], castle["y"]))
    page.keyboard.press("Enter")
    assert _rpg(page)["dialog"]["complete"] is True                         # text appears at once; nothing is lost
    page.keyboard.press("Escape")
    # Esc with nothing open moves the focus out of the map
    page.keyboard.press("Escape")
    assert page.evaluate("() => !document.querySelector('[data-testid=rpg-view]').contains(document.activeElement)")
    # Tab / Shift+Tab never open the Select menu and always move the focus
    page.get_by_test_id("rpg-view").focus()
    page.keyboard.press("Shift+Tab")
    assert _rpg(page)["select"]["open"] is False
    assert page.evaluate("() => document.activeElement !== document.querySelector('[data-testid=rpg-view]')")
    page.get_by_test_id("rpg-view").focus()
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement !== document.querySelector('[data-testid=rpg-view]')")
    ctx.close()


# NFR-UX-012 AC-299: with the assumed upper bound of entities the map still runs smoothly and fetches nothing.
def test_ac299_large_data_keeps_frame_rate_and_makes_no_external_requests(studio, tmp_path):
    repo = make_large(tmp_path / "big", entities=300, columns=600)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, str(ROOT / "studio.py"), "--repo", str(repo), "--port", str(port), "--no-open"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        end = time.time() + 15
        while time.time() < end:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        if True:
            browser = studio[0]
            page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
            urls = []
            page.on("request", lambda r: urls.append(r.url))
            page.goto(f"http://127.0.0.1:{port}/#/maprpg")
            page.wait_for_selector('[data-testid="rpg-view"][data-ready="true"]')
            page.get_by_test_id("rpg-view").focus()
            rpg = _rpg(page)
            assert len([p for p in rpg["places"] if p["kind"] == "town"]) == 30 and len(rpg["residents"]) == 300
            for key in ["ArrowDown", "ArrowRight", "ArrowDown", "ArrowLeft"] * 3:
                page.keyboard.press(key)
                page.wait_for_timeout(150)
            page.wait_for_timeout(1200)
            perf = _rpg(page)["perf"]
            print("fps", perf, "headless chromium")
            assert perf["fps"] >= perf["minFps"]
            assert all(u.startswith(f"http://127.0.0.1:{port}") or u.startswith("data:") for u in urls)
    finally:
        proc.terminate()



