import json
import sys

APP = '''from flask import Flask
app = Flask(__name__)


@app.route("/orders", methods=["POST"])
def create_order():
    return "ok"


def cancel(order):
    if order["shipped"]:
        raise ValueError("shipped")
    order["state"] = "cancelled"
    return order
'''

SCHEMA = "CREATE TABLE orders (id INTEGER PRIMARY KEY);\n"


def make_app(repo):
    repo.write("src/orders/app.py", APP)
    repo.write("src/orders/models.sql", SCHEMA)
    repo.write("tests/test_orders.py", "def test_x():\n    assert True\n")
    repo.write("docs/design/orders-design.md", "# 注文の設計 ORD-12\n")
    repo.commit("existing app")


def test_scan_inventory(repo):
    make_app(repo)
    out = repo.py("adopt.py", "scan", check=True).stdout
    assert "SCAN" in out
    inv = json.loads(repo.read("docs/baseline/inventory.json"))
    paths = {f["path"]: f for f in inv["files"]}
    assert paths["src/orders/app.py"]["role"] == "source"
    assert paths["tests/test_orders.py"]["role"] == "test"
    assert paths["docs/design/orders-design.md"]["role"] == "design"
    assert not any(p.startswith((".github/agents", "scripts/", "docs/baseline")) for p in paths)
    assert any(r["path"] == "/orders" and r["method"] == "POST" for r in inv["routes"])
    assert {t["name"] for t in inv["tables"]} == {"orders"}
    assert inv["clusters"][0]["name"] == "orders"
    assert "orders" in repo.read("docs/baseline/inventory.md")


def test_request_draft_is_unapproved_and_scope_none(repo):
    make_app(repo)
    repo.py("adopt.py", "scan", check=True)
    out = repo.py("adopt.py", "request", "--stdout", check=True).stdout
    assert "adopt-existing" in out and "scope: なし" in out and "approval_policy: 厳格" in out
    assert "`orders`" in out and "orders-design.md" in out


def test_anchor_drift_and_whitespace_insensitive(repo):
    make_app(repo)
    repo.py("adopt.py", "scan", check=True)
    repo.py("adopt.py", "anchor", "SRC-010", "src/orders/app.py:10-14", check=True)
    assert repo.py("adopt.py", "check").returncode == 0
    repo.write("src/orders/app.py", APP.replace("    if order", "        if order").replace("shipped\"]:", "shipped\"]:  "))
    assert "DRIFT" not in repo.py("adopt.py", "check").stdout
    repo.write("src/orders/app.py", APP.replace("cancelled", "void"))
    res = repo.py("adopt.py", "check", "--strict")
    assert "DRIFT SRC-010" in res.stdout and res.returncode == 1


def test_anchor_rejects_bad_input(repo):
    make_app(repo)
    assert repo.py("adopt.py", "anchor", "X-1", "src/orders/app.py").returncode == 2
    assert repo.py("adopt.py", "anchor", "SRC-001", "nope.py:1-2").returncode == 2


REVERSE_RD = """
#### FR-050 注文のキャンセル
- 要求: 発送前の注文はキャンセルできる。
- 決定状態: {state}　出自: 逆生成　優先度: SHOULD（現状）
- 上位: G-001　出典: {src}
- 対象エンティティ: 申請　関係する状態: 下書き
- 受入基準 AC-050: 発送前の注文をキャンセルすると取消済みになる。
  - 検証レベル: system
"""


def test_check_guards_reverse_generated_requirements(sample):
    make_app(sample)
    sample.py("adopt.py", "scan", check=True)
    rd = sample.read("docs/requirements-definition.md")
    marker = "## 10. 仮定・未解決事項"
    base = rd.replace(marker, "@@" + marker)

    def write(state, src):
        sample.write("docs/requirements-definition.md", base.replace("@@", REVERSE_RD.format(state=state, src=src) + "\n"))

    write("承認待ち（逆生成）", "依頼原文")
    res = sample.py("adopt.py", "check")
    assert res.returncode == 1 and "FR-050" in res.stdout and "出典" in res.stdout
    write("承認済み（包括承認 2026-10-12・安全範囲）", "SRC-001")
    sample.py("adopt.py", "anchor", "SRC-001", "src/orders/app.py:10-14", check=True)
    res = sample.py("adopt.py", "check")
    assert res.returncode == 1 and "包括承認できません" in res.stdout
    write("承認待ち（逆生成）", "SRC-001")
    res = sample.py("adopt.py", "check")
    assert res.returncode == 0, res.stdout


def test_golden_record_check_and_regression(repo):
    make_app(repo)
    repo.write("tool.py", "import sys, datetime\nprint('hello', sys.stdin.read().strip(), datetime.datetime(2020,1,2,3,4,5).isoformat())\n")
    repo.commit("tool")
    repo.py("adopt.py", "golden", "add", "hello", "--stdin", "bob", "--", sys.executable, "tool.py", check=True)
    assert repo.py("adopt.py", "golden", "check").returncode == 1  # not recorded yet
    assert "RECORDED hello" in repo.py("adopt.py", "golden", "record", check=True).stdout
    assert "PASS hello" in repo.py("adopt.py", "golden", "check", check=True).stdout
    assert (repo.path / "tests/system/golden/snapshots/hello.json").exists()
    repo.write("tool.py", "import sys\nprint('hello!', sys.stdin.read().strip())\n")
    res = repo.py("adopt.py", "golden", "check")
    assert res.returncode == 1 and "FAIL hello" in res.stdout
    assert "SKIP hello" in repo.py("adopt.py", "golden", "record", "hello", check=True).stdout
    repo.py("adopt.py", "golden", "record", "hello", "--update", check=True)
    assert repo.py("adopt.py", "golden", "check").returncode == 0


def test_golden_rejects_nondeterministic(repo):
    make_app(repo)
    repo.write("rnd.py", "import random\nprint(random.random())\n")
    repo.py("adopt.py", "golden", "add", "rnd", "--", sys.executable, "rnd.py", check=True)
    res = repo.py("adopt.py", "golden", "record")
    assert res.returncode == 1 and "NONDETERMINISTIC" in res.stdout
    assert not (repo.path / "tests/system/golden/snapshots/rnd.json").exists()
