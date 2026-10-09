"""Local, read-only EABK Studio server."""
from __future__ import annotations
import argparse, hashlib, json, re, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent

def _repo_data(repo: Path) -> dict:
    req = repo / "docs" / "requirements-definition.md"
    cat = repo / "docs" / "catalog.md"
    if not req.is_file() or not cat.is_file():
        raise ValueError("management data not found")
    text = req.read_text(encoding="utf-8")
    catalog = cat.read_text(encoding="utf-8")
    requirements = []
    current = None
    for line in text.splitlines():
        m = re.match(r"####\s+(FR-\d+)\s+(.+)", line)
        if m:
            current = {"id": m.group(1), "title": m.group(2), "text": "", "acs": []}
            requirements.append(current)
        elif current and line.startswith("- 要求:"):
            current["text"] = line.split(":", 1)[1].strip()
        elif current and "受入基準 AC-" in line:
            ac = re.search(r"(AC-\d+):\s*(.*)", line)
            if ac:
                current["acs"].append({"id": ac.group(1), "text": ac.group(2)})
    rows = []
    for line in catalog.splitlines():
        if line.startswith("| FR-"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 6:
                rows.append({"id": cells[0], "title": cells[1], "status": cells[2],
                             "files": cells[3], "tests": cells[4], "shared": cells[5]})
    files = sorted({p for row in rows for p in re.findall(r"`([^`]+)`", row["files"])})
    for item in requirements:
        match = next((r for r in rows if r["id"] == item["id"]), None)
        item["catalog"] = match or {}
        item["source"] = ["docs/requirements-definition.md", "docs/catalog.md"]
    return {"repo": repo.name, "repo_path": str(repo), "requirements": requirements,
            "catalog": rows, "files": files}

def fingerprint(repo: Path) -> str:
    h = hashlib.sha256()
    for name in ("docs/requirements-definition.md", "docs/catalog.md"):
        p = repo / name
        if p.exists():
            h.update(name.encode()); h.update(p.read_bytes())
    return h.hexdigest()

class Handler(BaseHTTPRequestHandler):
    server_version = "EABKStudio/1.0"
    def _json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/model":
            try: self._json(_repo_data(self.server.repo))
            except ValueError as e: self._json({"error": str(e)}, 422)
        elif parsed.path == "/api/fingerprint":
            self._json({"fingerprint": fingerprint(self.server.repo)})
        elif parsed.path == "/api/repo":
            self._json({"repo": self.server.repo.name, "path": str(self.server.repo)})
        elif parsed.path == "/" or parsed.path.startswith("/index.html"):
            self._serve(ROOT / "web" / "index.html")
        elif parsed.path.startswith("/web/"):
            self._serve(ROOT / parsed.path.lstrip("/"))
        else: self._json({"error": "not found"}, 404)
    def do_POST(self):
        if urlparse(self.path).path != "/api/repo":
            self._json({"error": "not found"}, 404); return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            target = Path(json.loads(self.rfile.read(length)).get("path", "")).expanduser().resolve()
            data = _repo_data(target)
        except (ValueError, OSError, json.JSONDecodeError) as e:
            self._json({"error": str(e) or "invalid repository"}, 422); return
        self.server.repo = target
        self._json(data)
    def _serve(self, path):
        if not path.is_file(): self.send_error(404); return
        body = path.read_bytes(); typ = "text/html" if path.suffix == ".html" else "text/javascript"
        self.send_response(200); self.send_header("Content-Type", typ + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *_): pass

def create_server(repo: Path, port: int = 8765):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.repo = repo.resolve()
    return server

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    server = create_server(Path(args.repo), args.port)
    print(f"EABK Studio: http://127.0.0.1:{args.port}/", flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__ == "__main__":
    main()
