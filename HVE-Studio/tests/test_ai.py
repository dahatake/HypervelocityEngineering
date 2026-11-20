"""FR-1096..FR-1098, NFR-SEC-024: the generative-AI endpoints of HVE Studio, against a fake Azure OpenAI on 127.0.0.1.

AC-521 AC-522 AC-525..AC-527 AC-529 AC-530 AC-543..AC-545
"""
import http.client
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "tests" / "system"))
import ai  # noqa: E402
import entity_repo  # noqa: E402

KEY = "sk-TEST-SECRET-4711"
CANARY = "CANARY_7f3e_DO_NOT_SEND"
HDR = {"X-EABK-Studio": "1", "Content-Type": "application/json"}


class Fake:
    """A minimal Azure OpenAI chat-completions endpoint that records what it receives."""

    def __init__(self, answer):
        self.calls = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"])).decode()
                outer.calls.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
                if self.headers.get("api-key") != KEY:
                    self.send_response(401)
                    self.end_headers()
                    return
                data = json.dumps({"model": "fake-model", "choices": [{"message": {"content": answer}}], "usage": {"prompt_tokens": 120, "completion_tokens": 30}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"


def _snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*")
            if p.is_file() and ".git" not in p.parts}


@pytest.fixture()
def studio(tmp_path):
    repo = entity_repo.make_standard(tmp_path / "std")
    (repo / "src").mkdir()
    (repo / "src" / "orders.py").write_text(f"SECRET = '{CANARY}'\n", encoding="utf-8")
    (repo / "docs" / "catalog.md").write_text((repo / "docs" / "catalog.md").read_text(encoding="utf-8").replace(
        "| FR-001 | 題名 | 承認済み | 未実装 |", "| FR-001 | 題名 | 承認済み | `src/orders.py` |"), encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = dict(os.environ, HVE_STUDIO_SECRET_STORE="memory")
    log = tmp_path / "server.log"
    with open(log, "w", encoding="utf-8") as out:
        proc = subprocess.Popen([sys.executable, str(ROOT / "studio.py"), "--repo", str(repo), "--port", str(port), "--no-open",
                                 "--no-remote"], env=env, stdout=out, stderr=subprocess.STDOUT)
    end = time.time() + 15
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)

    def call(method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=HDR)
        r = c.getresponse()
        raw = r.read().decode("utf-8")
        c.close()
        return r.status, raw

    call("GET", "/api/model")
    yield {"call": call, "repo": repo, "log": log}
    proc.terminate()
    proc.wait(10)


def _cfg(fake):
    return {"provider": "azure", "auth": "key", "endpoint": fake.url, "deployment": "dep"}


# FR-1096 AC-543 AC-521 / NFR-SEC-024 AC-529: the key is saved, never echoed, and deletable
def test_ac543_key_is_saved_never_returned_and_deletable(studio):
    fake = Fake("ok")
    st, raw = studio["call"]("POST", "/api/ai/key", {"config": _cfg(fake), "key": KEY, "persist": True})
    assert st == 200 and KEY not in raw and json.loads(raw)["stored"] is True
    st, raw = studio["call"]("GET", f"/api/ai/status?provider=azure&endpoint={fake.url}")
    assert json.loads(raw)["stored"] is True and KEY not in raw
    st, raw = studio["call"]("POST", "/api/ai/test", {"config": _cfg(fake)})
    assert st == 200 and json.loads(raw)["ok"] is True and KEY not in raw
    assert fake.calls[-1]["headers"]["api-key"] == KEY
    st, raw = studio["call"]("POST", "/api/ai/key/delete", {"config": _cfg(fake)})
    assert json.loads(raw)["stored"] is False
    st, raw = studio["call"]("POST", "/api/ai/test", {"config": _cfg(fake)})
    assert st == 502 and json.loads(raw)["error"] == "auth-failed" and KEY not in raw
    assert KEY not in studio["log"].read_text(encoding="utf-8")


# NFR-SEC-024 AC-530: nothing is sent before consent; afterwards only allowed kinds, never code contents or source paths
def test_ac530_consent_first_and_no_code_or_paths_are_sent(studio):
    fake = Fake("FR-001 needs attention.")
    studio["call"]("POST", "/api/ai/key", {"config": _cfg(fake), "key": KEY, "persist": False})
    st, raw = studio["call"]("POST", "/api/ai/ask", {"config": _cfg(fake), "step": 3, "question": "impact?", "lang": "en"})
    assert st == 409 and json.loads(raw)["error"] == "consent-required" and not fake.calls
    studio["call"]("POST", "/api/ai/consent", {"repos": [str(studio["repo"])]})
    for step in range(1, 7):
        st, raw = studio["call"]("POST", "/api/ai/ask", {"config": _cfg(fake), "step": step, "question": "status?", "lang": "en",
                                                         "repos": [str(studio["repo"])]})
        assert st == 200, raw
    sent = " ".join(c["body"] for c in fake.calls)
    assert CANARY not in sent and "src/orders.py" not in sent and "orders.py" not in sent
    assert "FR-001" in sent and "std" in sent
    assert set(json.loads(raw)["sentKinds"]) == set(ai.SENT_KINDS)


# FR-1098 AC-525 AC-526 AC-527: derived answer with provider/model/time; unknown IDs flagged; invalid recommendation hidden;
# the repository is not written
def test_ac526_answer_checks_and_ac527_no_writes(studio):
    fake = Fake("FR-001 and FR-999 matter.\nRECOMMEND Q-001: B\nend")
    studio["call"]("POST", "/api/ai/key", {"config": _cfg(fake), "key": KEY, "persist": False})
    studio["call"]("POST", "/api/ai/consent", {"repos": [str(studio["repo"])]})
    before = _snapshot(studio["repo"])
    st, raw = studio["call"]("POST", "/api/ai/ask", {"config": _cfg(fake), "step": 2, "question": "q", "lang": "ja",
                                                     "repos": [str(studio["repo"])]})
    r = json.loads(raw)
    assert st == 200 and r["model"] == "fake-model" and r["provider"] == "azure" and r["at"]
    assert {i["id"]: i["known"] for i in r["ids"]} == {"FR-001": True, "FR-999": False, "Q-001": False}
    assert r["recommendations"] == [{"question": "Q-001", "option": None, "valid": False}]
    assert "Japanese" in fake.calls[-1]["body"]
    assert r["usage"] == {"inputTokens": 120, "outputTokens": 30, "estimated": False}   # FR-1101: the provider's counts
    assert _snapshot(studio["repo"]) == before


def test_ac526_recommendation_must_be_one_of_the_options():
    q = {"Q-020": {"id": "Q-020", "options": "A: 保存しない／B: OS の保管庫／C: ファイル"}}
    out = ai.check_answer("RECOMMEND Q-020: B\nRECOMMEND Q-020: D", {"Q-020"}, q)
    assert out["recommendations"] == [{"question": "Q-020", "option": "B", "valid": True},
                                      {"question": "Q-020", "option": None, "valid": False}]


# FR-1096 AC-544: without a usable vault the key cannot be saved, but can be used for this session only
def test_ac544_no_vault_means_session_only(monkeypatch):
    monkeypatch.setenv("HVE_STUDIO_SECRET_STORE", "none")
    keys = ai.Keys()
    with pytest.raises(ai.AIError) as e:
        keys.put("azure", "https://x.openai.azure.com", KEY, persist=True)
    assert e.value.code == "vault-unavailable"
    status = keys.put("azure", "https://x.openai.azure.com", KEY, persist=False)
    assert status["session"] is True and status["stored"] is False
    assert keys.get("azure", "https://x.openai.azure.com") == KEY


# FR-1096 AC-545: classic PATs are refused; the account and the token source come from `gh auth status`
def test_ac545_github_cli_token_rules(monkeypatch):
    outputs = {
        ("auth", "token"): subprocess.CompletedProcess([], 0, "ghp_classic\n", ""),
        ("auth", "status"): subprocess.CompletedProcess([], 0, "", "github.com\n  ✓ Logged in to github.com account octo (GH_TOKEN)\n  - Active account: true\n"),
    }
    monkeypatch.setattr(ai, "_tool", lambda name, args, timeout=30: outputs[tuple(args[:2])])
    with pytest.raises(ai.AIError) as e:
        ai.github_token()
    assert e.value.code == "unsupported-token"
    assert ai.github_status() == {"account": "octo", "tokenSource": "env"}
    outputs[("auth", "token")] = subprocess.CompletedProcess([], 0, "gho_abc\n", "")
    assert ai.github_token() == "gho_abc"


# FR-1096: only https endpoints (loopback http is allowed for local providers and tests)
def test_endpoint_must_be_https():
    with pytest.raises(ai.AIError):
        ai.check_config({"provider": "azure", "auth": "key", "endpoint": "http://example.com"})
    assert ai.check_config({"provider": "azure", "auth": "key", "endpoint": "https://a.openai.azure.com/"})["endpoint"] == "https://a.openai.azure.com"

# FR-1096 AC-521 / 3.1: a missing Copilot SDK is reported with how to install it; nothing is installed automatically
def test_missing_copilot_sdk_is_reported_not_installed(monkeypatch):
    monkeypatch.setattr(ai, "copilot_available", lambda: False)
    with pytest.raises(ai.AIError) as e:
        ai.chat({"provider": "copilot", "auth": "gh", "model": "gpt-5"}, ai.Keys(), [{"role": "user", "content": "x"}])
    assert e.value.code == "missing-component" and "pip install microsoft-copilot-sdk" in e.value.action


# FR-1101 AC-547: no counts from the provider -> 4 characters = 1 token, marked as an estimate
def test_ac547_usage_is_estimated_when_the_provider_returns_no_counts():
    u = ai.estimate_usage([{"role": "system", "content": "a" * 40}, {"role": "user", "content": "b" * 41}], "c" * 8)
    assert u == {"inputTokens": 21, "outputTokens": 2, "estimated": True}
