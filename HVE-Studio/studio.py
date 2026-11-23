#!/usr/bin/env python3
"""HVE Studio: local web viewer for the HVE data layer of any repository.

    python HVE-Studio/studio.py --repo <path-to-any-repo>   # with HVE: data layer; without: code mode

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
from urllib.parse import parse_qs, urlparse

sys.dont_write_bytecode = True  # do not leave __pycache__ in the repository being viewed
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ai  # noqa: E402
import code_graph  # noqa: E402
import hve_model  # noqa: E402
import floorplan_scan  # noqa: E402
import repo_scan  # noqa: E402
import remote_github  # noqa: E402
import managed_data  # noqa: E402
import multi_repo  # noqa: E402
import release  # noqa: E402
import xrepo  # noqa: E402
from task_state import TaskStore  # noqa: E402

WEB = HERE / "web"
# The toolkit source keeps the guide in users-guide/; installed repositories get it as HVE-docs/.
GUIDE = next((d + "/studio/01-first-steps.md" for d in ("HVE-docs", "users-guide") if (HERE.parent / d / "studio" / "01-first-steps.md").exists()), "HVE-docs/studio/01-first-steps.md")
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
        self.extra: list[Path] = []  # FR-1099: the other repositories of the application (the group is [root, *extra])
        self.xrepo: tuple[str, bytes] | None = None  # FR-1100: (group stamp, JSON)
        self.repo_errors: dict[str, str] = {}  # FR-1099 AC-536: why a repository of the group could not be loaded
        self.ai_keys = ai.Keys()  # FR-1096: session keys in memory, the rest in the OS vault
        self.ai_consent: set[str] = set()  # NFR-SEC-024 AC-530: repositories the user agreed to send (this session only)

    def group(self) -> list[Path]:
        with self.lock:
            return [self.root, *self.extra]

    def repos_status(self) -> list[dict]:
        roots = self.group()
        names = multi_repo.repo_names([str(r) for r in roots])
        out = []
        with self.build_lock:
            for root, name in zip(roots, names):
                job = self.builds.get(str(root))
                if job is None:
                    status, error, mode = "pending", None, None
                elif not job["done"].is_set():
                    status, error, mode = "loading", None, None
                elif job["error"] is not None:
                    status, error, mode = "error", str(job["error"]), None
                else:
                    meta = job["model"]["meta"]
                    status = "error" if meta.get("error") else "loaded"
                    error, mode = (str(meta.get("error")) if meta.get("error") else None), meta.get("mode")
                if str(root) in self.repo_errors:
                    status, error = "error", self.repo_errors[str(root)]
                out.append({"name": name, "path": str(root), "status": status, "error": error, "mode": mode,
                            "primary": root == roots[0]})
        return out

    def add_repo(self, raw: str) -> list[dict]:
        p = Path(raw).expanduser()
        if not raw or not p.is_dir():
            raise ValueError("not-a-directory")
        root = hve_model.find_root(p)
        viewable = hve_model.can_view(root)
        with self.lock:
            group = [self.root, *self.extra]
            if any(os.path.normcase(str(root.resolve())) == os.path.normcase(str(g.resolve())) for g in group):
                raise ValueError("duplicate")
            if len(group) >= multi_repo.LIMIT:
                raise ValueError("limit")
            if not viewable:
                raise ValueError("no-data-layer")
            self.extra.append(root)
            self.cache.clear()
        self.build_for(root)
        return self.repos_status()

    def remove_repo(self, raw: str) -> list[dict]:
        target = os.path.normcase(str(Path(raw).expanduser().resolve())) if raw else ""
        with self.lock:
            group = [self.root, *self.extra]
            keep = [g for g in group if os.path.normcase(str(g.resolve())) != target]
            if len(keep) == len(group):
                raise ValueError("not-in-group")
            if not keep:
                raise ValueError("last-repository")
            primary_changed = keep[0] != self.root
            self.extra = keep[1:]
            self.cache.clear()
        if primary_changed:
            self.set_root(keep[0])
        return self.repos_status()

    def xrepo_bytes(self) -> bytes:
        roots = self.group()
        names = multi_repo.repo_names([str(r) for r in roots])
        pairs = [(n, r) for n, r in zip(names, roots) if r.is_dir()]  # a repository that disappeared is reported by repos_status()
        stamp = "|".join(str(r) + "#" + hve_model.fingerprint(r) for _, r in pairs)
        with self.lock:
            if self.xrepo and self.xrepo[0] == stamp:
                return self.xrepo[1]
        data = json.dumps(xrepo.build([{"name": n, "path": str(r)} for n, r in pairs]),
                          ensure_ascii=False).encode("utf-8")
        with self.lock:
            self.xrepo = (stamp, data)
        return data

    def ai_sources(self, paths: list[str]) -> list[tuple[str, dict]]:
        """The (name, model) of every consented repository among the requested ones (AC-530)."""
        roots = self.group()
        names = multi_repo.repo_names([str(r) for r in roots])
        wanted = {os.path.normcase(p) for p in paths}
        out = []
        for root, name in zip(roots, names):
            key = os.path.normcase(str(root))
            if key in wanted and key in self.ai_consent:
                out.append((name, self.raw_model(root)))
        return out

    def codegraph_bytes(self) -> bytes:
        with self.lock:
            root = self.root
        inv = repo_scan.inventory(root)
        source = hve_model.fingerprint(root, inv)
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
        source = hve_model.fingerprint(root, inv)
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
        catalog = root / hve_model.load_config(root)["catalog"]
        return hashlib.sha256(catalog.read_bytes()).hexdigest() if catalog.is_file() else ""

    def set_root(self, root: Path) -> None:
        with self.lock:
            self.root = root
            self.extra = [e for e in self.extra if e != root]
            self.previews.clear()
            self.catalog_baseline = self._catalog_hash(root)

    def switch_root(self, root: Path) -> None:
        """FR-010: the switch replaces the whole group with one repository (FR-1099 keeps adding as a separate action)."""
        with self.lock:
            self.extra = []
            self.cache.clear()
        self.set_root(root)

    def build_for(self, root: Path, inv: repo_scan.Inventory | None = None, source: str | None = None) -> dict:
        """The background build of root's raw model for this source state: joins a running build, reuses a finished one."""
        if inv is None:
            inv = repo_scan.inventory(root)
        if source is None:
            source = hve_model.fingerprint(root, inv)
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
            self.builds = {k: v for k, v in self.builds.items() if k in {str(self.root), *map(str, self.extra)}}  # bounded: the group + this one
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
            # FR-1095: a model that is still being built is never judged ("unknown", not a premature "ok")
            model["release"] = {"state": "unknown", "reasons": [{"code": "pending"}], "goals": [], "items": [],
                                "ledgerRunAt": None, "modelAt": model["meta"].get("generatedAt"), "approvalRequests": 0}
            data = json.dumps(model, ensure_ascii=False).encode("utf-8")
            with self.build_lock:
                job.update(partial=data, revision=job["revision"] + 1, stage=stage, published=time.monotonic())

        try:
            data_status, saved = managed_data.inspect(root, job["source"])
            model = saved if saved is not None else hve_model.build_model(
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
            source = hve_model.fingerprint(root, inv)
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
                source = hve_model.fingerprint(root, inv)
                extras = list(self.extra)
                fp = self._fingerprint(source) + self._extras_stamp(extras)
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
                if self.extra != extras:
                    continue
            model["release"] = release.judge(raw)  # FR-1095
            names = multi_repo.repo_names([str(r) for r in [root, *extras]])
            if extras:
                model = self._group_model(model, root, extras, names)  # FR-1099
            repos = self.repos_status()
            with self.lock:
                if self.root != root or self.extra != extras:
                    continue
                model["meta"]["repos"] = repos
                fp = self._fingerprint(source) + self._extras_stamp(extras)
                model["meta"]["stateFingerprint"] = str(root) + "#" + fp
                data = json.dumps(model, ensure_ascii=False).encode("utf-8")
                self.cache = {str(root): (fp, data)}
                return data

    @staticmethod
    def _extras_stamp(extras: list[Path]) -> str:
        def one(e: Path) -> str:
            try:
                return hve_model.fingerprint(e) if e.is_dir() else "missing"
            except (repo_scan.ScanError, OSError, ValueError) as exc:
                return "error:" + str(exc)
        return "".join("|" + str(e) + "#" + one(e) for e in extras)

    def _group_model(self, primary: dict, root: Path, extras: list[Path], names: list[str]) -> dict:
        """FR-1099 AC-536..AC-538: repositories that fail to load are left out (and reported), the rest are shown."""
        entries = [{"name": names[0], "path": str(root), "model": primary}]
        for path, name in zip(extras, names[1:]):
            try:
                if not path.is_dir():
                    raise OSError(f"folder not found: {path}")
                raw = self.raw_model(path)
            except (repo_scan.ScanError, OSError, ValueError, sqlite3.Error) as exc:
                self.repo_errors[str(path)] = str(exc)  # reported by repos_status(); the others are still shown
                continue
            self.repo_errors.pop(str(path), None)
            if raw["meta"].get("error"):
                continue
            entries.append({"name": name, "path": str(path), "model": {**raw, "release": release.judge(raw)}})
        merged = multi_repo.merge(entries)
        merged["release"] = multi_repo.group_release(entries)
        merged["tasks"] = primary.get("tasks", [])
        merged["remote"] = primary.get("remote")
        return merged

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
            return str(self.root) + "#" + self._fingerprint() + self._extras_stamp(list(self.extra))

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
            source = hve_model.fingerprint(self.root)
        return source + "#" + managed_data.stamp(self.root) + "#" + str(stamp) + "#" + str(refreshed) + "#" + "|".join(
            str(remote.get(k)) for k in ("status", "fetchedAt", "loading"))

    @staticmethod
    def _catalog_update(root: Path, requirement_id: str) -> dict:
        model = hve_model.build_model(root)
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
                with tempfile.NamedTemporaryFile("wb", dir=catalog.parent, prefix=".hve-studio-", delete=False) as handle:
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
                    hve_model.build_model(self.root)
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
    server_version = "HVEStudio/" + hve_model.STUDIO_VERSION
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
        if path == "/api/repos":
            return self.send_json({"repos": STATE.repos_status(), "limit": multi_repo.LIMIT})
        if path == "/api/xrepo":
            try:
                return self.send_bytes(STATE.xrepo_bytes(), MIME[".json"])
            except (repo_scan.ScanError, OSError, ValueError) as exc:
                return self.send_json({"error": "analysis-failed", "detail": str(exc)}, HTTPStatus.UNPROCESSABLE_ENTITY)
        if path == "/api/ai/status":
            q = parse_qs(urlparse(self.path).query)
            provider, endpoint = (q.get("provider") or [""])[0], (q.get("endpoint") or [""])[0]
            try:
                endpoint = ai._endpoint(endpoint) if endpoint else ""
            except ai.AIError as exc:
                return self.send_json(exc.as_dict(), HTTPStatus.BAD_REQUEST)
            status = STATE.ai_keys.status(provider, endpoint) if provider in ai.AUTHS else {"stored": False, "session": False}
            return self.send_json({**status, "vault": ai.secret_store.availability(),
                                   "copilotSdk": ai.copilot_available(), "timeout": ai.TIMEOUT,
                                   "consented": sorted(STATE.ai_consent)})
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
        if not self.host_ok() or self.headers.get("X-HVE-Studio") != "1":
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
        if endpoint.startswith(("/api/repos/", "/api/ai/")):
            try:
                payload = json.loads(self._body(32768) or b"{}")
                if not isinstance(payload, dict) or self._unread > 0:
                    raise ValueError("invalid payload")
            except (ValueError, TypeError):
                return self.send_json({"error": "bad request"}, HTTPStatus.BAD_REQUEST)
            if endpoint.startswith("/api/repos/"):
                return self._repos(endpoint, payload)
            return self._ai(endpoint, payload)
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
        root = hve_model.find_root(p)
        try:
            # FR-1089: the validating analysis is the shared background build, so its progress is visible
            # (GET /api/model/progress) and the browser's next model request reuses it instead of analyzing again.
            model = STATE.wait_build(STATE.build_for(root))
            if model["meta"].get("error"):
                return self.send_json({"error": "no-data-layer", "repo": str(root)}, HTTPStatus.UNPROCESSABLE_ENTITY)
            STATE.tasks.list(root, model.get("tasks", []))
        except (repo_scan.ScanError, OSError, ValueError, sqlite3.Error) as exc:
            return self.send_json({"error": "analysis-failed", "detail": str(exc)}, HTTPStatus.UNPROCESSABLE_ENTITY)
        STATE.switch_root(root)
        self.send_json({"repo": str(root)})

    def _repos(self, endpoint: str, payload: dict) -> None:
        """FR-1099 AC-536: add (folder dialog on the server) or remove one repository of the group."""
        try:
            if endpoint == "/api/repos/add":
                picked = pick_folder(str(STATE.root))
                if picked is None:
                    return self.send_json({"error": "picker-unavailable"}, HTTPStatus.NOT_IMPLEMENTED)
                if not picked:
                    return self.send_json({"cancelled": True, "repos": STATE.repos_status()})
                return self.send_json({"repos": STATE.add_repo(picked)})
            if endpoint == "/api/repos/restore":
                # restore the saved group: only paths, the first must be the current repository
                paths = payload.get("paths") or []
                added, skipped = [], []
                if isinstance(paths, list) and paths and os.path.normcase(str(paths[0])) == os.path.normcase(str(STATE.root)):
                    for p in paths[1:]:
                        try:
                            STATE.add_repo(str(p))
                            added.append(str(p))
                        except ValueError as exc:
                            skipped.append({"path": str(p), "error": str(exc)})
                return self.send_json({"repos": STATE.repos_status(), "added": added, "skipped": skipped})
            if endpoint == "/api/repos/remove":
                return self.send_json({"repos": STATE.remove_repo(str(payload.get("path", "")))})
        except ValueError as exc:
            return self.send_json({"error": str(exc), "repos": STATE.repos_status(), "limit": multi_repo.LIMIT},
                                  HTTPStatus.CONFLICT)
        return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def _ai(self, endpoint: str, payload: dict) -> None:
        """FR-1096..FR-1098, NFR-SEC-024: every call starts from a user action; keys never come back in a response."""
        name = endpoint.rsplit("/api/ai/", 1)[-1]
        try:
            if name == "key":
                cfg = ai.check_config(payload.get("config") or {})
                if not cfg.get("endpoint"):
                    raise ai.AIError("bad-config", "enter the endpoint first")
                status = STATE.ai_keys.put(cfg["provider"], cfg["endpoint"], str(payload.get("key") or ""),
                                           bool(payload.get("persist")))
                return self.send_json(status)
            if name == "key/delete":
                cfg = ai.check_config(payload.get("config") or {})
                return self.send_json(STATE.ai_keys.delete(cfg["provider"], cfg.get("endpoint") or ""))
            if name == "signin":
                return self.send_json(ai.signin(str(payload.get("provider") or "")))
            if name == "resources":
                return self.send_json({"items": ai.list_resources(str(payload.get("level") or ""),
                                                                  str(payload.get("subscription") or ""),
                                                                  str(payload.get("account") or ""))})
            if name == "test":
                return self.send_json(ai.test_connection(payload.get("config") or {}, STATE.ai_keys))
            if name == "consent":
                known = {os.path.normcase(str(r)) for r in STATE.group()}
                for p in payload.get("repos") or []:
                    if os.path.normcase(str(p)) in known:
                        STATE.ai_consent.add(os.path.normcase(str(p)))
                return self.send_json({"consented": sorted(STATE.ai_consent)})
            if name == "ask":
                paths = [str(p) for p in payload.get("repos") or [str(STATE.root)]]
                sources = STATE.ai_sources(paths)
                if not sources:
                    raise ai.AIError("consent-required", "agree to send this repository's information first")
                step = int(payload.get("step") or 1)
                return self.send_json(ai.ask(payload.get("config") or {}, STATE.ai_keys, step,
                                             str(payload.get("question") or ""), str(payload.get("lang") or "ja"), sources))
        except ai.AIError as exc:
            status = {"consent-required": HTTPStatus.CONFLICT, "bad-config": HTTPStatus.BAD_REQUEST}.get(exc.code, HTTPStatus.BAD_GATEWAY)
            return self.send_json(exc.as_dict(), status)
        except (repo_scan.ScanError, OSError, ValueError, sqlite3.Error) as exc:
            return self.send_json({"error": "provider-error", "detail": str(exc)[:300]}, HTTPStatus.BAD_GATEWAY)
        return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)


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
    HVE_STUDIO_PICK_PATH (tests) replaces the dialog; an empty value means cancel.
    """
    forced = os.environ.get("HVE_STUDIO_PICK_PATH")
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
    lines = [f"HVE Studio {hve_model.STUDIO_VERSION} --check", f"  repo: {report['root']}", "  data-layer files:"]
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
        lines.append(f"  mode: code (no HVE data layer; derived read-only from the repository) "
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
    return (f"no HVE data layer in {root} (docs/requirements-definition.md, docs/catalog.md or tests/system/ledger.json), "
            f"and not a local Git repository. "
            f"Pass a repository with --repo, or see {GUIDE}")


def main(argv=None) -> int:
    global STATE
    ap = argparse.ArgumentParser(description="HVE Studio (Hypervelocity Engineering Studio) - viewer for the HVE data layer (or, without HVE, for the code and PRD)")
    ap.add_argument("--repo", default=None, help="repository to view, with or without HVE (default: current directory)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="do not open the browser")

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
        root = hve_model.find_root(Path(args.repo))
    else:
        cwd_root = hve_model.find_root(Path.cwd())
        root = cwd_root if hve_model.can_view(cwd_root) else hve_model.find_root(HERE.parent)
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
            report = hve_model.data_layer_report(root)
        except (repo_scan.ScanError, OSError) as exc:
            print(f"repository analysis failed: {exc}", file=sys.stderr)
            return 1
        print(format_report(report))
        return 0 if report["ok"] else 1
    try:
        viewable = hve_model.can_view(root)
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
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"HVE Studio {hve_model.STUDIO_VERSION}\n  repo: {root}\n  url : {url}\n  (Ctrl+C to stop)")
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
