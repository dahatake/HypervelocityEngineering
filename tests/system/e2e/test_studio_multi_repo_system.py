"""System test for FR-1099 AC-536 (HVE Studio: repositories that make up one application).

AC-536: from the header's repository controls, repositories are added one by one with the OS folder dialog (the same
mechanism as FR-010; EABK_STUDIO_PICK_PATH replaces the dialog in tests) and removed from the list; the list shows each
repository's name, path, mode (management data / code mode) and loading state; at most PARAM-069 = 10; the same path is
rejected with a reason; one failing repository does not hide the others and shows its cause and a retry; the set of
paths (only) is kept per browser and restored on the next start; cancelling the dialog changes nothing.
"""
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect

from entity_repo import make_other, make_standard

ROOT = Path(__file__).resolve().parents[3]
STUDIO = ROOT / "HVE-Studio" / "studio.py"
HDR = {"X-EABK-Studio": "1", "Content-Type": "application/json"}


class Studio:
    def __init__(self, repo, pick, port=None):
        if port is None:
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
        self.port = port
        self.repo = repo
        self.start(pick)

    def start(self, pick):
        env = dict(os.environ)
        env.pop("EABK_STUDIO_PICK_PATH", None)
        if pick is not None:
            env["EABK_STUDIO_PICK_PATH"] = str(pick)
        self.proc = subprocess.Popen([sys.executable, str(STUDIO), "--repo", str(self.repo), "--port", str(self.port), "--no-open",
                                      "--no-remote"], cwd=self.repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        end = time.time() + 15
        while time.time() < end:
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                return
            except OSError:
                time.sleep(0.1)

    def stop(self):
        self.proc.terminate()
        self.proc.wait(10)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/"

    def post(self, path, body):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        c.request("POST", path, body=json.dumps(body), headers=HDR)
        r = c.getresponse()
        data = json.loads(r.read() or b"{}")
        c.close()
        return r.status, data


@pytest.fixture()
def repos(tmp_path):
    a = make_standard(tmp_path / "std")
    b = make_other(tmp_path / "oth")
    return a, b, tmp_path


def _open(context, url, route="#/tables?tab=reqs"):
    page = context.new_page()
    page.goto(url + route)
    page.wait_for_selector("#splash[hidden]", state="attached", timeout=30000)
    page.wait_for_load_state("networkidle")
    return page


def _rows(page):
    page.get_by_test_id("repo-list-open").click()
    page.wait_for_selector('[data-testid="repo-row"]')
    rows = page.locator('[data-testid="repo-row"]').evaluate_all(
        "els => els.map(e => ({path: e.dataset.path, status: e.dataset.status, text: e.innerText}))")
    page.keyboard.press("Escape")
    return rows


# FR-1099 AC-536 (add, list, duplicate, persistence and restore, cancel)
def test_ac536_add_list_duplicate_restore_and_cancel(browser, repos):
    a, b, _ = repos
    st = Studio(a, b)
    try:
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = _open(context, st.url)
        page.get_by_test_id("repo-add").click()
        expect(page.locator("#repoListBtn")).to_contain_text("2")
        rows = _rows(page)
        assert [Path(r["path"]) for r in rows] == [a, b]
        assert all(r["status"] == "loaded" for r in rows)
        assert "std" in rows[0]["text"] and "oth" in rows[1]["text"] and "管理データ" in rows[0]["text"]
        assert str(b) in rows[1]["text"]
        page.get_by_test_id("repo-add").click()          # the same path again
        expect(page.locator("#toast")).to_contain_text("すでに一覧")
        expect(page.locator("#repoListBtn")).to_contain_text("2")
        saved = json.loads(page.evaluate("() => localStorage.getItem('eabk-studio.repos')"))
        assert [Path(p) for p in saved] == [a, b] and all(isinstance(p, str) for p in saved)
        st.stop()
        st.start(None)                                     # next start: the server opens only `a` ...
        page.reload()
        page.wait_for_selector("#splash[hidden]", state="attached", timeout=30000)
        expect(page.locator("#repoListBtn")).to_contain_text("2")   # ... and the browser restores the group
        st.stop()
        st.start("")                                       # cancel: nothing changes, no error
        page.reload()
        page.wait_for_selector("#splash[hidden]", state="attached", timeout=30000)
        expect(page.locator("#repoListBtn")).to_contain_text("2")
        page.get_by_test_id("repo-add").click()
        page.wait_for_timeout(500)
        expect(page.locator("#repoListBtn")).to_contain_text("2")
        assert page.locator("#toast:not([hidden])").count() == 0
        rows = _rows(page)                                 # removing from the list
        page.get_by_test_id("repo-list-open").click()
        page.locator(f'[data-testid="repo-row"][data-path="{rows[1]["path"]}"] [data-testid="repo-remove"]'.replace("\\", "\\\\")).click()
        expect(page.locator("#repoListBtn")).to_contain_text("1")
        assert [Path(p) for p in json.loads(page.evaluate("() => localStorage.getItem('eabk-studio.repos')"))] == [a]
    finally:
        st.stop()


# FR-1099 AC-536 (limit PARAM-069 and one failing repository)
def test_ac536_limit_and_partial_failure(browser, repos):
    a, b, tmp = repos
    extra = [make_other(tmp / f"r{i}") for i in range(10)]
    st = Studio(a, None)
    try:
        status, data = st.post("/api/repos/restore", {"paths": [str(a)] + [str(x) for x in extra]})
        assert status == 200 and len(data["repos"]) == 10
        assert [s["error"] for s in data["skipped"]] == ["limit"]
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = _open(context, st.url)
        expect(page.locator("#repoListBtn")).to_contain_text("10")
        shutil.rmtree(extra[0])                            # this one now fails to load
        page.reload()
        page.wait_for_selector("#splash[hidden]", state="attached", timeout=60000)
        rows = _rows(page)
        failed = [r for r in rows if r["status"] == "error"]
        assert len(failed) == 1 and Path(failed[0]["path"]) == extra[0]
        assert "folder not found" in failed[0]["text"]
        assert sum(r["status"] == "loaded" for r in rows) == 9
        page.get_by_test_id("repo-list-open").click()
        assert page.locator('[data-testid="repo-row"][data-status="error"] [data-testid="repo-retry"]').count() == 1
        expect(page.locator("#view")).to_contain_text("std:FR-001")   # the others are still shown
    finally:
        st.stop()

def _w(p, s):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


# FR-1100 AC-540 AC-539: step 3 opens "relations between repositories": repositories as nodes, kinds and counts on the
# edges, the evidence of an edge with both code locations, candidates hidden until asked for and then told apart by words
def test_ac540_relations_diagram_between_repositories(browser, repos):
    a, _, tmp = repos
    api, shared = tmp / "api", tmp / "shared"
    _w(shared / "pyproject.toml", '[project]\nname = "shared-lib"\n')
    _w(shared / "shared_lib" / "__init__.py", "")
    _w(shared / "shared_lib" / "pricing.py", "def compute_total(rows):\n    return 1\n")
    _w(shared / "db" / "001.sql", "CREATE TABLE orders (id int);\n")
    _w(api / "pyproject.toml", '[project]\nname = "orders-api"\ndependencies = ["shared-lib"]\n')
    _w(api / "main.py", "from shared_lib.pricing import compute_total\n\ndef run(db):\n    db.execute('SELECT * FROM orders')\n    return compute_total([])\n")
    for r in (api, shared):
        subprocess.run(["git", "init", "-q"], cwd=r, check=True)
        subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    st = Studio(a, None)
    try:
        status, _ = st.post("/api/repos/restore", {"paths": [str(a), str(api), str(shared)]})
        assert status == 200
        page = _open(browser.new_context(viewport={"width": 1400, "height": 900}), st.url, "#/dashboard")
        page.locator('[data-testid="step"][data-step="3"]').click()
        page.locator('#nav a[data-nav="source"]').click()
        page.get_by_test_id("src-tab-repos").click()
        page.wait_for_selector('[data-testid="xr-diagram"] [data-edge]', timeout=60000)
        assert set(page.locator('[data-testid="xr-diagram"] [data-repo]').evaluate_all("e => e.map(x => x.dataset.repo)")) == {"std", "api", "shared"}
        edge = page.locator('[data-testid="xr-diagram"] [data-edge="api→shared"]')
        label = edge.get_attribute("aria-label")
        assert "パッケージの依存 1" in label and "関数の呼出し 1" in label and "候補" not in label
        edge.focus()
        page.keyboard.press("Enter")
        rows = page.locator('[data-testid="xr-row"]')
        assert rows.count() == 2 and "api:main.py:5" in page.get_by_test_id("xr-table").inner_text()
        page.get_by_test_id("xr-candidates").check()
        page.locator('[data-testid="xr-diagram"] [data-edge="api→shared"]').click()
        assert page.locator('[data-testid="xr-row"][data-certainty="candidate"]').count() == 1
        assert "候補" in page.locator('[data-testid="xr-row"][data-certainty="candidate"]').inner_text()
    finally:
        st.stop()
