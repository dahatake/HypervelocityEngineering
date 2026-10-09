#!/usr/bin/env python3
"""EABK Studio: local web viewer for the EABK data layer of any repository.

    python EABK-Studio/studio.py --repo <path-to-a-repo-that-uses-EABK>

Only the Python standard library is needed. The server listens on 127.0.0.1 only
and reads nothing but the EABK data files of the selected repository.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import eabk_model  # noqa: E402

WEB = HERE / "web"
MIME = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
    ".LICENSE": "text/plain; charset=utf-8",
}


class State:
    def __init__(self, root: Path):
        self.lock = threading.Lock()
        self.root = root
        self.cache: dict[str, tuple[str, bytes]] = {}

    def set_root(self, root: Path) -> None:
        with self.lock:
            self.root = root

    def model_bytes(self) -> bytes:
        with self.lock:
            root = self.root
            fp = eabk_model.fingerprint(root)
            hit = self.cache.get(str(root))
            if hit and hit[0] == fp:
                return hit[1]
            data = json.dumps(eabk_model.build_model(root), ensure_ascii=False).encode("utf-8")
            self.cache = {str(root): (fp, data)}
            return data

    def fingerprint(self) -> str:
        with self.lock:
            return str(self.root) + "#" + eabk_model.fingerprint(self.root)


STATE: State


class Handler(BaseHTTPRequestHandler):
    server_version = "EABKStudio/" + eabk_model.STUDIO_VERSION

    def log_message(self, fmt, *args):  # quiet
        pass

    def host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return host in ("127.0.0.1", "localhost", "::1")

    def send_bytes(self, body: bytes, ctype: str, status=HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, obj, status=HTTPStatus.OK) -> None:
        self.send_bytes(json.dumps(obj, ensure_ascii=False).encode("utf-8"), MIME[".json"], status)

    def do_GET(self) -> None:  # noqa: N802
        if not self.host_ok():
            return self.send_json({"error": "bad host"}, HTTPStatus.FORBIDDEN)
        path = urlparse(self.path).path
        if path == "/api/model":
            return self.send_bytes(STATE.model_bytes(), MIME[".json"])
        if path == "/api/fingerprint":
            return self.send_json({"fingerprint": STATE.fingerprint()})
        if path == "/api/repo":
            return self.send_json({"repo": str(STATE.root)})
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (WEB / rel).resolve()
        if WEB.resolve() not in target.parents or not target.is_file():
            return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        ctype = MIME.get(target.suffix, "application/octet-stream")
        self.send_bytes(target.read_bytes(), ctype)

    def do_POST(self) -> None:  # noqa: N802
        if not self.host_ok() or self.headers.get("X-EABK-Studio") != "1":
            return self.send_json({"error": "forbidden"}, HTTPStatus.FORBIDDEN)
        if urlparse(self.path).path != "/api/repo":
            return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(min(length, 8192)) or b"{}")
            raw = str(payload.get("path", "")).strip().strip('"')
        except (ValueError, TypeError):
            return self.send_json({"error": "bad request"}, HTTPStatus.BAD_REQUEST)
        p = Path(raw).expanduser()
        if not raw or not p.is_dir():
            return self.send_json({"error": "not-a-directory"}, HTTPStatus.BAD_REQUEST)
        root = eabk_model.find_root(p)
        files = eabk_model.load_config(root)
        if not any((root / files[k]).exists() for k in ("requirements", "catalog", "ledger")):
            return self.send_json({"error": "no-data-layer", "repo": str(root)}, HTTPStatus.UNPROCESSABLE_ENTITY)
        STATE.set_root(root)
        self.send_json({"repo": str(root)})


def main(argv=None) -> int:
    global STATE
    ap = argparse.ArgumentParser(description="EABK Studio - viewer for the EABK data layer")
    ap.add_argument("--repo", default=None, help="repository that uses EABK (default: current directory)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="do not open the browser")
    args = ap.parse_args(argv)
    if args.repo is not None:
        root = eabk_model.find_root(Path(args.repo))
    else:
        cwd_root = eabk_model.find_root(Path.cwd())
        files = eabk_model.load_config(cwd_root)
        has_data = any((cwd_root / files[k]).exists() for k in ("requirements", "catalog", "ledger"))
        root = cwd_root if has_data else eabk_model.find_root(HERE.parent)
    STATE = State(root)
    srv = None
    for port in range(args.port, args.port + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if srv is None:
        print("no free port", file=sys.stderr)
        return 1
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"EABK Studio {eabk_model.STUDIO_VERSION}\n  repo: {root}\n  url : {url}\n  (Ctrl+C to stop)")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
