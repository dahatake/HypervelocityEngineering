import json

from conftest import SAMPLE_RD, git
from test_gate import denied, shell, start


def fixes(out):
    return [l for l in out.splitlines() if l.startswith("FIX ")]


def manual(out):
    return [l for l in out.splitlines() if l.startswith("MANUAL ")]


def test_clean_sample_has_nothing_to_fix(sample):
    proc = sample.py("rdfix.py")
    assert proc.returncode == 0, proc.stdout
    assert "rdfix: fix=0" in proc.stdout


def test_catalog_follows_requirements_definition(sample):
    rd = SAMPLE_RD.replace("決定状態: 承認済み（依頼 2026-10-08）", "決定状態: 保留") + """
#### FR-002 一覧の表示
- 要求: 利用者は、自分の申請の一覧を確認できる。
- 決定状態: 承認待ち　優先度: SHOULD
- 上位: G-001
- 対象エンティティ: 申請　関係する状態: なし　参照パラメータ: なし
"""
    sample.write("docs/requirements-definition.md", rd)
    sample.write("src/list.py", "# FR-002\n")
    sample.write("tests/unit/test_list.py", "# FR-002\n")
    sample.write("docs/catalog.md", sample.read("docs/catalog.md")
                 + "| FR-009 | 消した要求 | 承認済み | 未実装 | 未実装 | なし |\n"
                 + "| FR-001 | 入力の中断と再開 | 承認済み | 未実装 | 未実装 | なし |\n")
    sample.py("next-id.py", "--sync", "--adopt", check=True)

    proc = sample.py("rdfix.py")
    assert proc.returncode == 1
    out = proc.stdout
    assert any("FR-001 の決定状態を 承認済み → 保留" in l for l in fixes(out))
    assert any("FR-001 の重複した行" in l for l in fixes(out))
    assert any("要求定義書にない FR-009" in l for l in fixes(out))
    assert any("FR-002（承認待ち）の行がない" in l for l in fixes(out))
    assert "保留" not in sample.read("docs/catalog.md")  # dry run writes nothing

    proc = sample.py("rdfix.py", "--apply")
    assert proc.returncode == 0, proc.stdout
    cat = sample.read("docs/catalog.md")
    assert "| FR-001 | 入力の中断と再開 | 保留 | 未実装 | 未実装 | なし |" in cat
    assert cat.count("| FR-001 |") == 1 and "FR-009" not in cat
    assert "| FR-002 | 一覧の表示 | 承認待ち | src/list.py | tests/unit/test_list.py | - |" in cat
    assert "CHK-07" not in sample.py("rdcheck.py", "check", "--base", "none").stdout
    assert sample.py("rdfix.py").returncode == 0  # converged


def test_catalog_file_references_follow_renames(sample):
    sample.write("src/old_name.py", "# FR-001\n")
    sample.commit("add impl")
    git(sample.path, "mv", "src/old_name.py", "src/new_name.py")
    sample.commit("rename")
    cat = sample.read("docs/catalog.md").replace("| 未実装 | 未実装 | なし |", "| `src/old_name.py`, src/gone.py | 未実装 | なし |")
    sample.write("docs/catalog.md", cat)
    assert "CHK-08" in sample.py("rdcheck.py", "check", "--base", "none").stdout
    out = sample.py("rdfix.py", "--apply").stdout
    assert any("src/old_name.py は src/new_name.py に名前が変わって" in l for l in fixes(out))
    assert any("src/gone.py が存在しない" in l for l in fixes(out))
    assert "| FR-001 | 入力の中断と再開 | 承認済み | src/new_name.py | 未実装 | なし |" in sample.read("docs/catalog.md")
    assert "CHK-08" not in sample.py("rdcheck.py", "check", "--base", "none").stdout


def test_registry_states_and_duplicates_but_not_reuse(sample):
    reg = sample.read("docs/id-registry.md")
    fr_row = next(l for l in reg.splitlines() if l.startswith("| FR-001 |"))
    q_row = next(l for l in reg.splitlines() if l.startswith("| Q-001 |"))
    reg = reg.replace(fr_row, fr_row.replace("使用中", "廃止")) + fr_row.replace("使用中", "廃止") + "\n"
    reg = reg.replace(q_row, q_row.replace("使用中", "削除済み"))
    sample.write("docs/id-registry.md", reg)
    sample.write("docs/requirements-definition.md", SAMPLE_RD.replace("- 受入基準 AC-002:", "- 受入基準 AC-077:"))

    out = sample.py("rdfix.py", "--only", "registry").stdout
    assert any("FR-001 の状態を 廃止 → 使用中" in l for l in fixes(out))
    assert any("FR-001 の重複した行" in l for l in fixes(out))
    assert any("AC-002 の状態を 使用中 → 削除済み" in l for l in fixes(out))
    assert any("Q-001 は ID 台帳で削除済み" in l and "rd-author" in l for l in manual(out))
    assert any("AC-077 が ID 台帳にありません" in l for l in manual(out))

    sample.py("rdfix.py", "--only", "registry", "--apply", check=True)
    reg = sample.read("docs/id-registry.md")
    assert reg.count("| FR-001 |") == 1 and "| FR-001 | FR | 使用中 |" in reg
    assert "| Q-001 | Q | 削除済み |" in reg  # never revived by rdfix (CHK-02 stays visible)
    assert "AC-077" not in reg

    sample.py("rdfix.py", "--only", "registry", "--adopt", "--apply", check=True)
    assert "| AC-077 | AC | 使用中 |" in sample.read("docs/id-registry.md")


def test_ledger_repair_keeps_review_signals(sample):
    sample.py("ledger.py", "add", "--req", "FR-001", "--ac", "AC-001", "--title", "t", "--layer", "e2e",
              "--command", "python -c \"raise SystemExit(0)\"", check=True)
    led = json.loads(sample.read("tests/system/ledger.json"))
    led["cases"][0]["requirement_ids"] = ["FR-099"]
    del led["cases"][0]["history"]
    led["ac_digests"]["AC-002"] = "sha256:dead"
    led["ac_digests"]["AC-001"] = "sha256:stale"
    sample.write("tests/system/ledger.json", json.dumps(led, ensure_ascii=False, indent=2))

    out = sample.py("rdfix.py", "--only", "ledger", "--apply").stdout
    assert any("E2E-001 の requirement_ids" in l for l in fixes(out))
    assert any("AC-002 の ac_digests を取り除きます" in l for l in fixes(out))
    assert any("AC-001 の本文が台帳の作成時から変わっています" in l and "test-designer" in l for l in manual(out))
    led = json.loads(sample.read("tests/system/ledger.json"))
    case = led["cases"][0]
    assert case["requirement_ids"] == ["FR-001"]
    assert case["history"][-1]["by"] == "rdfix" and "requirement_ids" in case["history"][-1]["change"]
    assert led["ac_digests"] == {"AC-001": "sha256:stale"}  # stale digest is left for test-designer


def test_gitignore_and_run_history(sample):
    gi = "\n".join(l for l in sample.read(".gitignore").splitlines() if "work" not in l) + "\n"
    sample.write(".gitignore", gi)
    row = "| 202610080900 | 2026-10-08 09:00 | 10:00 | abc | 全件完了 | FR-001 | - | 100% | 1h | 100% | - | 1 | 1 |\n"
    sample.write("docs/run-history.md", sample.read("docs/run-history.md") + row + row)
    out = sample.py("rdfix.py", "--apply").stdout
    assert any(".gitignore" in l for l in fixes(out)) and any("run-id 202610080900 の重複" in l for l in fixes(out))
    assert "/work/" in sample.read(".gitignore")
    assert sample.read("docs/run-history.md").count("202610080900") == 1


def test_verify_prints_hint(sample):
    sample.write("docs/catalog.md", sample.read("docs/catalog.md").replace("| 承認済み |", "| 保留 |"))
    out = sample.py("verify.py", "--docs-only").stdout
    assert "FAIL rdcheck" in out and "HINT rdfix" in out


def test_apply_refused_for_workers(sample):
    git(sample.path, "switch", "-q", "-c", "work/r/I-01")
    assert sample.py("rdfix.py", "--apply").returncode == 2
    git(sample.path, "switch", "-q", "main")
    start(sample)
    assert shell(sample, "python scripts/rdfix.py") == {}
    sample.gate("subagent-start", {"agentName": "implementer"})
    assert denied(shell(sample, "python scripts/rdfix.py --apply"), "G-2")
    sample.gate("subagent-stop", {"agentName": "implementer", "agentId": "i1", "response": "RESULT: done"})
    sample.gate("subagent-start", {"agentName": "rd-author"})
    assert denied(shell(sample, "python scripts/rdfix.py --apply"), "G-5")
    assert shell(sample, "python scripts/rdfix.py --apply --only catalog,registry") == {}

def test_common_parts_follow_function_table(sample):
    sample.write("docs/catalog.md", sample.read("docs/catalog.md").replace("| 未実装 | 未実装 | なし |", "| 未実装 | 未実装 | 下書き保存 |")
                 + "\n## 共通部品\n\n| 部品名 | ファイル | 用途 | 使っている要求 ID |\n|---|---|---|---|\n"
                 + "| 下書き保存 | - | 下書きの保持 | FR-404 |\n")
    assert "CHK-27" in sample.py("rdcheck.py", "check", "--base", "none").stdout
    proc = sample.py("rdfix.py", "--only", "catalog", "--apply")
    assert proc.returncode == 0, proc.stdout
    assert "| 下書き保存 | - | 下書きの保持 | FR-001 |" in sample.read("docs/catalog.md")
    out = sample.py("rdcheck.py", "check", "--base", "none").stdout
    assert "CHK-27" not in out and "CHK-24" not in out, out
