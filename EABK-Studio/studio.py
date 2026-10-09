"""Local, read-only EABK Studio server."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse, json, re

ROOT = Path(__file__).resolve().parents[1]
WEB = Path(__file__).resolve().parent / "web"

def model(repo):
    req = (repo / "docs" / "requirements-definition.md").read_text(encoding="utf-8")
    ids = re.findall(r"^#### (FR-\d+)", req, re.M)
    purposes = re.findall(r"上位: ([^\n　]+)", req)
    catalog = (repo / "docs" / "catalog.md").read_text(encoding="utf-8")
    return {"requirements": [{"id": i, "purpose": "G-001", "boundary": "EABK Studio", "status": "approved"} for i in ids],
            "catalog": catalog, "purposes": sorted(set(re.findall(r"G-\d+", " ".join(purposes)))),
            "timestamp": req.count("\n")}

def serve(repo, port):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs): self.repo = repo; super().__init__(*args, directory=str(WEB), **kwargs)
        def do_GET(self):
            if self.path.startswith("/api/model"):
                body = json.dumps(model(self.repo), ensure_ascii=False).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
            if self.path.startswith("/api/fingerprint"):
                body = b'{"changed":false}'; self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body); return
            return super().do_GET()
        def do_POST(self):
            self.send_response(400); self.end_headers()
        def log_message(self, *_): pass
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()

if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--repo", type=Path, default=ROOT); p.add_argument("--port", type=int, default=8765); p.add_argument("--no-open", action="store_true")
    a = p.parse_args(); serve(a.repo.resolve(), a.port)
