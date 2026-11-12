"""Studio-owned tasks and overrides, isolated by canonical repository path."""
from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

STATUSES = ("todo", "doing", "done")


def data_dir() -> Path:
    if os.environ.get("HVE_STUDIO_DATA_DIR"):
        return Path(os.environ["HVE_STUDIO_DATA_DIR"]).expanduser().resolve()
    base = Path(os.environ["LOCALAPPDATA"]) if os.environ.get("LOCALAPPDATA") else Path.home() / ".local" / "share"
    return base / "hve-studio"


class TaskStore:
    def __init__(self, directory: Path | None = None):
        self.path = (directory if directory is not None else data_dir()) / "tasks.sqlite3"

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE IF NOT EXISTS tasks (repo TEXT, id TEXT, title TEXT, status TEXT, PRIMARY KEY(repo,id))")
        return conn

    @staticmethod
    def key(root: Path) -> str:
        return os.path.normcase(str(root.resolve()))

    def list(self, root: Path, imported: list[dict]) -> list[dict]:
        if self.path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Studio task storage must be outside the selected repository; set HVE_STUDIO_DATA_DIR")
        if not self.path.exists():
            return [dict(t) for t in imported]
        with closing(self._connect()) as conn, conn:
            saved = {r["id"]: dict(r) for r in conn.execute("SELECT id,title,status FROM tasks WHERE repo=?", (self.key(root),))}
        result = []
        for task in imported:
            result.append({**task, "status": saved.get(task["id"], task)["status"]})
        result.extend({**t, "origin": "studio", "file": "", "line": None} for t in saved.values() if t["id"].startswith("local:"))
        return result

    def update(self, root: Path, payload: dict, imported: list[dict]) -> dict:
        action, ident = payload.get("action"), payload.get("id")
        tasks = {t["id"]: t for t in self.list(root, imported)}
        if action == "create":
            ident = "local:" + uuid.uuid4().hex
            title = payload.get("title")
            status = "todo"
        else:
            if not isinstance(ident, str) or ident not in tasks:
                raise ValueError("unknown task")
            title = payload.get("title", tasks[ident]["title"])
            status = payload.get("status", tasks[ident]["status"])
        if action not in ("create", "update", "delete", "reset"):
            raise ValueError("unknown task action")
        if action == "delete" and not ident.startswith("local:"):
            raise ValueError("repository tasks cannot be deleted; edit the original file")
        if action == "reset" and ident.startswith("local:"):
            raise ValueError("only repository tasks have overrides")
        if not isinstance(title, str) or not title.strip() or len(title) > 2000:
            raise ValueError("task title must contain 1..2000 characters")
        if status not in STATUSES:
            raise ValueError("invalid task status")
        if not ident.startswith("local:") and title != tasks[ident]["title"]:
            raise ValueError("repository task titles must be edited in the original file")
        with closing(self._connect()) as conn, conn:
            if action in ("delete", "reset"):
                conn.execute("DELETE FROM tasks WHERE repo=? AND id=?", (self.key(root), ident))
            else:
                conn.execute("INSERT OR REPLACE INTO tasks (repo,id,title,status) VALUES (?,?,?,?)",
                             (self.key(root), ident, title.strip(), status))
        return {"id": ident}
