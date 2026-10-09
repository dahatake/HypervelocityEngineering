#!/usr/bin/env python3
"""Loopback-only, standard-library EABK Studio server.

FR-010 AC-010; FR-012 AC-012; FR-013 AC-013; NFR-SEC-001 AC-023;
NFR-SEC-002 AC-024; NFR-OPS-001 AC-026
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from eabk_model import build_model, management_paths

HOST = "127.0.0.1"
PORT = 8765
WEB_ROOT = Path(__file__).with_name("web")


class StudioState:
    def __init__(self, repo: Path):
        self.repo = repo.resolve()
        self.model = build_model(self.repo)

    def switch(self, value: str) -> dict:
        candidate = Path(value).expanduser().resolve()
        model = build_model(candidate)
        self.repo, self.model = candidate, model
        return model

    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        for path in management_paths(self.repo):
            if path.is_file():
                digest.update(str(path.relative_to(self.repo)).encode())
                digest.update(path.read_bytes())
        return digest.hexdigest()


def make_handler(state: StudioState):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

        def _trusted_host(self) -> bool:
            host = self.headers.get("Host", "").split(":", 1)[0].strip("[]").lower()
            return host in {"127.0.0.1", "localhost"}

        def guess_type(self, path: str) -> str:
            value = super().guess_type(path)
            if value.startswith(("text/", "application/javascript")):
                return value + "; charset=utf-8"
            return value

        def _json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _reject_host(self) -> bool:
            if self._trusted_host():
                return False
            self._json({"error": "Host is not loopback"}, HTTPStatus.FORBIDDEN)
            return True

        def do_GET(self) -> None:
            if self._reject_host():
                return
            path = urlparse(self.path).path
            if path == "/api/model":
                state.model = build_model(state.repo)
                self._json(state.model)
            elif path == "/api/fingerprint":
                self._json({"fingerprint": state.fingerprint()})
            elif path == "/api/repo":
                self._json({"repo": str(state.repo), "name": state.repo.name})
            else:
                super().do_GET()

        def do_POST(self) -> None:
            if self._reject_host():
                return
            if urlparse(self.path).path != "/api/repo":
                self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                value = json.loads(self.rfile.read(size).decode("utf-8"))
                model = state.switch(str(value["repo"]))
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._json(model)

        def log_message(self, format: str, *args: object) -> None:
            sys.stdout.write("%s - %s\n" % (self.address_string(), format % args))

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="EABK Studio")
    parser.add_argument("--repo", default=".", help="repository containing management data")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    state = StudioState(Path(args.repo))
    server = ThreadingHTTPServer((HOST, args.port), make_handler(state))
    url = f"http://{HOST}:{args.port}/"
    print(f"EABK Studio: {url} ({state.repo})", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
