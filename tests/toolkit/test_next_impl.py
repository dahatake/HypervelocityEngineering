import json
import sys

from conftest import run

# FR-1015 AC-096..AC-100 / FR-1016 AC-101..AC-103

RD = """# 要求定義書

### 3.2 パラメータ（PARAM）

| ID | 名前 | 値 | 単位 | 根拠 | 決定状態 |
|---|---|---|---|---|---|
| PARAM-012 | 換算 | 60 | 分／要求 | 根拠 | 承認済み |

## 6. 要求

{reqs}
"""


def req(n, state="承認済み", pri="SHOULD", deps="なし", level="system", blocked=False, title=None):
    b = f"\n  - BLOCKED: Q-{n}" if blocked else ""
    return (f"#### FR-{n} {title or 'T' + n}\n- 要求: x\n- 決定状態: {state}　優先度: {pri}\n"
            f"- 関連する既存資産: {deps}\n- 受入基準 AC-{n}: a。\n  - 検証レベル: {level}{b}\n")


def setup(repo, reqs, catalog_rows="", cases=None):
    repo.write("docs/requirements-definition.md", RD.format(reqs="\n".join(reqs)))
    repo.write("docs/catalog.md",
               "# カタログ\n\n## 機能\n\n| 要求 ID | 題名 | 決定状態 | 実装ファイル | テスト | 使っている共通部品 |\n"
               "|---|---|---|---|---|---|\n" + catalog_rows)
    repo.write("src/a.py", "x = 1\n")
    repo.write("tests/system/ledger.json", json.dumps(
        {"version": 1, "ac_digests": {}, "cases": cases or []}, ensure_ascii=False))
    repo.commit("fixture")


def analyze(repo):
    r = repo.py("next-impl.py", "--json", check=True)
    return json.loads(r.stdout)


def row(n, impl=True):
    return f"| FR-{n} | T{n} | 承認済み | {'`src/a.py`' if impl else '未実装'} | 未実装 | なし |\n"


# FR-1015 AC-096 AC-099
def test_candidates_and_exclusions_without_changing_files(repo):
    setup(repo, [
        req("101"), req("102", state="承認待ち"), req("103", state="廃止"),
        req("104"), req("105"), req("106"), req("107", blocked=True), req("108", level="unit"),
    ], row("104") + row("105") + row("106") + row("108"),
        [{"id": "E1", "requirement_ids": ["FR-105"], "status": "pass"},
         {"id": "E2", "requirement_ids": ["FR-106"], "status": "pass"},
         {"id": "E3", "requirement_ids": ["FR-106"], "status": "fail"}])
    before = repo.read("docs/catalog.md")
    res = analyze(repo)
    assert set(res["scope"]) == {"FR-101", "FR-104", "FR-106"}
    reasons = {e["id"]: e["reason"] for e in res["excluded"]}
    assert reasons["FR-102"] == "未承認" and reasons["FR-103"] == "未承認"
    assert reasons["FR-105"] == "完了済み" and reasons["FR-108"] == "完了済み"
    assert reasons["FR-107"] == "BLOCKED"
    states = {c["id"]: c["state"] for c in res["candidates"]}
    assert states == {"FR-101": "未着手", "FR-104": "実装登録済み・試験未登録", "FR-106": "実装登録済み・試験未合格"}
    out = repo.py("next-impl.py", check=True).stdout
    assert "順位" in out and "除外一覧" in out and "scope: " in out
    assert repo.read("docs/catalog.md") == before
    assert run(["git", "status", "--porcelain"], repo.path).stdout.strip() == ""


# FR-1015 AC-097
def test_ranking_priority_dependents_state_id_and_determinism(repo):
    setup(repo, [
        req("201", pri="MAY"), req("202", pri="SHOULD"), req("203", pri="MUST"),
        req("204", pri="SHOULD", deps="FR-205"), req("205", pri="MAY"),
        req("206", pri="SHOULD"),
    ], row("206"))
    first = analyze(repo)["scope"]
    assert first == ["FR-203", "FR-206", "FR-202", "FR-205", "FR-204", "FR-201"]
    assert analyze(repo)["scope"] == first


# FR-1015 AC-098
def test_dependency_unapproved_excluded_and_cycle_warned(repo):
    setup(repo, [
        req("301", deps="FR-302"), req("302", state="承認待ち"),
        req("303", deps="FR-304"), req("304", deps="FR-303"), req("305"),
    ])
    r = repo.py("next-impl.py", "--json")
    assert r.returncode == 0
    res = json.loads(r.stdout)
    ex = {e["id"]: e for e in res["excluded"]}
    assert "FR-302" in ex["FR-301"]["detail"] and "依存先" in ex["FR-301"]["reason"]
    assert res["scope"] == ["FR-303", "FR-304", "FR-305"]
    assert "FR-303" in res["warnings"][0] and "FR-304" in res["warnings"][0]


# FR-1015 AC-100
def test_run_queue_doing_and_done(repo):
    setup(repo, [req("401"), req("402"), req("403")])
    repo.py("run-state.py", "start", "--no-branch", check=True)
    repo.py("run-state.py", "queue", "add", "--id", "i1", "--req", "FR-401", check=True)
    repo.py("run-state.py", "queue", "add", "--id", "i2", "--req", "FR-402", check=True)
    repo.py("run-state.py", "queue", "set", "i1", "--status", "doing", check=True)
    repo.py("run-state.py", "queue", "set", "i2", "--status", "doing", check=True)
    repo.py("run-state.py", "queue", "set", "i2", "--status", "done", check=True)
    res = analyze(repo)
    ex = {e["id"]: e["reason"] for e in res["excluded"]}
    assert ex == {"FR-401": "実行中", "FR-402": "完了済み"}
    assert res["scope"] == ["FR-403"]


def test_no_run_does_not_fail(repo):
    setup(repo, [req("501")])
    assert analyze(repo)["scope"] == ["FR-501"]


# FR-1016 AC-101
def test_duration_parsing_and_errors(repo):
    setup(repo, [req("601")])
    for arg, hours in (("60分", "1"), ("24時間", "24"), ("90m", "1.5"), ("1.5h", "1.5")):
        out = repo.py("build-request.py", arg, check=True).stdout
        assert f"max_hours: {hours}\n" in out
    for bad in ("60", "0分", "-1h", "abc", "10x"):
        r = repo.py("build-request.py", bad)
        assert r.returncode != 0 and "<run_options>" not in r.stdout
        assert "指定例" in r.stderr


# FR-1016 AC-102 AC-103
def test_scope_count_template_and_run_state_acceptance(repo):
    setup(repo, [req(str(700 + i)) for i in range(1, 6)])
    out = repo.py("build-request.py", "2h", check=True).stdout
    for tag in ("<request>", "<answers>", "<references>", "<run_options>"):
        assert tag in out
    opts = out.split("<run_options>\n")[1].split("</run_options>")[0]
    assert "scope: FR-701, FR-702\n" in opts  # 120 min / 60 = 2
    for line in ("approval_policy: 安全範囲は推奨どおり", "git_push: しない", "deploy: しない",
                 "external_write: しない", "paid_services: 使わない", "external_exposure: 公開しない"):
        assert line in opts
    assert "| 1 | FR-701 |" in out  # rank table in <request>
    short = repo.py("build-request.py", "10分", check=True).stdout
    assert "scope: FR-701\n" in short  # minimum 1
    big = repo.py("build-request.py", "100h", check=True).stdout
    assert "scope: FR-701, FR-702, FR-703, FR-704, FR-705\n" in big
    r = repo.py("run-state.py", "start", "--no-branch", "--options", opts.strip(), check=True)
    meta = json.loads((repo.path / "work" / "runs").glob("*/meta.json").__next__().read_text(encoding="utf-8"))
    assert meta["options"]["max_hours"] == "2"
    assert meta["options"]["scope"] == "FR-701, FR-702"


# FR-1016 AC-102
def test_no_candidates_exits_normally_without_request(repo):
    setup(repo, [req("801", state="承認待ち")])
    r = repo.py("build-request.py", "60分")
    assert r.returncode == 0
    assert "<run_options>" not in r.stdout and "FR-801" in r.stdout
