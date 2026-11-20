"""FR-1100 AC-541 AC-542 (relations between repositories) and FR-1099 AC-537 (IDs kept apart per repository)."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import multi_repo  # noqa: E402
import xrepo  # noqa: E402


def _w(p: Path, s: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def _git(*roots):
    for r in roots:
        subprocess.run(["git", "init", "-q"], cwd=r, check=True)
        subprocess.run(["git", "add", "-A"], cwd=r, check=True)


def _known_group(tmp: Path):
    """front -> api (HTTP), api -> shared (package + function), both use the table `orders` (name only)."""
    sh, api, fr = tmp / "shared", tmp / "api", tmp / "front"
    _w(sh / "pyproject.toml", '[project]\nname = "shared-lib"\nversion = "1.0"\n')
    _w(sh / "shared_lib" / "__init__.py", "")
    _w(sh / "shared_lib" / "pricing.py", "def compute_total(rows):\n    return sum(r.price for r in rows)\n")
    _w(sh / "migrations" / "001_orders.sql", "CREATE TABLE orders (id int primary key, price int);\n")
    _w(api / "pyproject.toml", '[project]\nname = "orders-api"\ndependencies = [\n  "shared-lib>=1.0",\n  "fastapi",\n]\n')
    _w(api / "app" / "main.py", "from fastapi import FastAPI\nfrom shared_lib.pricing import compute_total\napp = FastAPI()\n\n"
       "@app.get(\"/api/orders/{order_id}\")\ndef get_order(order_id: int):\n"
       "    rows = db.execute(\"SELECT * FROM orders WHERE id = ?\", order_id)\n    return compute_total(rows)\n")
    _w(fr / "package.json", '{"name": "web-front", "dependencies": {"react": "18"}}')
    _w(fr / "src" / "api.js", "export async function loadOrder() {\n  const r = await fetch('/api/orders/42');\n  return r.json();\n}\n")
    _git(sh, api, fr)
    return [{"name": "shared", "path": str(sh)}, {"name": "api", "path": str(api)}, {"name": "front", "path": str(fr)}]


# FR-1100 AC-542: confirmed relations equal the known ones (none extra); the shared table name is only a candidate
def test_ac542_known_relations_are_found_and_nothing_else_is_confirmed(tmp_path):
    out = xrepo.build(_known_group(tmp_path))
    confirmed = {(r["kind"], r["label"], r["from"]["repo"], r["to"]["repo"]) for r in out["relations"] if r["certainty"] == "confirmed"}
    assert confirmed == {("package", "shared-lib", "api", "shared"), ("function", "compute_total", "api", "shared"),
                         ("api", "GET /api/orders/{order_id}", "front", "api")}
    cand = [r for r in out["relations"] if r["certainty"] == "candidate"]
    assert [(r["kind"], r["label"], r["from"]["repo"], r["to"]["repo"]) for r in cand] == [("data", "table orders", "api", "shared")]
    fn = next(r for r in out["relations"] if r["kind"] == "function")
    assert fn["from"] == {"repo": "api", "file": "app/main.py", "line": 8} and fn["to"]["file"] == "shared_lib/pricing.py"


# FR-1100 AC-541: no relation -> the kinds examined and the files per repository; unsupported files are counted
def test_ac541_no_relations_reports_what_was_examined(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _w(a / "main.py", "def run():\n    return 1\n")
    _w(a / "Main.java", "class Main {}\n")
    _w(b / "index.js", "export function go() { return 2; }\n")
    _git(a, b)
    out = xrepo.build([{"name": "a", "path": str(a)}, {"name": "b", "path": str(b)}])
    assert out["relations"] == [] and out["kinds"] == ["package", "function", "api", "data"]
    stats = {r["name"]: r for r in out["repos"]}
    assert stats["a"]["files"] == 2 and stats["a"]["unparsed"] == 1 and stats["b"]["files"] == 1
    assert out["limits"] == {"maxFileBytes": 512000, "maxFunctions": 20000}


# FR-1099 AC-537: the same ID in two repositories is kept apart with the repository name, references follow
def test_ac537_same_ids_are_prefixed_per_repository():
    def model(title):
        return {"meta": {"name": title}, "reqs": [{"id": "FR-001", "title": title, "goal": "G-001", "acs": [{"id": "AC-001"}]}],
                "goals": [{"id": "G-001"}], "cases": [{"id": "E2E-001", "ac_ids": ["AC-001"], "status": "pass"}],
                "graph": {"nodes": [{"id": "FR-001", "label": "FR-001", "type": "req"}, {"id": "file:src/a.py", "label": "src/a.py", "type": "file"}],
                          "edges": [{"s": "FR-001", "t": "file:src/a.py", "rel": "impl"}]}}
    merged = multi_repo.merge([{"name": "web", "path": "/w", "model": model("web req")}, {"name": "api", "path": "/a", "model": model("api req")}])
    assert [r["id"] for r in merged["reqs"]] == ["web:FR-001", "api:FR-001"]
    assert [r["goal"] for r in merged["reqs"]] == ["web:G-001", "api:G-001"]
    assert merged["cases"][1]["ac_ids"] == ["api:AC-001"]
    assert {(e["s"], e["t"]) for e in merged["graph"]["edges"]} == {("web:FR-001", "web:file:src/a.py"), ("api:FR-001", "api:file:src/a.py")}
    assert {n["repo"] for n in merged["graph"]["nodes"]} == {"web", "api"}
    assert merged["graph"]["nodes"][1]["label"] == "web:src/a.py"


def test_repo_names_are_unique():
    assert multi_repo.repo_names(["/x/app", "/y/app", "/z/api"]) == ["x/app", "y/app", "api"]
