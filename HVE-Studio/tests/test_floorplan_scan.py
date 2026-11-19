"""FR-1092: the floorplan scan — parts, endpoints, screens, health and recent work.
The route expectations for Express / Hono / FastAPI mirror the fixtures and expected lists of Floorplan's own tests (MIT), written out inline:
an independent reader of the same source has to produce the same endpoints."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import floorplan_routes as R  # noqa: E402
import floorplan_scan as S  # noqa: E402


def _repo(tmp_path, files, commit=False):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    if commit:
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "Add refunds"], cwd=tmp_path, check=True)
    return tmp_path


def _keys(files):
    return sorted(f"{r['m']} {r['p']} <- {r['f']}" for r in R.extract(files))


EXPRESS = {
    "server/index.ts": ("import express from 'express';\nimport orderRoutes from './orders.routes.js';\nimport { authRoutes } from './auth/index.js';\n"
                        "import { createBillingRoutes } from './billing.routes.js';\nimport { profileRoutes } from './profile.routes.js';\n\nconst app = express();\n"
                        "const billingRoutes = createBillingRoutes();\n\napp.use('/api/orders', orderRoutes);\napp.use('/api/auth', authRoutes);\napp.use('/api/billing', billingRoutes);\n"
                        "app.use('/api/profile', profileRoutes);\napp.get('/health', (req, res) => res.json({ ok: true }));\n"),
    "server/orders.routes.ts": "import { Router } from 'express';\nconst router = Router();\nrouter.get('/', (req, res) => res.json([]));\nexport default router;\n",
    "server/billing.routes.ts": "import { Router } from 'express';\nexport function createBillingRoutes() {\n  const router = Router();\n  router.post('/refund', (req, res) => res.json({}));\n  return router;\n}\n",
    "server/profile.routes.ts": "import { Router } from 'express';\nexport const profileRoutes = Router();\nprofileRoutes.get('/me', (req, res) => res.json({}));\n",
    "server/auth/auth.routes.ts": "import { Router } from 'express';\nconst router = Router();\nrouter.post('/login', (req, res) => res.json({}));\nexport default router;\n",
    "server/auth/index.ts": "export { default as authRoutes } from './auth.routes.js';\n",
}


# FR-1092 AC-508: Express mounts through barrels, factories and named exports give the same endpoints as Floorplan's own fixture.
def test_ac508_express_mounts_match_the_reference_fixture():
    assert _keys(EXPRESS) == [
        "GET /api/orders <- server/orders.routes.ts", "GET /api/profile/me <- server/profile.routes.ts", "GET /health <- server/index.ts",
        "POST /api/auth/login <- server/auth/auth.routes.ts", "POST /api/billing/refund <- server/billing.routes.ts"]


# FR-1092 AC-508: Hono routers under any name nest inside one file; a name that is not a router puts no prefix on anything.
def test_ac508_hono_nested_routers_and_non_router_use():
    hono = {"src/routes.ts": ("import { Hono } from 'hono';\nexport const frentes = new Hono();\nfrentes.get('/lista', () => new Response('ok'));\nfrentes.delete('/vieja', () => new Response('ok'));\n"
                              "export const croquis = new Hono();\ncroquis.get('/mapa', () => new Response('ok'));\nconst api = new Hono();\napi.route('/frentes', frentes);\napi.route('/croquis', croquis);\nexport default api;\n"),
            "src/index.ts": "import { Hono } from 'hono';\nimport api from './routes.js';\nconst app = new Hono();\napp.get('/health', () => new Response('ok'));\napp.route('/api', api);\nexport default app;\n"}
    assert _keys(hono) == ["DELETE /api/frentes/vieja <- src/routes.ts", "GET /api/croquis/mapa <- src/routes.ts", "GET /api/frentes/lista <- src/routes.ts", "GET /health <- src/index.ts"]
    plain = {"server/index.js": ("import express from 'express';\nimport { authenticate, authRoutes } from './auth.js';\nconst app = express();\napp.use('/api', authenticate);\napp.use('/auth', authRoutes);\n"
                                 "app.get('/health', (req, res) => res.json({ ok: true }));\n"),
             "server/auth.js": ("import { Router } from 'express';\nexport function authenticate(req, res, next) { next(); }\nexport const authRoutes = Router();\nauthRoutes.post('/login', (req, res) => res.json({}));\n")}
    assert _keys(plain) == ["GET /health <- server/index.js", "POST /auth/login <- server/auth.js"]


# FR-1092 AC-508: FastAPI include_router across files, Flask blueprints, http.server literals and Django urls.
def test_ac508_python_frameworks():
    fastapi = {
        "app/main.py": "from fastapi import FastAPI\nfrom app.routers import items, staff, orders\napp = FastAPI()\napp.include_router(items.router, prefix='/items')\napp.include_router(staff.router, prefix='/staff')\napp.include_router(orders.router)\n",
        "app/routers/items.py": "from fastapi import APIRouter\nrouter = APIRouter()\n\n\n@router.delete('/{item_id}')\ndef drop(item_id):\n    \"\"\"Remove one item.\"\"\"\n",
        "app/routers/staff.py": "from fastapi import APIRouter\nrouter = APIRouter()\n\n\n@router.get('/report')\ndef report():\n    pass\n\n\n@router.post('/reset')\ndef reset():\n    pass\n",
        "app/routers/orders.py": "from fastapi import APIRouter\nrouter = APIRouter()\n\n\n@router.post('/orders')\ndef make():\n    pass\n"}
    assert _keys(fastapi) == ["DELETE /items/{item_id} <- app/routers/items.py", "GET /staff/report <- app/routers/staff.py", "POST /orders <- app/routers/orders.py", "POST /staff/reset <- app/routers/staff.py"]
    assert {r["h"]: r["d"] for r in R.extract(fastapi)}["drop"] == "Remove one item."
    flask = {"app.py": "from flask import Flask, Blueprint\napp = Flask(__name__)\nbp = Blueprint('b', __name__, url_prefix='/b')\n\n\n@bp.route('/x', methods=['POST'])\ndef x():\n    pass\n\n\n@app.get('/items')\ndef items():\n    pass\n\n\napp.register_blueprint(bp)\n"}
    assert _keys(flask) == ["GET /items <- app.py", "POST /b/x <- app.py"]
    server = {"srv.py": ("class H:\n    def do_GET(self):\n        if path == '/api/model':\n            pass\n        if path.startswith('/api/files/'):\n            pass\n\n"
                         "    def _post(self):\n        if endpoint in ('/api/a', '/api/b'):\n            pass\n")}
    assert _keys(server) == ["GET /api/files/* <- srv.py", "GET /api/model <- srv.py", "POST /api/a <- srv.py", "POST /api/b <- srv.py"]


# FR-1092 AC-508: a literal request from the frontend becomes a web-request line to the endpoint; a path built at run time is not guessed.
def test_ac508_requests_are_matched_to_endpoints():
    files = {"web/api.js": "export const drop = (id) => fetch('/items/3', { method: 'DELETE' });\nexport const dyn = (p) => fetch(base + p);\n"}
    calls = R.http_calls(files)
    assert calls == [("web/api.js", "DELETE", "/items/3", 1)]
    assert R.match("/items/{item_id}", "/items/3") and R.match("/api/files/*", "/api/files/x/y") and not R.match("/items/{id}", "/items/3/more")


# FR-1092 AC-507: architecture.json parts claim files by the deepest glob; exclude is inherited; externals follow packages and hosts; bad patterns are reported.
def test_ac507_authored_parts_assignment_externals_and_problems(tmp_path):
    arch = {"project": {"name": "Shop", "summary": "A shop."}, "ignore": ["gen/**"], "editor": "cursor", "nodes": [
        {"id": "web", "label": "Storefront", "kind": "ui", "summary": "The pages.", "paths": ["web"], "exclude": ["**/*.test.js"]},
        {"id": "web.core", "parent": "web", "label": "Core", "kind": "library", "paths": ["web/src"]},
        {"id": "tests", "label": "Tests", "kind": "test", "paths": ["**/*.test.js"]},
        {"id": "api", "label": "Server", "kind": "service", "paths": ["server/**"]},
        {"id": "api.db", "parent": "api", "label": "Data", "kind": "data", "paths": ["server/{db,models}/**"]},
        {"id": "stripe", "label": "Stripe", "kind": "external", "hosts": ["api.stripe.com"]},
        {"id": "bad", "label": "Bad", "kind": "library", "paths": ["[evil"]}],
        "edges": [{"from": "api", "to": "stripe", "kind": "http", "label": "charges"}],
        "annotations": [{"path": "server/app.py", "note": "All routes here."}],
        "flows": [{"id": "f", "title": "Pay", "steps": [{"node": "web.core", "note": "Click"}, {"node": "api", "note": "Charge"}]}], "tour": [{"node": "api", "title": "Server", "note": "Hi"}]}
    repo = _repo(tmp_path, {
        "floorplan/architecture.json": json.dumps(arch),
        "web/src/app.js": "// The pages.\nexport const go = () => fetch('/charge', { method: 'POST' });\n", "web/src/app.test.js": "import { go } from './app.js';\ngo();\n",
        "server/app.py": "from flask import Flask\napp = Flask(__name__)\n\n\n@app.post('/charge')\ndef charge():\n    pass\n", "server/db/models.py": "X = 1\n",
        "server/pay.py": "URL = 'https://api.stripe.com/v1/charges'\n", "gen/out.js": "x\n"})
    g = S.build(repo)
    node = {f["p"]: f["n"] for f in g["files"]}
    assert node["web/src/app.js"] == "web.core" and node["web/src/app.test.js"] == "tests"      # exclude on `web` is inherited by web.core
    assert node["server/db/models.py"] == "api.db" and node["server/app.py"] == "api" and "gen/out.js" not in node
    assert g["meta"]["authored"] and g["meta"]["editor"] == "cursor" and any("[evil" in p for p in g["meta"]["problems"])
    assert {"a": "f:server/pay.py", "b": "n:stripe", "k": "http", "w": 1, "names": []} in g["links"]
    assert any(l["a"] == "n:api" and l["b"] == "n:stripe" and l["label"] == "charges" for l in g["links"])
    assert any(l["a"] == "f:web/src/app.js" and l["b"].startswith("r:") and l["k"] == "http" for l in g["links"])
    assert g["flows"][0]["steps"][0]["node"] == "n:web.core" and g["tour"][0]["node"] == "n:api" and g["annotations"][0]["path"] == "server/app.py"
    stats = {n["id"]: n["stats"] for n in g["nodes"]}
    assert stats["api"]["files"] == 3 and stats["api"]["endpoints"] == 1 and stats["web"]["files"] == 1


# FR-1092 AC-507: without architecture.json, parts come from folders: tests are their own part and a part with more than 24 files groups folders into children.
def test_ac507_automatic_parts(tmp_path):
    files = {f"app/pages/p{i}.js": f"// page {i}\nexport const p{i} = 1;\n" for i in range(14)}
    files.update({f"app/forms/f{i}.js": f"export const f{i} = 1;\n" for i in range(14)})
    files.update({"app/index.js": "export const a = 1;\n", "tests/a_test.py": "def test_a():\n    pass\n", "scripts/run.sh": "#!/bin/sh\necho hi\n"})
    g = S.build(_repo(tmp_path, files))
    kinds = {n["id"]: n["kind"] for n in g["nodes"]}
    assert kinds["tests"] == "test" and kinds["scripts"] == "script" and "app.pages" in kinds and "app.forms" in kinds
    assert {f["p"]: f["n"] for f in g["files"]}["app/pages/p0.js"] == "app.pages" and not g["meta"]["authored"]


# FR-1092 AC-509: screens (lazy-loaded routes, pages) know what is behind them; Health reports what it checked and never copies a secret.
def test_ac509_screens_health_and_recent_work(tmp_path):
    secret = "sk_live_" + "Abc123xyz456Qwe789Rty012"
    files = {
        "web/index.html": "<html><head><title>Shop</title></head><body><script type=module src=\"app.js\"></script></body></html>\n",
        "web/app.js": "const ROUTES = {\n  orders: { load: () => import('./orders.js') },\n};\nexport { ROUTES };\n",
        "web/orders.js": "import { list } from './api.js';\nexport const mount = () => list();\n",
        "web/api.js": "export const list = () => fetch('/api/orders');\n",
        "server/app.py": ("from flask import Flask\nfrom server.db import rows\napp = Flask(__name__)\n\n\n@app.get('/api/orders')\ndef orders():\n    return rows()\n\n\n@app.post('/api/purge')\ndef purge():\n    pass\n"),
        "server/db.py": "def rows():\n    return []\n",
        "server/pay.py": f"KEY = '{secret}'\nHEADERS = {{'Access-Control-Allow-Origin': '*'}}\n",
        "web/env.js": "const k = import.meta.env.VITE_STRIPE_SECRET_KEY;\n",
        "server/big.py": "\n".join(f"x{i} = {i}" for i in range(1100)) + "\n", "server/orphan.py": "def lonely():\n    pass\n"}
    repo = _repo(tmp_path, files, commit=True)
    (repo / "server" / "db.py").write_text("def rows():\n    return [1]\n", encoding="utf-8")        # an uncommitted change
    g = S.build(repo)
    screen = {s["name"]: s for s in g["screens"]}["Orders"]
    behind = {b["id"]: b["kind"] for b in screen["behind"]}
    assert behind["f:web/orders.js"] == "screen" and behind["f:web/api.js"] == "part"
    assert "request" in behind.values() and behind["f:server/app.py"] == "server" and behind["f:server/db.py"] in ("data", "part")
    assert any(s["url"] == "/web/index.html" for s in g["screens"])
    ids = {i["id"] for i in g["health"]["issues"]}
    assert {"secret:server/pay.py", "exposed:web/env.js", "cors", "open-endpoints", "big-files", "unused"} <= ids
    assert secret not in json.dumps(g["health"]) and g["health"]["checked"]["endpoints"] == 2 and g["health"]["checked"]["mutating"] == 1
    assert g["health"]["summary"]["high"] >= 2
    tasks = g["recent"]["tasks"]
    assert tasks[0]["kind"] == "uncommitted" and tasks[0]["items"][0] == {"ref": "server/db.py", "change": "changed", "note": ""}
    assert any(t["title"] == "Add refunds" and any(i["change"] == "new" for i in t["items"]) for t in tasks)
