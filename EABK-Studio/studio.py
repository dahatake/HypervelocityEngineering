#!/usr/bin/env python3
"""EABK Studio: local web viewer for the EABK data layer of any repository.

    python EABK-Studio/studio.py --repo <path-to-a-repo-that-uses-EABK>

Only the Python standard library is needed. The server listens on 127.0.0.1.
Normal viewing is read-only; an explicit maintenance confirmation can update
the title and decision-state columns of docs/catalog.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
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
        self.previews: dict[str, dict] = {}
        self.catalog_baseline = self._catalog_hash(root)

    @staticmethod
    def _catalog_hash(root: Path) -> str:
        catalog = root / eabk_model.load_config(root)["catalog"]
        return hashlib.sha256(catalog.read_bytes()).hexdigest() if catalog.is_file() else ""

    def set_root(self, root: Path) -> None:
        with self.lock:
            self.root = root
            self.previews.clear()
            self.catalog_baseline = self._catalog_hash(root)

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

    @staticmethod
    def _catalog_update(root: Path, requirement_id: str) -> dict:
        model = eabk_model.build_model(root)
        reqs = [item for item in model["reqs"] if item["id"] == requirement_id]
        features = [item for item in model["catalog"]["features"] if item["req"] == requirement_id]
        if len(reqs) != 1 or len(features) != 1:
            code = "unsupported" if not reqs else "invalid-input"
            raise MaintenanceError(code, "unsupported requirement" if code == "unsupported" else "input condition is not unique")

        catalog_rel = model["meta"]["files"]["catalog"]
        catalog = (root / catalog_rel).resolve()
        if root.resolve() not in catalog.parents or not catalog.is_file():
            raise MaintenanceError("unsupported", "catalog is outside the repository or missing")
        original = catalog.read_bytes()
        text = original.decode("utf-8")
        lines = text.splitlines(keepends=True)
        line_index = features[0]["line"] - 1
        if line_index < 0 or line_index >= len(lines):
            raise MaintenanceError("invalid-input", "catalog row position is invalid")

        header_index = line_index - 2
        if header_index < 0:
            raise MaintenanceError("invalid-input", "catalog table header is missing")
        headers = [cell.strip() for cell in lines[header_index].strip().strip("|").split("|")]
        normalized = [re.sub(r"\s+", "", header) for header in headers]
        try:
            id_index = normalized.index("要求ID")
            title_index = normalized.index("題名")
            status_index = normalized.index("決定状態")
        except ValueError as exc:
            raise MaintenanceError("unsupported", "catalog columns are unsupported") from exc

        cells = [cell.strip() for cell in lines[line_index].strip().strip("|").split("|")]
        if len(cells) != len(headers) or cells[id_index] != requirement_id:
            raise MaintenanceError("invalid-input", "catalog row does not match the preview target")
        req = reqs[0]
        before_title, before_status = cells[title_index], cells[status_index]
        cells[title_index], cells[status_index] = req["title"], req["status"]
        newline = "\r\n" if lines[line_index].endswith("\r\n") else "\n"
        lines[line_index] = "| " + " | ".join(cells) + " |" + newline
        updated = "".join(lines).encode("utf-8")
        if updated == original:
            raise MaintenanceError("unsupported", "catalog row is already consistent")
        return {
            "id": requirement_id,
            "path": catalog_rel,
            "catalog": catalog,
            "original": original,
            "updated": updated,
            "original_sha256": hashlib.sha256(original).hexdigest(),
            "before_title": before_title,
            "after_title": req["title"],
            "before_status": before_status,
            "after_status": req["status"],
        }

    def maintenance_preview(self, requirement_id: str) -> dict:
        with self.lock:
            try:
                preview = self._catalog_update(self.root, requirement_id)
                if self.catalog_baseline:
                    preview["original_sha256"] = self.catalog_baseline
            except MaintenanceError:
                raise
            token = hashlib.sha256(
                (str(self.root) + requirement_id + preview["original_sha256"] + str(os.urandom(16))).encode("utf-8")
            ).hexdigest()
            preview["root"] = self.root
            self.previews[token] = preview
            return {
                "token": token,
                "id": requirement_id,
                "path": preview["path"],
                "changes": [
                    {"column": "題名", "before": preview["before_title"], "after": preview["after_title"]},
                    {"column": "決定状態", "before": preview["before_status"], "after": preview["after_status"]},
                ],
                "verify": "python scripts/verify.py --docs-only",
            }

    def maintenance_apply(self, token: str) -> dict:
        with self.lock:
            preview = self.previews.pop(token, None)
            if not preview or preview["root"] != self.root:
                raise MaintenanceError("invalid-input", "preview token is invalid")
            catalog: Path = preview["catalog"]
            current = catalog.read_bytes()
            if hashlib.sha256(current).hexdigest() != preview["original_sha256"]:
                raise MaintenanceError("preview-conflict", "catalog changed after preview")
            mode = catalog.stat().st_mode
            if not mode & stat.S_IWRITE:
                raise MaintenanceError("write-error", "catalog is read-only")
            for path in self.root.rglob("*"):
                if path.is_file() and path != catalog:
                    try:
                        if os.path.samefile(path, catalog):
                            raise MaintenanceError("outside-preview", f"{path.relative_to(self.root)} aliases catalog")
                    except OSError:
                        continue

            before = catalog.stat()
            temp_name = None
            try:
                with tempfile.NamedTemporaryFile("wb", dir=catalog.parent, prefix=".eabk-studio-", delete=False) as handle:
                    temp_name = handle.name
                    handle.write(preview["updated"])
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, catalog)
                temp_name = None
                verify = self.root / "scripts" / "verify.py"
                if verify.is_file():
                    result = subprocess.run(
                        [sys.executable, str(verify), "--docs-only"],
                        cwd=self.root,
                        capture_output=True,
                        text=True,
                        timeout=120,
                        check=False,
                    )
                    if result.returncode:
                        raise MaintenanceError("verify-failure", (result.stdout + result.stderr).strip())
                else:
                    eabk_model.build_model(self.root)
            except MaintenanceError:
                catalog.write_bytes(current)
                os.chmod(catalog, stat.S_IMODE(before.st_mode))
                os.utime(catalog, ns=(before.st_atime_ns, before.st_mtime_ns))
                raise
            except (OSError, subprocess.SubprocessError) as exc:
                if catalog.exists():
                    catalog.write_bytes(current)
                    os.chmod(catalog, stat.S_IMODE(before.st_mode))
                    os.utime(catalog, ns=(before.st_atime_ns, before.st_mtime_ns))
                raise MaintenanceError("write-error", str(exc)) from exc
            finally:
                if temp_name:
                    Path(temp_name).unlink(missing_ok=True)
            self.cache.clear()
            self.catalog_baseline = hashlib.sha256(preview["updated"]).hexdigest()
            return {"exit": 0, "message": "applied bytes match preview / preview と一致", "path": preview["path"]}


class MaintenanceError(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


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
        endpoint = urlparse(self.path).path
        if endpoint not in ("/api/repo", "/api/maintenance/preview", "/api/maintenance/apply"):
            return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(min(length, 8192)) or b"{}")
        except (ValueError, TypeError):
            return self.send_json({"error": "bad request"}, HTTPStatus.BAD_REQUEST)
        if endpoint.startswith("/api/maintenance/"):
            try:
                if endpoint.endswith("/preview"):
                    result = STATE.maintenance_preview(str(payload.get("id", "")).strip())
                else:
                    result = STATE.maintenance_apply(str(payload.get("token", "")).strip())
                return self.send_json(result)
            except MaintenanceError as exc:
                return self.send_json(
                    {"error": exc.code, "detail": exc.detail, "restored": True},
                    HTTPStatus.CONFLICT if exc.code == "preview-conflict" else HTTPStatus.UNPROCESSABLE_ENTITY,
                )
        raw = str(payload.get("path", "")).strip().strip('"')
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
