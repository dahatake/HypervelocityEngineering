"""System tests for FR-010 AC-332..AC-336 (EABK Studio: repository switch by the OS folder dialog).

Expected values come only from the acceptance criteria in docs/requirements-definition.md.  The
implementation is NOT the oracle.

CONTRACT (design premise handed to the implementer; not derived from the implementation):
  - POST /api/repo/pick: Host must be localhost/127.0.0.1/::1 and header X-EABK-Studio: 1 (else 403).
    The OS dialog is opened server-side.  If env EABK_STUDIO_PICK_PATH is set, its value is returned as the
    selection instead of opening the dialog (test hook; empty string = cancel).
    Response {"path": "<selected>"} / cancel {"path": ""} / dialog impossible: 501 {"error":"picker-unavailable"}.
  - Screen: #repoBtn (data-testid="repo-pick", with a folder icon) click -> /api/repo/pick; if path is
    non-empty -> /api/repo switch, then every display is reloaded.  No path-typing modal exists.
  - Repositories: A = make_standard ("std": FR-003 画面表示のみ), B = make_other ("oth": FR-001 ほげ).
    The header target name is the repository folder name.
"""
import http.client
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect

from entity_repo import make_other, make_standard

ROOT = Path(__file__).resolve().parents[3]
STUDIO = ROOT / "EABK-Studio" / "studio.py"
HDR = {"X-EABK-Studio": "1", "Content-Type": "application/json"}


def _serve(repo, pick=None):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = dict(os.environ)
    env.pop("EABK_STUDIO_PICK_PATH", None)
    if pick is not None:
        env["EABK_STUDIO_PICK_PATH"] = pick
    proc = subprocess.Popen(
        [sys.executable, str(STUDIO), "--repo", str(repo), "--port", str(port), "--no-open"],
        cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    end = time.time() + 10
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return proc, port
        except OSError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("EABK Studio did not start")


class Studio:
    def __init__(self, tmp_path, pick_kind):
        self.a = make_standard(tmp_path / "std")
        self.b = make_other(tmp_path / "oth")
        self.plain = tmp_path / "plain"          # exists, no management data
        self.plain.mkdir()
        self.missing = tmp_path / "nowhere"      # does not exist
        pick = {"b": str(self.b), "cancel": "", "plain": str(self.plain),
                "missing": str(self.missing), None: None}[pick_kind]
        self.proc, self.port = _serve(self.a, pick)
        self.url = f"http://127.0.0.1:{self.port}"

    def post(self, path, headers=None, host=None, body=b"{}"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = dict(headers or {})
        if host:
            h["Host"] = host
        c.request("POST", path, body=body, headers=h)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, data

    def repo(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", "/api/repo")
        data = json.loads(c.getresponse().read())
        c.close()
        return Path(data["repo"]).name

    def stop(self):
        self.proc.terminate()


@pytest.fixture()
def make_studio(tmp_path):
    made = []

    def _make(pick_kind=None):
        s = Studio(tmp_path, pick_kind)
        made.append(s)
        return s

    yield _make
    for s in made:
        s.stop()


def _open(browser, st, hash_="#/tables?tab=reqs"):
    page = browser.new_context().new_page()
    page.goto(st.url + "/" + hash_)
    page.wait_for_load_state("networkidle")
    return page


def _btn(page):
    return page.get_by_test_id("repo-pick")


# FR-010 AC-332
def test_ac332_repo_button_has_folder_icon_and_click_opens_picker_not_text_modal(browser, make_studio):
    st = make_studio("cancel")
    page = _open(browser, st)
    expect(_btn(page)).to_be_visible()
    assert _btn(page).evaluate("e => e.id") == "repoBtn"
    assert _btn(page).locator("svg, img, [class*=icon]").count() >= 1  # folder icon
    with page.expect_request(lambda r: r.url.endswith("/api/repo/pick") and r.method == "POST"):
        _btn(page).click()
    page.wait_for_timeout(300)
    assert page.locator("dialog[open], [role=dialog], .modal").count() == 0
    assert page.evaluate("() => !document.querySelector('[role=dialog] input, dialog[open] input, .modal input')")


# FR-010 AC-332 (keyboard only)
@pytest.mark.parametrize("key", ["Enter", "Space"])
def test_ac332_repo_button_is_operable_by_keyboard_only(browser, make_studio, key):
    st = make_studio("cancel")
    page = _open(browser, st)
    _btn(page).focus()
    assert page.evaluate("() => document.activeElement.id") == "repoBtn"
    with page.expect_request(lambda r: r.url.endswith("/api/repo/pick") and r.method == "POST"):
        page.keyboard.press(key)


# FR-010 AC-333
def test_ac333_picking_other_repo_switches_and_clears_selection_filter_search(browser, make_studio):
    st = make_studio("b")
    page = _open(browser, st)
    page.locator("input[type=search]").first.fill("FR-003")
    page.locator("#view tbody tr").filter(has_text="FR-003").first.locator("td").last.click()
    expect(page.locator("#repoBtn")).to_contain_text("std")
    expect(page.locator("#view")).to_contain_text("画面表示のみ")
    _btn(page).click()
    expect(page.locator("#repoBtn")).to_contain_text("oth")
    assert st.repo() == "oth"
    expect(page.locator("#view")).to_contain_text("ほげ")
    expect(page.locator("body")).not_to_contain_text("画面表示のみ")
    expect(page.locator("body")).not_to_contain_text("注文登録")
    h = page.evaluate("() => location.hash")
    assert "select=FR-003" not in h and "q=FR-003" not in h
    assert page.locator("input[type=search]").first.input_value() == ""
    expect(page.locator("#drawer")).not_to_contain_text("画面表示のみ")


# FR-010 AC-333 (other views are also refreshed)
@pytest.mark.parametrize("view", ["#/dashboard", "#/map2d", "#/entities"])
def test_ac333_other_views_show_new_repo_content_after_switch(browser, make_studio, view):
    st = make_studio("b")
    page = _open(browser, st, view)
    _btn(page).click()
    expect(page.locator("#repoBtn")).to_contain_text("oth")
    page.wait_for_load_state("networkidle")
    expect(page.locator("body")).not_to_contain_text("画面表示のみ")
    expect(page.locator("body")).not_to_contain_text("注文登録")


# FR-010 AC-334
def test_ac334_cancel_changes_nothing_and_shows_no_error(browser, make_studio):
    st = make_studio("cancel")
    page = _open(browser, st)
    box = page.locator("input[type=search]").first
    box.fill("FR-003")
    page.locator("#view tbody tr").filter(has_text="FR-003").first.locator("td").last.click()
    before_hash = page.evaluate("() => location.hash")
    before_view = page.locator("#view").inner_text()
    with page.expect_response(lambda r: r.url.endswith("/api/repo/pick")) as ri:
        _btn(page).click()
    assert ri.value.status == 200 and ri.value.json() == {"path": ""}
    page.wait_for_timeout(500)
    expect(page.locator("#repoBtn")).to_contain_text("std")
    assert st.repo() == "std"
    assert page.evaluate("() => location.hash") == before_hash
    assert box.input_value() == "FR-003"
    assert page.locator("#view").inner_text() == before_view
    assert page.locator("[role=alert], .error, .toast-error, .banner-error").filter(visible=True).count() == 0


# FR-010 AC-335 (abnormal: no management data)
@pytest.mark.parametrize("kind", ["plain", "missing"])
def test_ac335_unusable_folder_keeps_model_and_shows_cause_and_actions(browser, make_studio, kind):
    st = make_studio(kind)
    page = _open(browser, st)
    _btn(page).click()
    page.wait_for_timeout(800)
    expect(page.locator("#repoBtn")).to_contain_text("std")
    assert st.repo() == "std"
    expect(page.locator("#view")).to_contain_text("画面表示のみ")
    alert = page.locator("[role=alert], .error, .state-error, .banner-error").filter(visible=True)
    assert alert.count() >= 1
    text = alert.first.inner_text()
    assert text.strip() != ""
    assert page.get_by_role("button", name="再試行").count() >= 1
    assert page.get_by_role("button", name="元へ戻る").count() >= 1 or page.get_by_role("button", name="戻る").count() >= 1


# FR-010 AC-335 (abnormal: dialog cannot be opened)
def test_ac335_picker_unavailable_keeps_model_and_shows_cause_and_actions(browser, make_studio):
    st = make_studio(None)
    page = _open(browser, st)
    page.route("**/api/repo/pick", lambda route: route.fulfill(
        status=501, content_type="application/json", body=json.dumps({"error": "picker-unavailable"})))
    _btn(page).click()
    page.wait_for_timeout(800)
    expect(page.locator("#repoBtn")).to_contain_text("std")
    assert st.repo() == "std"
    expect(page.locator("#view")).to_contain_text("画面表示のみ")
    alert = page.locator("[role=alert], .error, .state-error, .banner-error").filter(visible=True)
    assert alert.count() >= 1 and alert.first.inner_text().strip() != ""
    assert page.get_by_role("button", name="再試行").count() >= 1


# FR-010 AC-336 (contract: header + host)
def test_ac336_pick_without_identification_header_is_rejected_and_repo_unchanged(make_studio):
    st = make_studio("b")
    status, _ = st.post("/api/repo/pick")
    assert status == 403
    status, _ = st.post("/api/repo/pick", headers={"X-EABK-Studio": "0"})
    assert status == 403
    assert st.repo() == "std"


# FR-010 AC-336 (abnormal: non-local Host)
@pytest.mark.parametrize("host", ["evil.example.com", "192.0.2.10:8080", "evil.example.com:80"])
def test_ac336_pick_with_non_local_host_is_rejected_and_repo_unchanged(make_studio, host):
    st = make_studio("b")
    status, _ = st.post("/api/repo/pick", headers=HDR, host=host)
    assert status == 403
    assert st.repo() == "std"


# FR-010 AC-336 (normal: local + header is accepted and returns the selection; selection alone does not switch)
def test_ac336_pick_from_local_with_header_returns_selected_path_only(make_studio):
    st = make_studio("b")
    status, data = st.post("/api/repo/pick", headers=HDR)
    assert status == 200
    assert Path(json.loads(data)["path"]) == st.b
    assert st.repo() == "std"
