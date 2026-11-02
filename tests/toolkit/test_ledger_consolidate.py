"""System Test の数の最小化: ledger.py の consolidate・cost と、同じ要求・同じ層の add の拒否。"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("ledger_mod_consolidate", SOURCE / "scripts" / "ledger.py")
L = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(L)


def case(cid, cmd, req="FR-001", ac="AC-001", layer="e2e", **kw):
    return {"id": cid, "requirement_ids": [req], "ac_ids": [ac], "title": cid, "layer": layer, "command": cmd,
            "canary": False, "status": "pass", "history": [], **kw}


F = "tests/system/e2e/test_x.py"


def test_merge_plan_groups_same_file_layer_and_requirements_only():
    data = {"cases": [
        case("E2E-001", f"python -m pytest {F}::test_a -q"),
        case("E2E-002", f'python -m pytest {F} -k "ac2" -q', ac="AC-002"),
        case("E2E-003", f"python -m pytest {F}::test_c -q", req="FR-002", ac="AC-003"),   # 別の要求
        case("E2E-004", f"python -m pytest {F}::test_d -q", layer="contract"),             # 別の層
        case("E2E-005", f"python -m pytest {F}::test_e -q", canary=True),                  # canary は残す
        case("E2E-006", f"python -m pytest {F}::test_f -q", status="blocked"),             # blocked は対象外
        case("E2E-007", "npx playwright test x.spec.ts"),                                  # pytest 以外は対象外
    ]}
    plan = L.merge_plan(data)
    assert [[c["id"] for c in g] for g in plan] == [["E2E-001", "E2E-002"]]


def test_merged_command_selects_the_union_and_whole_file_wins():
    a = case("E2E-001", f"python -m pytest {F}::test_a -q")
    b = case("E2E-002", f'python -m pytest {F} -k "ac2 or ac3" -q', ac="AC-002")
    cmd = L.merged_command([a, b])
    assert cmd == f'python -m pytest {F} -k "test_a or (ac2 or ac3)" -q'
    assert L.parse_pytest(cmd) == (F, "", "test_a or (ac2 or ac3)")  # ledger run がまとめて実行できる形のまま
    whole = case("E2E-003", f"python -m pytest {F} -q")
    assert L.merged_command([a, whole]) == f"python -m pytest {F} -q"


def _add(sample, ac, title, layer="api", extra=()):
    return sample.py("ledger.py", "--by", "test-designer", "add", "--req", "FR-001", "--ac", ac, "--title", title,
                     "--layer", layer, "--command", "python -m pytest tests/system/test_x.py -q", *extra)


def test_consolidate_cli_unions_acs_blocks_the_rest_and_keeps_history(sample):
    sample.write("tests/system/test_x.py", "def test_a():\n    pass\n")
    sample.py("ledger.py", "--by", "test-designer", "add", "--req", "FR-001", "--ac", "AC-001", "--title", "a",
              "--layer", "api", "--command", "python -m pytest tests/system/test_x.py::test_a -q", check=True)
    # 同じ要求・同じ層の 2 件目は既定で拒否される
    refused = _add(sample, "AC-001", "b")
    assert refused.returncode != 0
    forced = _add(sample, "AC-001", "b", extra=("--new-case-reason", "テスト用に別ケース"))
    assert forced.returncode == 0, forced.stdout + forced.stderr
    out = sample.py("rdcheck.py", "check", "--base", "none").stdout
    assert "CHK-34" in out
    plan = sample.py("ledger.py", "consolidate", check=True).stdout
    assert "IT-001 <- IT-002" in plan and "--apply" in plan
    assert json.loads(sample.read("tests/system/ledger.json"))["cases"][1]["status"] != "blocked"  # 計画だけでは書かない

    sample.py("ledger.py", "--by", "conductor", "consolidate", "--apply", check=True)
    led = json.loads(sample.read("tests/system/ledger.json"))
    keep, gone = led["cases"][0], led["cases"][1]
    assert keep["status"] == "not_run" and "AC-001" in keep["ac_ids"]
    assert gone["status"] == "blocked" and gone["merged_into"] == keep["id"]
    assert any("統合" in h["reason"] for h in gone["history"])
    assert "CHK-34" not in sample.py("rdcheck.py", "check", "--base", "none").stdout
    assert sample.py("rdcheck.py", "check", "--base", "HEAD").returncode == 0  # 削除ではなく blocked なので CHK-12 に触れない


def test_cost_reports_and_budget_check_fails_when_exceeded(sample):
    sample.py("ledger.py", "--by", "test-designer", "add", "--req", "FR-001", "--ac", "AC-001", "--title", "a",
              "--layer", "api", "--command", "python -c pass", check=True)
    out = sample.py("ledger.py", "cost", check=True).stdout
    assert "cases: active 1 / total 1" in out and "budget:" in out
    cfg_path = "scripts/ebak.config.json"
    cfg = json.loads(sample.read(cfg_path))
    cfg["system_test"] = {"budget": {"max_active_cases": 0}}
    sample.write(cfg_path, json.dumps(cfg))
    over = sample.py("ledger.py", "cost", "--check")
    assert over.returncode == 1 and "BUDGET: 有効なケース 1 > max_active_cases 0" in over.stdout
