#!/usr/bin/env python3
"""HVE Studio: local web viewer for the EABK data layer of any repository.

    python HVE-Studio/studio.py --repo <path-to-any-repo>   # with EABK: data layer; without: code mode

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
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.dont_write_bytecode = True  # do not leave __pycache__ in the repository being viewed
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import code_graph  # noqa: E402
import eabk_model  # noqa: E402
import floorplan_scan  # noqa: E402
import repo_scan  # noqa: E402
import remote_github  # noqa: E402
import managed_data  # noqa: E402
from task_state import TaskStore  # noqa: E402

WEB = HERE / "web"
# The toolkit source keeps the guide in users-guide/; installed repositories get it as EABK-docs/.
GUIDE = next((d + "/studio/01-first-steps.md" for d in ("EABK-docs", "users-guide") if (HERE.parent / d / "studio" / "01-first-steps.md").exists()), "EABK-docs/studio/01-first-steps.md")
# --role: first screen for each reader (same targets as the persona buttons in the header).
ROLE_ROUTES = {"pm": "#/dashboard", "architect": "#/map2d", "swe": "#/tables"}
MIME = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
    ".LICENSE": "text/plain; charset=utf-8",
}


class State:
    REMOTE_TTL = 600
    PARTIAL_FIRST = 1.0  # seconds before the first partial model is published (fast builds publish none)
    PARTIAL_INTERVAL = 5.0  # PARAM-065: minimum seconds between partial models

    def __init__(self, root: Path, data_dir: Path | None = None, remote: bool = False):
        self.lock = threading.Lock()
        self.root = root
        self.cache: dict[str, tuple[str, bytes]] = {}
        self.previews: dict[str, dict] = {}
        self.catalog_baseline = self._catalog_hash(root)
        self.tasks = TaskStore(data_dir)
        self.remote_enabled = remote
        self.remote: dict[str, dict] = {}  # in memory only; never written to disk
        self.remote_loading: set[str] = set()
        self.data_lock = threading.Lock()
        self.data_jobs: dict[str, dict] = {}
        # FR-1089: one background model build per repository, shared by every request; read under build_lock only
        self.build_lock = threading.Lock()
        self.builds: dict[str, dict] = {}
        self.latest_build: dict | None = None
        self.code_graphs: dict[str, tuple[str, bytes]] = {}  # FR-1091: root -> (source fingerprint, JSON)
        self.floorplans: dict[str, tuple[str, bytes]] = {}   # FR-1092: root -> (stamp, JSON)

    def codegraph_bytes(self) -> bytes:
        with self.lock:
            root = self.root
        inv = repo_scan.inventory(root)
        source = eabk_model.fingerprint(root, inv)
        with self.lock:
            hit = self.code_graphs.get(str(root))
        if hit and hit[0] == source:
            return hit[1]
        data = json.dumps(code_graph.build(root, inv), ensure_ascii=False).encode("utf-8")
        with self.lock:
            self.code_graphs = {str(root): (source, data)}
        return data

    def floorplan_bytes(self) -> bytes:
        with self.lock:
            root = self.root
        inv = repo_scan.inventory(root)
        source = eabk_model.fingerprint(root, inv)
        arch = root / "floorplan" / "architecture.json"
        stamp = source + "#" + (str(arch.stat().st_mtime_ns) if arch.is_file() else "")
        with self.lock:
            hit = self.floorplans.get(str(root))
        if hit and hit[0] == stamp:
            return hit[1]
        data = json.dumps(floorplan_scan.build(root, inv), ensure_ascii=False).encode("utf-8")
        with self.lock:
            self.floorplans = {str(root): (stamp, data)}
        return data

    def _remote(self, root: Path, force: bool = False) -> dict:
        """Current GitHub data for root; starts a background fetch when missing, stale or forced. Caller holds lock."""
        if not self.remote_enabled:
            return {"status": "disabled", "reason": "started with --no-remote"}
        key = str(root)
        hit = self.remote.get(key)
        stale = hit is None or force or time.time() - hit.get("_at", 0) > self.REMOTE_TTL
        if stale and key not in self.remote_loading:
            self.remote_loading.add(key)

            def store(data):
                with self.lock:
                    previous = self.remote.get(key, {})
                    kept = {s: previous.get(s, []) for s in data.get("pending", [])}  # keep old rows until refetched
                    self.remote[key] = {**data, **kept, "_at": time.time()}

            def work():
                try:
                    data = remote_github.fetch(root, progress=store)
                except Exception as exc:  # a failed fetch is reported, never fatal
                    data = {"status": "error", "reason": str(exc), "issues": [], "pulls": [], "runs": []}
                with self.lock:
                    self.remote[key] = {**data, "_at": time.time()}
                    self.remote_loading.discard(key)

            threading.Thread(target=work, daemon=True).start()
        current = dict(hit) if hit else {"status": "loading", "issues": [], "pulls": [], "runs": []}
        current["loading"] = key in self.remote_loading
        current.pop("_at", None)
        return current

    def refresh_remote(self) -> dict:
        with self.lock:
            return {"status": self._remote(self.root, force=True)["status"]}

    def _imported(self, root: Path, model: dict) -> list[dict]:
        remote = self._remote(root)
        model["remote"] = remote
        return model.get("tasks", []) + remote_github.issue_tasks(remote)

    @staticmethod
    def _catalog_hash(root: Path) -> str:
        catalog = root / eabk_model.load_config(root)["catalog"]
        return hashlib.sha256(catalog.read_bytes()).hexdigest() if catalog.is_file() else ""

    def set_root(self, root: Path) -> None:
        with self.lock:
            self.root = root
            self.previews.clear()
            self.catalog_baseline = self._catalog_hash(root)

    def build_for(self, root: Path, inv: repo_scan.Inventory | None = None, source: str | None = None) -> dict:
        """The background build of root's raw model for this source state: joins a running build, reuses a finished one."""
        if inv is None:
            inv = repo_scan.inventory(root)
        if source is None:
            source = eabk_model.fingerprint(root, inv)
        state = source + "#" + managed_data.stamp(root)  # generated display data changes what is shown, not the source
        key = str(root)
        with self.build_lock:
            job = self.builds.get(key)
            running = job is not None and not job["done"].is_set()
            if running or (job is not None and job["state"] == state and job["error"] is None):
                return job  # a running build is joined even if the source moved on; the caller re-checks afterwards
            job = {"repo": key, "source": source, "state": state, "started": time.monotonic(), "finished": None,
                   "done": threading.Event(),
                   "model": None, "dataStatus": None, "error": None, "published": None, "partial": None, "revision": 0,
                   "stage": None, "progress": {"phase": "prepare", "completed": 0, "total": 1}}
            self.builds = {k: v for k, v in self.builds.items() if k == str(self.root)}  # bounded: current + this one
            self.builds[key] = job
            self.latest_build = job
        threading.Thread(target=self._build, args=(job, root, inv), daemon=True).start()
        return job

    def _build(self, job: dict, root: Path, inv: repo_scan.Inventory) -> None:
        def progress(event):
            with self.build_lock:
                job["progress"] = dict(event)

        data_status = None

        def snapshot(stage, make):
            now = time.monotonic()
            last = job["published"]
            if now - (last if last is not None else job["started"]) < (self.PARTIAL_INTERVAL if last is not None else self.PARTIAL_FIRST):
                return
            model = make()
            model["meta"]["generatedData"] = data_status
            model.setdefault("tasks", [])
            model["remote"] = {"status": "loading", "issues": [], "pulls": [], "runs": []}
            data = json.dumps(model, ensure_ascii=False).encode("utf-8")
            with self.build_lock:
                job.update(partial=data, revision=job["revision"] + 1, stage=stage, published=time.monotonic())

        try:
            data_status, saved = managed_data.inspect(root, job["source"])
            model = saved if saved is not None else eabk_model.build_model(
                root, progress=progress, inv=inv, source_fingerprint=job["source"], snapshot=snapshot)
            with self.build_lock:
                job.update(model=model, dataStatus=data_status)
        except Exception as exc:  # reported to every waiting request
            with self.build_lock:
                job["error"] = exc
        finally:
            with self.build_lock:
                job.update(finished=time.monotonic(), partial=None)
            job["done"].set()

    @staticmethod
    def wait_build(job: dict) -> dict:
        job["done"].wait()
        if job["error"] is not None:
            raise job["error"]
        return job["model"]

    def raw_model(self, root: Path) -> dict:
        """root's freshly built model, without Studio-side decoration (tasks, GitHub data). Do not mutate."""
        while True:
            inv = repo_scan.inventory(root)
            source = eabk_model.fingerprint(root, inv)
            job = self.build_for(root, inv, source)
            model = self.wait_build(job)
            if job["source"] == source:
                return model

    def build_progress(self) -> dict:
        """FR-1089: progress of the latest model build (polled by the browser; never blocks on a running build)."""
        with self.build_lock:
            job = self.latest_build
            if job is None:
                return {"repo": str(self.root), "status": "idle"}
            status = "running" if not job["done"].is_set() else "error" if job["error"] is not None else "done"
            return {"repo": job["repo"], "status": status, "progress": dict(job["progress"]),
                    "elapsedMs": int(((job["finished"] or time.monotonic()) - job["started"]) * 1000),
                    "partial": job["revision"] if job["partial"] is not None else 0, "stage": job["stage"],
                    "error": str(job["error"]) if job["error"] is not None else None}

    def partial_bytes(self) -> bytes | None:
        with self.build_lock:
            job = self.builds.get(str(self.root))
            return job["partial"] if job is not None and not job["done"].is_set() else None

    def model_bytes(self) -> bytes:
        while True:
            with self.lock:
                root = self.root
                inv = repo_scan.inventory(root)
                source = eabk_model.fingerprint(root, inv)
                fp = self._fingerprint(source)
                hit = self.cache.get(str(root))
                if hit and hit[0] == fp:
                    return hit[1]
            job = self.build_for(root, inv, source)
            raw = self.wait_build(job)
            if job["source"] != source:
                continue  # joined an older build; build the current state
            with self.lock:
                if self.root != root:
                    continue
                # Studio-side decoration on a shallow copy: the raw model stays reusable when only tasks or GitHub data change
                model = dict(raw)
                model["meta"] = dict(raw["meta"])
                model["meta"]["generatedData"] = job["dataStatus"]
                model["tasks"] = self.tasks.list(root, self._imported(root, model))
                model["meta"]["taskStorage"] = str(self.tasks.path)
                fp = self._fingerprint(source)
                model["meta"]["stateFingerprint"] = str(root) + "#" + fp
                data = json.dumps(model, ensure_ascii=False).encode("utf-8")
                self.cache = {str(root): (fp, data)}
                return data

    def update_task(self, payload: dict) -> dict:
        root = self.root
        if payload.get("repo") != str(root):
            raise ValueError("repository changed; reload before editing tasks")
        model = dict(self.raw_model(root))
        with self.lock:
            if payload.get("repo") != str(self.root):
                raise ValueError("repository changed; reload before editing tasks")
            result = self.tasks.update(self.root, payload, self._imported(self.root, model))
            self.cache.clear()
            return result

    def fingerprint(self) -> str:
        with self.lock:
            return str(self.root) + "#" + self._fingerprint()

    def data_status(self) -> dict:
        root = self.root
        with self.data_lock:
            job = dict(self.data_jobs.get(str(root), {}))
        return {"repo": str(root), "data": managed_data.inspect(root)[0], "operation": job}

    def start_data_operation(self, payload: dict, action: str) -> dict:
        with self.lock:
            root = self.root
            if payload.get("repo") != str(root):
                raise managed_data.DataError("repository changed; reload before managing data")
        if action == "delete" and payload.get("confirm") is not True:
            raise managed_data.DataError("confirm deletion of the displayed generated-data file")
        key = str(root)
        with self.data_lock:
            if self.data_jobs.get(key, {}).get("status") == "running":
                raise managed_data.DataError("a data operation is already running for this repository")
            self.data_jobs[key] = {"repo": key, "action": action, "status": "running",
                                   "id": os.urandom(16).hex(),
                                   "progress": {"phase": "prepare", "completed": 0, "total": 1}, "error": None}

        def progress(event):
            with self.data_lock:
                self.data_jobs[key]["progress"] = event

        def work():
            try:
                operation = managed_data.sync if action == "sync" else managed_data.delete
                operation(root, progress=progress)
            except (OSError, ValueError, repo_scan.ScanError) as exc:
                with self.data_lock:
                    self.data_jobs[key].update(status="error", error=str(exc))
            else:
                with self.data_lock:
                    self.data_jobs[key]["status"] = "done"
            finally:
                with self.lock:
                    self.cache.pop(key, None)

        threading.Thread(target=work, daemon=True).start()
        return {"repo": key, "status": "running"}

    def _fingerprint(self, source: str | None = None) -> str:
        stamp = self.tasks.path.stat().st_mtime_ns if self.tasks.path.exists() else 0
        remote = self._remote(self.root)
        refreshed = self.remote.get(str(self.root), {}).get("_at", "")
        if source is None:
            source = eabk_model.fingerprint(self.root)
        return source + "#" + managed_data.stamp(self.root) + "#" + str(stamp) + "#" + str(refreshed) + "#" + "|".join(
            str(remote.get(k)) for k in ("status", "fetchedAt", "loading"))

    @staticmethod
    def _catalog_update(root: Path, requirement_id: str) -> dict:
        model = eabk_model.build_model(root)
        reqs = [item for item in model["reqs"] if item["id"] == requirement_id]
        features = [item for item in model["catalog"]["features"] if item["req"] == requirement_id]
        features = [item for item in features if not item.get("derived")]
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
    DISCARD_SECONDS = 2.0  # upper bound for discarding an unread request body
    _unread = 0

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
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # the browser closed the connection (reload, tab closed)

    def send_json(self, obj, status=HTTPStatus.OK) -> None:
        self.send_bytes(json.dumps(obj, ensure_ascii=False).encode("utf-8"), MIME[".json"], status)

    def do_GET(self) -> None:  # noqa: N802
        if not self.host_ok():
            return self.send_json({"error": "bad host"}, HTTPStatus.FORBIDDEN)
        path = urlparse(self.path).path
        if path == "/api/model":
            try:
                return self.send_bytes(STATE.model_bytes(), MIME[".json"])
            except (repo_scan.ScanError, OSError, ValueError, sqlite3.Error) as exc:
                return self.send_json({"error": "analysis-failed", "detail": str(exc)}, HTTPStatus.UNPROCESSABLE_ENTITY)
        if path == "/api/floorplan":
            try:
                return self.send_bytes(STATE.floorplan_bytes(), MIME[".json"])
            except (repo_scan.ScanError, OSError, ValueError) as exc:
                return self.send_json({"error": "analysis-failed", "detail": str(exc)}, HTTPStatus.UNPROCESSABLE_ENTITY)
        if path == "/api/codegraph":
            try:
                return self.send_bytes(STATE.codegraph_bytes(), MIME[".json"])
            except (repo_scan.ScanError, OSError, ValueError) as exc:
                return self.send_json({"error": "analysis-failed", "detail": str(exc)}, HTTPStatus.UNPROCESSABLE_ENTITY)
        if path == "/api/model/progress":
            return self.send_json(STATE.build_progress())
        if path == "/api/model/partial":
            partial = STATE.partial_bytes()
            if partial is None:
                return self.send_bytes(b"", MIME[".json"], HTTPStatus.NO_CONTENT)
            return self.send_bytes(partial, MIME[".json"])
        if path == "/api/fingerprint":
            try:
                return self.send_json({"fingerprint": STATE.fingerprint()})
            except (repo_scan.ScanError, OSError) as exc:
                return self.send_json({"error": "analysis-failed", "detail": str(exc)}, HTTPStatus.UNPROCESSABLE_ENTITY)
        if path == "/api/repo":
            return self.send_json({"repo": str(STATE.root)})
        if path == "/api/data":
            try:
                return self.send_json(STATE.data_status())
            except (repo_scan.ScanError, OSError) as exc:
                return self.send_json({"error": "data-status-failed", "detail": str(exc)}, HTTPStatus.UNPROCESSABLE_ENTITY)
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (WEB / rel).resolve()
        if WEB.resolve() not in target.parents or not target.is_file():
            return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        ctype = MIME.get(target.suffix, "application/octet-stream")
        self.send_bytes(target.read_bytes(), ctype)

    def _body(self, limit: int = 8192) -> bytes:
        data = self.rfile.read(min(self._unread, limit)) if self._unread > 0 else b""
        self._unread -= len(data)
        return data

    def _discard_body(self) -> None:
        """Lingering close for a request whose body was not read (rejected early or oversized): without it the client
        can get a connection reset instead of the response (seen on Windows with multi-megabyte bodies)."""
        if self._unread <= 0:
            return
        self.close_connection = True
        try:
            self.wfile.flush()
            self.connection.shutdown(socket.SHUT_WR)
            self.connection.settimeout(self.DISCARD_SECONDS)
            deadline = time.monotonic() + self.DISCARD_SECONDS
            while self._unread > 0 and time.monotonic() < deadline:
                chunk = self.rfile.read1(min(self._unread, 65536))
                if not chunk:
                    break
                self._unread -= len(chunk)
        except OSError:
            pass

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._unread = max(0, int(self.headers.get("Content-Length") or 0))
        except ValueError:
            self._unread = 0
        try:
            self._post()
        finally:
            self._discard_body()

    def _post(self) -> None:
        if not self.host_ok() or self.headers.get("X-EABK-Studio") != "1":
            return self.send_json({"error": "forbidden"}, HTTPStatus.FORBIDDEN)
        endpoint = urlparse(self.path).path
        if endpoint == "/api/repo/pick":
            # FR-010 AC-332..336: the OS folder dialog is opened on the server (this machine); body is unused.
            self._body()
            picked = pick_folder(str(STATE.root))
            if picked is None:
                return self.send_json({"error": "picker-unavailable"}, HTTPStatus.NOT_IMPLEMENTED)
            return self.send_json({"path": picked})
        if endpoint == "/api/remote/refresh":
            self._body()
            return self.send_json(STATE.refresh_remote())
        if endpoint not in ("/api/repo", "/api/tasks", "/api/maintenance/preview", "/api/maintenance/apply",
                            "/api/data/sync", "/api/data/delete"):
            return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self._body() or b"{}")
            if not isinstance(payload, dict) or length > 8192:
                raise ValueError("invalid payload")
        except (ValueError, TypeError):
            return self.send_json({"error": "bad request"}, HTTPStatus.BAD_REQUEST)
        if endpoint in ("/api/data/sync", "/api/data/delete"):
            try:
                result = STATE.start_data_operation(payload, endpoint.rsplit("/", 1)[-1])
                return self.send_json(result, HTTPStatus.ACCEPTED)
            except managed_data.DataError as exc:
                return self.send_json({"error": "data-operation-rejected", "detail": str(exc)}, HTTPStatus.CONFLICT)
        if endpoint == "/api/tasks":
            try:
                return self.send_json(STATE.update_task(payload))
            except ValueError as exc:
                return self.send_json({"error": "invalid-task", "detail": str(exc)}, HTTPStatus.CONFLICT)
            except (repo_scan.ScanError, OSError, sqlite3.Error) as exc:
                return self.send_json({"error": "task-save-failed", "detail": str(exc)}, HTTPStatus.UNPROCESSABLE_ENTITY)
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
        try:
            # FR-1089: the validating analysis is the shared background build, so its progress is visible
            # (GET /api/model/progress) and the browser's next model request reuses it instead of analyzing again.
            model = STATE.wait_build(STATE.build_for(root))
            if model["meta"].get("error"):
                return self.send_json({"error": "no-data-layer", "repo": str(root)}, HTTPStatus.UNPROCESSABLE_ENTITY)
            STATE.tasks.list(root, model.get("tasks", []))
        except (repo_scan.ScanError, OSError, ValueError, sqlite3.Error) as exc:
            return self.send_json({"error": "analysis-failed", "detail": str(exc)}, HTTPStatus.UNPROCESSABLE_ENTITY)
        STATE.set_root(root)
        self.send_json({"repo": str(root)})


_PICKER_SCRIPT = (
    "import sys, tkinter\n"
    "from tkinter import filedialog\n"
    "r = tkinter.Tk(); r.withdraw()\n"
    "try: r.attributes('-topmost', True)\n"
    "except Exception: pass\n"
    "p = filedialog.askdirectory(initialdir=sys.argv[1], mustexist=True)\n"
    "sys.stdout.write(p or '')\n"
)


def pick_folder(initial: str) -> str | None:
    """Open the OS folder dialog (tkinter in a subprocess so other requests are not blocked).

    Returns the selected path, "" on cancel, or None when no dialog can be opened.
    EABK_STUDIO_PICK_PATH (tests) replaces the dialog; an empty value means cancel.
    """
    forced = os.environ.get("EABK_STUDIO_PICK_PATH")
    if forced is not None:
        return forced.strip()
    try:
        done = subprocess.run([sys.executable, "-c", _PICKER_SCRIPT, initial], capture_output=True, text=True,
                              encoding="utf-8", timeout=600)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip()


def format_report(report: dict) -> str:
    lines = [f"HVE Studio {eabk_model.STUDIO_VERSION} --check", f"  repo: {report['root']}", "  data-layer files:"]
    for item in report["files"]:
        lines.append(f"    [{'found' if item['exists'] else 'missing':7}] {item['key']:<16} {item['path']}")
    if report["boundaryFiles"]:
        lines.append(f"    ({report['boundaryFiles']} boundary file(s) in the requirements directory)")
    c = report["counts"]
    lines.append(
        f"  parsed: requirements={c['requirements']} acceptance-criteria={c['acceptanceCriteria']} "
        f"catalog-rows={c['catalogFeatures']} ledger-cases={c['ledgerCases']} "
        f"warnings={len(report['warnings'])}")
    lines += [f"    warning: {w}" for w in report["warnings"][:10]]
    if report.get("mode") == "code" and report.get("derivedFrom"):
        d = report["derivedFrom"]
        lines.append(f"  mode: code (no EABK data layer; derived read-only from the repository) "
                     f"requirement-docs={', '.join(d['requirementDocs']) or '-'} requirements={d['requirements']} "
                     f"linked-to-code={d['linkedRequirements']} code-files={d['codeFiles']} test-files={d['testFiles']} "
                     f"components={d['components']}")
    if report.get("repository"):
        inv = report["repository"]
        lines.append(f"  repository: {inv.get('counts', {})} tasks={len(inv.get('tasks', []))} "
                     f"dependencies={len(inv.get('dependencies', []))} commits={len(inv.get('history', []))}")
        lines += [f"    scope: {item}" for item in inv.get("unavailable", [])]
    lines.append("  result: OK - start the viewer with `python HVE-Studio/studio.py --repo <repo>`" if report["ok"]
                 else "  result: " + no_data_message(report["root"]))
    return "\n".join(lines)


def no_data_message(root) -> str:
    return (f"no EABK data layer in {root} (docs/requirements-definition.md, docs/catalog.md or tests/system/ledger.json), "
            f"and not a local Git repository. "
            f"Pass a repository with --repo, or see {GUIDE}")


def main(argv=None) -> int:
    global STATE
    ap = argparse.ArgumentParser(description="HVE Studio (Hypervelocity Engineering Studio) - viewer for the EABK data layer (or, without EABK, for the code and PRD)")
    ap.add_argument("--repo", default=None, help="repository to view, with or without EABK (default: current directory)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="do not open the browser")
    ap.add_argument("--role", choices=sorted(ROLE_ROUTES), default=None,
                    help="first screen: pm=dashboard, architect=2D map, swe=tables")
    operations = ap.add_mutually_exclusive_group()
    operations.add_argument("--check", action="store_true",
                    help="list the data-layer files found/missing and record counts, then exit (0 = data layer found, 1 = none)")
    operations.add_argument("--sync-data", action="store_true",
                           help="create/synchronize disposable display data with progress, then exit")
    operations.add_argument("--delete-data", action="store_true",
                           help="delete only intact Studio-generated display data, then exit")
    operations.add_argument("--data-status", action="store_true",
                           help="show generated display-data presence and synchronization state, then exit")
    ap.add_argument("--no-remote", action="store_true",
                    help="do not read GitHub issues, pull requests and Actions runs through the local GitHub CLI (gh)")
    args = ap.parse_args(argv)
    if args.repo is not None:
        root = eabk_model.find_root(Path(args.repo))
    else:
        cwd_root = eabk_model.find_root(Path.cwd())
        root = cwd_root if eabk_model.can_view(cwd_root) else eabk_model.find_root(HERE.parent)
    if args.sync_data or args.delete_data or args.data_status:
        try:
            if args.sync_data:
                status = managed_data.sync(root, progress=managed_data.console_progress())
            elif args.delete_data:
                status = managed_data.delete(root, progress=managed_data.console_progress())
            else:
                status = managed_data.inspect(root)[0]
            print(json.dumps(status, ensure_ascii=False))
            return 1 if status["state"] == "conflict" else 0
        except (repo_scan.ScanError, OSError, ValueError) as exc:
            print(f"Studio data operation failed: {exc}", file=sys.stderr)
            return 1
    if args.check:
        try:
            report = eabk_model.data_layer_report(root)
        except (repo_scan.ScanError, OSError) as exc:
            print(f"repository analysis failed: {exc}", file=sys.stderr)
            return 1
        print(format_report(report))
        return 0 if report["ok"] else 1
    try:
        viewable = eabk_model.can_view(root)
    except (repo_scan.ScanError, OSError) as exc:
        print(f"repository analysis failed: {exc}", file=sys.stderr)
        return 1
    if not viewable:
        print(no_data_message(root), file=sys.stderr)
        return 1
    STATE = State(root, remote=not args.no_remote)
    with STATE.lock:
        STATE._remote(root)  # start the GitHub fetch while the server starts
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
    url = f"http://127.0.0.1:{srv.server_address[1]}/" + (ROLE_ROUTES[args.role] if args.role else "")
    print(f"HVE Studio {eabk_model.STUDIO_VERSION}\n  repo: {root}\n  url : {url}\n  (Ctrl+C to stop)")
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
