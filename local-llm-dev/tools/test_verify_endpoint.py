#!/usr/bin/env python3
"""``verify_endpoint.py`` の Agent 厳格判定を固定する RED 契約テスト。

外部通信は行わず、標準ライブラリのローカル HTTP サーバーに対して CLI を
subprocess で実行する。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator, cast
from unittest.mock import patch

import verify_endpoint

MODEL_ID = "fixture-agent-model"
VERIFY_SCRIPT = Path(__file__).resolve().with_name("verify_endpoint.py")
PROCESS_TIMEOUT_SECONDS = 15


class _EndpointHandler(BaseHTTPRequestHandler):
    """OpenAI 互換の最小 fixture 応答を返す。"""

    server_version = "VerifyEndpointFixture/1.0"

    def log_message(self, _format: str, *args: object) -> None:
        """テスト出力へ HTTP アクセスログを混ぜない。"""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        server = cast(_FixtureServer, self.server)
        server.record("GET", self.path, None)

        if self.path == "/api/ps":
            context_length = 4096 if server.scenario == "context_mismatch" else 8192
            self._send_json(200, {
                "models": [{"name": MODEL_ID, "model": MODEL_ID, "context_length": context_length}],
            })
            return
        if self.path != "/v1/models":
            self._send_json(404, {"error": "not found"})
            return
        if server.scenario == "timeout_models":
            # クライアント側 timeout まで応答しない。sleep ではなく teardown の
            # Event で解放するため、CPU 速度やスケジューリングに依存しない。
            server.timeout_release.wait()
            return
        if server.scenario == "http_error_models":
            self._send_json(503, {"error": "fixture unavailable"})
            return

        self._send_json(200, {
            "object": "list",
            "data": [{"id": MODEL_ID, "object": "model"}],
        })

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        server = cast(_FixtureServer, self.server)
        body = self._read_json()
        server.record("POST", self.path, body)

        if self.path != "/v1/chat/completions":
            self._send_json(404, {"error": "not found"})
            return
        if body.get("stream") is True:
            self._send_bytes(
                200,
                b'data: {"choices":[{"delta":{"content":"1"}}]}\n\n'
                b"data: [DONE]\n\n",
                "text/event-stream",
            )
            return
        if "tools" in body:
            self._send_json(200, self._tool_call_response(server.scenario))
            return

        self._send_json(200, {
            "id": "chatcmpl-fixture",
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "OK"},
                "finish_reason": "stop",
            }],
        })

    def _read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    @staticmethod
    def _tool_call_response(scenario: str) -> dict[str, object]:
        if scenario == "missing_tool_calls":
            message: dict[str, object] = {
                "role": "assistant",
                "content": "The fixture intentionally returned no structured call.",
            }
        else:
            arguments = "{not-json" if scenario == "invalid_arguments" else json.dumps(
                {"city": "Tokyo"}, separators=(",", ":")
            )
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_fixture_1",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": arguments,
                    },
                }],
            }
        return {
            "id": "chatcmpl-tool-fixture",
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls",
            }],
        }

    def _send_json(self, status: int, value: object) -> None:
        payload = json.dumps(value, separators=(",", ":")).encode("utf-8")
        self._send_bytes(status, payload, "application/json")

    def _send_bytes(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            # timeout fixture でクライアントが先に切断するのは期待動作。
            pass


class _FixtureServer(ThreadingHTTPServer):
    """シナリオと受信履歴を保持するループバック専用サーバー。"""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, scenario: str) -> None:
        super().__init__(("127.0.0.1", 0), _EndpointHandler)
        self.scenario = scenario
        self.timeout_release = threading.Event()
        self.ready = threading.Event()
        self._records_lock = threading.Lock()
        self._records: list[tuple[str, str, dict[str, object] | None]] = []

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"

    def service_actions(self) -> None:
        # serve_forever のループへ入ったことを sleep なしで通知する。
        self.ready.set()

    def record(self, method: str, path: str, body: dict[str, object] | None) -> None:
        with self._records_lock:
            self._records.append((method, path, body))

    def probe_kinds(self) -> set[str]:
        kinds: set[str] = set()
        with self._records_lock:
            records = tuple(self._records)
        for method, path, body in records:
            if method == "GET" and path == "/v1/models":
                kinds.add("models")
            elif method == "GET" and path == "/api/ps":
                kinds.add("context")
            elif method == "POST" and path == "/v1/chat/completions" and body is not None:
                if body.get("stream") is True:
                    kinds.add("sse")
                elif "tools" in body:
                    kinds.add("tool_calls")
                else:
                    kinds.add("chat")
        return kinds


@contextmanager
def _serve_endpoint(scenario: str = "ok") -> Iterator[_FixtureServer]:
    server = _FixtureServer(scenario)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
    thread.start()
    if not server.ready.wait(timeout=2):
        server.server_close()
        raise RuntimeError("fixture HTTP server did not start")
    try:
        yield server
    finally:
        server.timeout_release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        if thread.is_alive():
            raise RuntimeError("fixture HTTP server did not stop")


def _subprocess_environment() -> dict[str, str]:
    env = os.environ.copy()
    for key in tuple(env):
        if key.casefold() in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}:
            env.pop(key)
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run_cli(
    server: _FixtureServer,
    *extra_args: str,
    request_timeout: int = 2,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(VERIFY_SCRIPT),
        "--url",
        server.base_url,
        "--model",
        MODEL_ID,
        "--timeout",
        str(request_timeout),
        *extra_args,
    ]
    return subprocess.run(
        command,
        cwd=VERIFY_SCRIPT.parent,
        env=_subprocess_environment(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=PROCESS_TIMEOUT_SECONDS,
        check=False,
    )


class VerifyEndpointCliContractTests(unittest.TestCase):
    """Chat 互換性を保ちながら Agent 厳格モードを追加する契約。"""

    @staticmethod
    def _details(result: subprocess.CompletedProcess[str], server: _FixtureServer) -> str:
        return (
            f"\nreturncode={result.returncode}"
            f"\nprobes={sorted(server.probe_kinds())}"
            f"\nstdout:\n{result.stdout}"
            f"\nstderr:\n{result.stderr}"
        )

    def _assert_all_probes(
        self,
        result: subprocess.CompletedProcess[str],
        server: _FixtureServer,
    ) -> None:
        self.assertTrue(
            {"models", "chat", "sse", "tool_calls"}.issubset(server.probe_kinds()),
            self._details(result, server),
        )

    def _assert_require_agent_was_processed(
        self,
        result: subprocess.CompletedProcess[str],
        server: _FixtureServer,
    ) -> None:
        combined = f"{result.stdout}\n{result.stderr}".casefold()
        self.assertNotIn("unrecognized arguments", combined, self._details(result, server))
        self.assertIn("tool_calls", server.probe_kinds(), self._details(result, server))

    def test_require_agent_accepts_valid_agent_response(self) -> None:
        with _serve_endpoint() as server:
            result = _run_cli(server, "--require-agent", "--expected-context", "8192")

        self._assert_require_agent_was_processed(result, server)
        self._assert_all_probes(result, server)
        self.assertIn("context", server.probe_kinds(), self._details(result, server))
        self.assertEqual(0, result.returncode, self._details(result, server))

    def test_expected_context_mismatch_is_failure(self) -> None:
        with _serve_endpoint("context_mismatch") as server:
            result = _run_cli(server, "--expected-context", "8192")

        self._assert_all_probes(result, server)
        self.assertIn("context", server.probe_kinds(), self._details(result, server))
        self.assertNotEqual(0, result.returncode, self._details(result, server))
        self.assertIn("4096", result.stdout, self._details(result, server))
        self.assertIn("8192", result.stdout, self._details(result, server))

    def test_missing_tool_calls_is_failure(self) -> None:
        with _serve_endpoint("missing_tool_calls") as server:
            result = _run_cli(server)

        self._assert_all_probes(result, server)
        self.assertNotEqual(0, result.returncode, self._details(result, server))
        self.assertIn("tool_calls", result.stdout, self._details(result, server))

    def test_require_agent_rejects_invalid_arguments(self) -> None:
        with _serve_endpoint("invalid_arguments") as server:
            result = _run_cli(server, "--require-agent")

        self._assert_require_agent_was_processed(result, server)
        self._assert_all_probes(result, server)
        self.assertNotEqual(0, result.returncode, self._details(result, server))
        self.assertIn("arguments", result.stdout.casefold(), self._details(result, server))

    def test_regular_mode_warns_but_accepts_invalid_arguments(self) -> None:
        with _serve_endpoint("invalid_arguments") as server:
            result = _run_cli(server)

        self._assert_all_probes(result, server)
        self.assertEqual(0, result.returncode, self._details(result, server))
        self.assertIn("[ warn ]", result.stdout.casefold(), self._details(result, server))
        self.assertIn("arguments", result.stdout.casefold(), self._details(result, server))

    def test_timeout_is_failure(self) -> None:
        with _serve_endpoint("timeout_models") as server:
            result = _run_cli(server, request_timeout=1)

        self.assertIn("models", server.probe_kinds(), self._details(result, server))
        self.assertNotEqual(0, result.returncode, self._details(result, server))
        combined = f"{result.stdout}\n{result.stderr}".casefold()
        self.assertTrue(
            "timeout" in combined or "タイムアウト" in combined,
            self._details(result, server),
        )

    def test_http_error_is_failure(self) -> None:
        with _serve_endpoint("http_error_models") as server:
            result = _run_cli(server)

        self.assertIn("models", server.probe_kinds(), self._details(result, server))
        self.assertNotEqual(0, result.returncode, self._details(result, server))
        self.assertIn("503", result.stdout, self._details(result, server))

    def test_request_uses_explicit_no_proxy_opener(self) -> None:
        class _Response:
            status = 200

            def __enter__(self) -> "_Response":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            @staticmethod
            def read() -> bytes:
                return b'{"data":[]}'

        with patch.object(
            verify_endpoint._no_proxy_opener,
            "open",
            return_value=_Response(),
        ) as no_proxy_open, patch(
            "urllib.request.urlopen",
            side_effect=AssertionError("environment proxy-aware urlopen must not be used"),
        ):
            status, body = verify_endpoint.request("http://127.0.0.1:11434/v1/models", timeout=1)

        self.assertEqual(200, status)
        self.assertEqual('{"data":[]}', body)
        no_proxy_open.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
