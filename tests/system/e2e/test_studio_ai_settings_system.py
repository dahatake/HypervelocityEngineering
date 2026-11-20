"""System tests for FR-1096 AC-520 and NFR-SEC-024 AC-528 (HVE Studio: generative-AI settings and silence when AI is off).

AC-520: choosing a provider and an authentication method shows only the fields and information of that combination
(Azure/Key: endpoint, deployment, key; Azure/Entra ID: sign-in state and the subscription -> resource -> deployment lists,
no endpoint or key; Copilot SDK/GitHub CLI: sign-in state and model, no key; Copilot SDK/Key (BYOK): provider type,
endpoint, key, model). "Do not use AI" shows no field.
AC-528: with AI unset and with "Do not use AI", going through every screen of the six steps makes no request to an AI
provider, Azure Resource Manager or GitHub Copilot, from the browser or the server; without credentials, SDK or CLI the
rest of Studio works and "Ask AI" says "not set" with a way to the settings; the server listens only on 127.0.0.1.
"""
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import expect

from entity_repo import make_standard

ROOT = Path(__file__).resolve().parents[3]
STUDIO = ROOT / "HVE-Studio" / "studio.py"
SERVER_CALLS_OUT = ("/api/ai/test", "/api/ai/ask", "/api/ai/resources", "/api/ai/signin")   # the only ways the server goes out for AI


class Recorder:
    """Stands in as HTTP(S)_PROXY for the server: any outgoing HTTP(S) request of the server would arrive here."""

    def __init__(self):
        self.hits = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _any(self):
                outer.hits.append((self.command, self.path))
                self.send_response(502)
                self.end_headers()
            do_GET = do_POST = do_CONNECT = _any

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"


@pytest.fixture()
def studio(tmp_path):
    repo = make_standard(tmp_path / "std")
    rec = Recorder()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = dict(os.environ, HTTP_PROXY=rec.url, HTTPS_PROXY=rec.url, NO_PROXY="127.0.0.1,localhost",
               PATH=str(Path(sys.executable).parent))   # no az, no gh: credentials, SDK and CLI are absent
    for k in ("GH_TOKEN", "GITHUB_TOKEN", "AZURE_OPENAI_API_KEY"):
        env.pop(k, None)
    proc = subprocess.Popen([sys.executable, str(STUDIO), "--repo", str(repo), "--port", str(port), "--no-open", "--no-remote"],
                            cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    end = time.time() + 15
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield {"url": f"http://127.0.0.1:{port}/", "rec": rec, "proc": proc}
    proc.terminate()
    proc.wait(10)


def _open(browser, url):
    page = browser.new_context(viewport={"width": 1400, "height": 900}).new_page()
    page.goto(url)
    page.wait_for_selector("#splash[hidden]", state="attached", timeout=30000)
    page.wait_for_load_state("networkidle")
    return page


def _settings(page):
    page.get_by_test_id("ai-settings-btn").click()
    page.wait_for_selector('[data-testid="ai-settings"]')
    return page.get_by_test_id("ai-settings")


def _fields(dialog):
    return set(dialog.locator("[data-field]").evaluate_all("els => els.map(e => e.dataset.field)"))


# FR-1096 AC-520
def test_ac520_each_combination_shows_only_its_fields(browser, studio):
    page = _open(browser, studio["url"])
    dialog = _settings(page)
    assert _fields(dialog) == set()                       # "Do not use AI"
    page.get_by_test_id("ai-provider-azure").check()
    page.get_by_test_id("ai-auth-key").check()
    assert _fields(dialog) == {"endpoint", "deployment", "key"}
    page.get_by_test_id("ai-auth-entra").check()
    assert _fields(dialog) == {"signin"}
    assert dialog.locator('[data-testid="ai-field-endpoint"], [data-testid="ai-field-key"], input[type=password]').count() == 0
    expect(page.get_by_test_id("ai-signin")).not_to_have_text("")   # sign-in state (here: the Azure CLI is missing)
    page.get_by_test_id("ai-provider-copilot").check()
    page.get_by_test_id("ai-auth-gh").check()
    assert _fields(dialog) == {"signin", "model"}
    assert dialog.locator('[data-testid="ai-field-key"], input[type=password]').count() == 0
    page.get_by_test_id("ai-auth-byok").check()
    assert _fields(dialog) == {"byokType", "endpoint", "key", "model"}
    page.get_by_test_id("ai-provider-off").check()
    assert _fields(dialog) == set()


def _walk_every_screen(page):
    for n in range(1, 7):
        page.locator(f'[data-testid="step"][data-step="{n}"]').click()
        page.wait_for_selector(f'[data-testid="step"][data-step="{n}"][aria-current="step"]')
        for i in range(page.locator("#nav a").count()):
            page.locator("#nav a").nth(i).click()
            page.wait_for_load_state("networkidle")


# NFR-SEC-024 AC-528
@pytest.mark.parametrize("setting", ["unset", "off"])
def test_ac528_no_ai_traffic_when_unset_or_off_and_everything_else_works(browser, studio, setting):
    page = _open(browser, studio["url"])
    origin = studio["url"].rstrip("/")
    if setting == "off":
        _settings(page)
        page.get_by_test_id("ai-provider-off").check()
        page.get_by_test_id("ai-settings-close").click()
    requests = []
    page.on("request", lambda r: requests.append(r.url))
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _walk_every_screen(page)
    page.get_by_test_id("ai-ask").click()
    expect(page.get_by_test_id("ai-unset")).to_be_visible()
    expect(page.get_by_test_id("ai-panel").get_by_role("button", name="AI を設定する")).to_be_visible()
    page.locator("#q").fill("FR-001")       # the rest keeps working
    expect(page.locator("#results")).to_contain_text("FR-001")
    outside = [u for u in requests if not u.startswith(origin) and not u.startswith("data:")]
    assert outside == []
    assert not [u for u in requests if any(p in u for p in SERVER_CALLS_OUT)]
    assert studio["rec"].hits == []
    assert errors == []
    out = studio["proc"].stdout
    assert out is not None
    with socket.socket() as s:       # listening only on 127.0.0.1 (PARAM-002)
        s.settimeout(0.5)
        host = socket.gethostbyname(socket.gethostname())
        port = int(studio["url"].rsplit(":", 1)[1].strip("/"))
        if host != "127.0.0.1":
            assert s.connect_ex((host, port)) != 0

# NFR-UX-019 AC-531: before using the AI, "Ask AI" says what the AI can do, what it cannot do and that it can be wrong
def test_ac531_capabilities_are_stated_before_use(browser, studio):
    page = _open(browser, studio["url"])
    page.get_by_test_id("ai-ask").click()
    intro = page.get_by_test_id("ai-intro").inner_text()
    assert "できること" in intro and "できないこと" in intro and "誤りうること" in intro
    page.locator('#lang [data-lang="en"]').click()
    intro = page.get_by_test_id("ai-intro").inner_text()
    assert "Can:" in intro and "Cannot:" in intro and "May be wrong:" in intro
