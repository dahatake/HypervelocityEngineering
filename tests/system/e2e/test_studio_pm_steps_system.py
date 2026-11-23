"""System test for FR-1094 AC-514 (HVE Studio: the Product Manager's work steps at the top of the screen).

Expected values come from the acceptance criterion and section 4 "ステップごとの既定の表現" of
docs/requirements-definition.md: six numbered steps in order; on start step 1 is selected with the dashboard; each step
opens its default screen and lists only its screens; FR-1041's nine items are all reachable from some step; steps can be
chosen by mouse, keyboard (Tab, arrow keys, Enter) and the command search; the selected step is marked by shape and
word besides colour; no role selector (Product Manager / Architect / Software Engineer) is shown in the header.
"""
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect

from entity_repo import make_standard

ROOT = Path(__file__).resolve().parents[3]
STUDIO = ROOT / "HVE-Studio" / "studio.py"
NINE = {"dashboard", "implstatus", "map", "diagrams", "entities", "integrations", "source", "tables", "maintenance"}
# section 4: step -> (default screen, screens of the step); "release" is the release view of the implementation status item
STEPS = {
    1: ("dashboard", ["dashboard"]),
    2: ("tables", ["tables", "entities", "integrations"]),
    3: ("source", ["source", "map", "diagrams"]),
    4: ("implstatus", ["implstatus", "tables"]),
    5: ("release", ["release", "tables"]),
    6: ("maintenance", ["maintenance", "tables"]),
}
HASH = {"dashboard": "#/dashboard", "tables": "#/tables", "source": "#/floorplan", "implstatus": "#/implstatus", "release": "#/release",
        "maintenance": "#/maintenance"}


@pytest.fixture()
def url(tmp_path):
    repo = make_standard(tmp_path / "std")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, str(STUDIO), "--repo", str(repo), "--port", str(port), "--no-open", "--no-remote"],
                            cwd=repo, env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    end = time.time() + 15
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}/"
    proc.terminate()


def _open(browser, url):
    page = browser.new_context(viewport={"width": 1400, "height": 900}).new_page()
    page.goto(url)
    page.wait_for_selector("#splash[hidden]", state="attached", timeout=30000)
    page.wait_for_load_state("networkidle")
    return page


def _steps(page):
    return page.locator('#steps [data-testid="step"]')


# FR-1094 AC-514
def test_ac514_steps_in_order_with_default_screens_and_all_nine_items(browser, url):
    page = _open(browser, url)
    steps = _steps(page)
    expect(steps).to_have_count(6)
    assert [steps.nth(i).get_attribute("data-step") for i in range(6)] == ["1", "2", "3", "4", "5", "6"]
    assert all(re.search(rf"\b{i + 1}\b", steps.nth(i).inner_text()) or steps.nth(i).locator(".step-num svg").count() for i in range(6))
    expect(steps.nth(0)).to_have_attribute("aria-current", "step")
    assert page.evaluate("() => location.hash") in ("", "#/dashboard")
    expect(page.locator('#nav a[data-nav="dashboard"]')).to_have_attribute("aria-current", "page")

    reached = set()
    for n, (default, items) in STEPS.items():
        steps.nth(n - 1).click()
        expect(steps.nth(n - 1)).to_have_attribute("aria-current", "step")
        page.wait_for_function("h => location.hash.startsWith(h)", arg=HASH[default])
        listed = page.locator("#nav a").evaluate_all("els => els.map(e => e.dataset.nav)")
        assert listed == items, (n, listed)
        expect(page.locator(f'#nav a[data-nav="{default}"]')).to_have_attribute("aria-current", "page")
        reached |= set(listed)
    assert NINE <= reached


def test_ac514_impact_step_opens_source_and_keeps_other_tabs_available(browser, url):
    page = _open(browser, url)
    step = _steps(page).nth(2)
    step.click()
    tabs = page.locator("#nav a")
    expect(tabs).to_have_text(["ソースコード構造", "マップ", "図式"])
    expect(tabs.nth(0)).to_have_attribute("aria-current", "page")
    expect(page.get_by_test_id("src-tab-functions")).to_have_attribute("aria-selected", "true")
    for key in ("map", "diagrams"):
        tab = page.locator(f'#nav a[data-nav="{key}"]')
        tab.click()
        expect(tab).to_have_attribute("aria-current", "page")
        expect(step).to_have_attribute("aria-current", "step")
    _steps(page).nth(0).click()
    step.click()
    expect(page.get_by_test_id("src-tab-functions")).to_have_attribute("aria-selected", "true")


def test_ac514_keyboard_and_command_search_choose_a_step(browser, url):
    page = _open(browser, url)
    steps = _steps(page)
    steps.nth(0).focus()
    page.keyboard.press("ArrowRight")
    assert page.evaluate("() => document.activeElement.dataset.step") == "2"
    page.keyboard.press("Enter")
    expect(steps.nth(1)).to_have_attribute("aria-current", "step")
    page.wait_for_function("() => location.hash.startsWith('#/tables')")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("Space")
    expect(steps.nth(3)).to_have_attribute("aria-current", "step")
    # Tab reaches the step bar (the current step is the one in the tab order)
    assert steps.nth(3).get_attribute("tabindex") == "0" and steps.nth(0).get_attribute("tabindex") == "-1"
    page.locator("#q").fill(">ステップ 5")
    page.get_by_test_id("command-item").filter(has_text="ステップ 5").first.click()
    expect(steps.nth(4)).to_have_attribute("aria-current", "step")
    page.wait_for_function("() => location.hash.startsWith('#/release')")


def test_ac514_selected_step_has_shape_and_word_and_no_role_selector(browser, url):
    page = _open(browser, url)
    on = page.locator('#steps [data-testid="step"][aria-current="step"]')
    off = page.locator('#steps [data-testid="step"]:not([aria-current])').first
    assert on.locator(".step-num svg").count() == 1 and off.locator(".step-num svg").count() == 0   # shape: check mark
    assert on.locator(".step-here").inner_text().strip() and off.locator(".step-here").count() == 0  # word: "現在"
    deco = page.evaluate("""() => { const a = getComputedStyle(document.querySelector('.step.on')), b = getComputedStyle(document.querySelector('.step:not(.on)'));
        return [a.textDecorationLine, b.textDecorationLine, a.fontWeight, b.fontWeight]; }""")
    assert "underline" in deco[0] and "underline" not in deco[1] and deco[2] != deco[3]
    header = page.locator("header.top")
    for role in ("Product Manager", "Architect", "Software Engineer"):
        assert header.get_by_role("button", name=re.compile(role)).count() == 0
    assert page.locator("#personaBar").count() == 0
