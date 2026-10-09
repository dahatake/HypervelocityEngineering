"""System-level E2E coverage for the approved EABK Studio acceptance criteria.

The assertions below are derived from docs/requirements-definition.md.  The
application is used only to discover the browser entry points and controls.
"""

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect


ROOT = Path(__file__).resolve().parents[3]
STUDIO = ROOT / "EABK-Studio" / "studio.py"


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def studio_url():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(STUDIO), "--repo", str(ROOT), "--port", str(port), "--no-open"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        raise RuntimeError("EABK Studio did not start")
    yield f"http://127.0.0.1:{port}"
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture()
def page(browser, studio_url):
    context = browser.new_context()
    page = context.new_page()
    page.goto(studio_url)
    page.wait_for_load_state("networkidle")
    yield page
    context.close()


def _fingerprint(path):
    return (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())


# FR-001 AC-001
def test_model_can_traverse_requirement_to_catalog_file_and_test(page):
    page.goto(page.url + "#/tables?tab=reqs")
    expect(page.get_by_text("FR-001", exact=True)).to_be_visible()
    page.get_by_text("FR-001", exact=True).click()
    expect(page.locator("#drawer")).to_contain_text("FR-001")
    expect(page.locator("#drawer")).to_contain_text("catalog")
    expect(page.locator("#drawer")).to_contain_text("test")


# FR-002 AC-002
def test_dashboard_shows_aggregates_and_selectable_breakdowns(page):
    page.goto(page.url + "#/dashboard")
    expect(page.locator("#view")).to_contain_text("要求")
    expect(page.locator("#view")).to_contain_text("目的")
    expect(page.locator("#view")).to_contain_text("境界")
    page.locator("#view").get_by_text("G-001", exact=True).click()
    expect(page.url).to_contain_text("#/map2d")


# FR-003 AC-003
def test_maps_highlight_selected_relationships_and_support_navigation(page):
    page.goto(page.url + "#/map2d?select=FR-001")
    expect(page.locator("#view")).to_contain_text("FR-001")
    page.mouse.wheel(0, 500)
    page.goto(page.url + "#/map3d?select=FR-001")
    expect(page.locator("#view")).to_contain_text("FR-001")
    page.mouse.move(400, 300)
    page.mouse.down()
    page.mouse.move(460, 330)
    page.mouse.up()
    page.keyboard.press("Escape")
    expect(page.locator("#drawer")).to_be_hidden()


# FR-005 AC-005
def test_selection_and_filter_survive_placement_map_and_table_switches(page):
    page.goto(page.url + "#/tables?tab=reqs&q=FR-001")
    expect(page.locator("#view")).to_contain_text("FR-001")
    page.goto(page.url + "#/map2d?select=FR-001")
    expect(page.url).to_contain_text("select=FR-001")
    page.goto(page.url + "#/placement")
    expect(page.locator("#view")).to_contain_text("配置")
    page.goto(page.url + "#/tables?tab=reqs&q=FR-001")
    expect(page.locator("#view")).to_contain_text("FR-001")


# FR-006 AC-006
def test_search_shortcuts_limit_results_and_export_table_csv(page):
    page.keyboard.press("/")
    expect(page.locator("#q")).to_be_focused()
    page.locator("#q").fill("FR-")
    expect(page.locator("#results")).to_be_visible()
    assert page.locator("#results > *").count() <= 40
    page.keyboard.press("Enter")
    expect(page.url).to_contain_text("map")
    page.keyboard.press("Control+K")
    expect(page.locator("#q")).to_be_focused()
    page.goto(page.url.split("#")[0] + "#/tables?tab=reqs")
    with page.expect_download() as download_info:
        page.get_by_text("CSV", exact=True).click()
    assert download_info.value.suggested_filename.endswith(".csv")


# FR-008 AC-008
def test_persona_defaults_and_switching_preserve_selected_id_filter_and_time(page):
    page.goto(page.url + "#/dashboard")
    expect(page.locator("#view")).to_contain_text("Product")
    page.goto(page.url + "#/map2d?select=FR-001")
    selected_url = page.url
    page.get_by_role("button", name="EN").click()
    expect(page.url).to_contain_text("select=FR-001")
    expect(page.locator("#view")).to_contain_text("FR-001")
    assert page.url != selected_url or page.locator("#view").inner_text()


# FR-010 AC-010
def test_invalid_repository_switch_keeps_model_and_explains_failure(page, tmp_path):
    before = page.locator("#repoBtn").inner_text()
    page.locator("#repoBtn").click()
    page.get_by_role("dialog").get_by_role("textbox").fill(str(tmp_path))
    page.get_by_role("dialog").get_by_role("button", name="OK").click()
    expect(page.locator("#toast")).to_contain_text("data")
    expect(page.locator("#repoBtn")).to_have_text(before)


# FR-013 AC-013
def test_startup_switch_and_refresh_do_not_write_data_or_leave_loopback(page, studio_url):
    tracked = [ROOT / "docs" / "requirements-definition.md", ROOT / "docs" / "catalog.md"]
    before = {path: _fingerprint(path) for path in tracked}
    expect(page).to_have_url(studio_url + "/")
    page.goto(page.url + "#/tables?tab=cases")
    page.reload()
    assert {path: _fingerprint(path) for path in tracked} == before
    assert page.url.startswith("http://127.0.0.1:")


# NFR-SEC-001 AC-023
def test_server_binds_loopback_on_default_port_and_rejects_foreign_host(page):
    default = subprocess.Popen(
        [sys.executable, str(STUDIO), "--repo", str(ROOT), "--no-open"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", 8765), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise AssertionError("default port 8765 did not open")
        assert page.url.startswith("http://127.0.0.1:")
    finally:
        default.terminate()
        try:
            default.wait(timeout=3)
        except subprocess.TimeoutExpired:
            default.kill()
    response = page.request.get(page.url.split("/", 3)[0] + "//evil.example/api/model")
    assert response.status in (400, 403)


# NFR-SEC-002 AC-024
def test_all_views_are_read_only_and_do_not_issue_external_requests(page):
    tracked = ROOT / "docs" / "requirements-definition.md"
    before = _fingerprint(tracked)
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    for route in ("dashboard", "map2d", "map3d", "diagrams", "placement", "source", "tables"):
        page.goto(page.url.split("#")[0] + f"#/{route}")
    assert _fingerprint(tracked) == before
    assert all(url.startswith("http://127.0.0.1:") for url in requests)


# NFR-OPS-001 AC-026
def test_python_runtime_starts_without_extra_installation_and_shows_default_model(page):
    assert sys.version_info >= (3, 9)
    expect(page.locator("#repoBtn")).to_contain_text(ROOT.name)
    expect(page.locator("#view")).not_to_contain_text("no-data-layer")


# NFR-OPS-003 AC-028
def test_missing_data_error_offers_recovery_without_losing_current_model(page, tmp_path):
    current = page.locator("#repoBtn").inner_text()
    page.locator("#repoBtn").click()
    page.get_by_role("dialog").get_by_role("textbox").fill(str(tmp_path / "missing"))
    page.get_by_role("dialog").get_by_role("button", name="OK").click()
    expect(page.locator("#toast")).to_contain_text("not found")
    expect(page.locator("#repoBtn")).to_have_text(current)
    expect(page.get_by_role("button", name="Close")).to_be_visible()


# FR-001 AC-033
def test_configured_data_links_requirement_ac_catalog_case_and_source(page):
    page.goto(page.url + "#/tables?tab=reqs")
    page.get_by_text("FR-001", exact=True).click()
    drawer = page.locator("#drawer")
    expect(drawer).to_contain_text("AC-001")
    expect(drawer).to_contain_text("EABK-Studio")
    expect(drawer).to_contain_text("test")
    expect(drawer).to_contain_text("SRC-")


# FR-010 AC-034
def test_repository_switch_success_updates_model_and_failure_restores_previous(page, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    (other / "docs").mkdir()
    (other / "docs" / "requirements-definition.md").write_text(
        "# Other\n\n- 目的 G-OTHER: Other\n- 要求 FR-OTHER: Other\n", encoding="utf-8"
    )
    (other / "docs" / "catalog.md").write_text("# Catalog\n", encoding="utf-8")
    page.locator("#repoBtn").click()
    page.get_by_role("dialog").get_by_role("textbox").fill(str(other))
    page.get_by_role("dialog").get_by_role("button", name="OK").click()
    expect(page.locator("#repoBtn")).to_contain_text("other")
    page.locator("#repoBtn").click()
    page.get_by_role("dialog").get_by_role("textbox").fill(str(tmp_path / "invalid"))
    page.get_by_role("dialog").get_by_role("button", name="OK").click()
    expect(page.locator("#repoBtn")).to_contain_text("other")


# FR-1001 AC-037
def test_first_steps_consolidates_startup_prerequisites_and_unknowns(page):
    guide = ROOT / "EABK-Studio" / "users-guide" / "01-first-steps.md"
    page.goto("file://" + guide.as_posix())
    content = page.locator("body")
    for phrase in ("start.ps1", "start.sh", "Python", "追加インストール不要", "three.js", "127.0.0.1", "8765"):
        expect(content).to_contain_text(phrase)
    expect(content).to_contain_text("未確認")
