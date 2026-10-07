import json

from conftest import SAMPLE_RD


def codes(proc):
    return [l.split()[1] for l in proc.stdout.splitlines() if l.startswith("ERROR")]


def test_template_passes(repo):
    proc = repo.py("verify.py")
    assert proc.returncode == 0, proc.stdout
    assert "verify: PASS" in proc.stdout


def test_sample_passes_with_warnings(sample):
    proc = sample.py("rdcheck.py", "check", "--base", "none")
    assert proc.returncode == 0, proc.stdout
    assert "WARN CHK-10" in proc.stdout  # system AC without a ledger case (before stage 4)
    assert "WARN CHK-09" in proc.stdout  # MUST requirement not implemented yet


def test_strict_ledger_turns_missing_case_into_error(sample):
    proc = sample.py("rdcheck.py", "check", "--base", "none", "--strict-ledger")
    assert proc.returncode == 1
    assert "CHK-10" in codes(proc)


def test_show_prints_only_the_block(sample):
    out = sample.py("rdcheck.py", "show", "FR-001", check=True).stdout
    assert "#### FR-001" in out and "AC-002" in out and "## 10." not in out
    out = sample.py("rdcheck.py", "show", "Q-001", check=True).stdout
    assert "Q-001" in out and "| ID |" in out


def test_list_and_stats(sample):
    out = sample.py("rdcheck.py", "list", "--level", "system", check=True).stdout
    assert out.startswith("AC-001")
    stats = json.loads(sample.py("rdcheck.py", "stats", check=True).stdout)
    assert stats["requirements"] == 1 and stats["blocked_acs"] == 1 and stats["open_questions"] == 1


def test_detects_typical_defects(sample):
    bad = SAMPLE_RD
    bad = bad.replace("- 上位: G-001　出典: 依頼原文", "- 上位: G-009　出典: 依頼原文")              # CHK-04
    bad = bad.replace("承認済み（依頼 2026-10-08）", "承認済み")                                    # CHK-06
    bad = bad.replace("保持期間は {PARAM-001} とする。", "保持期間は {PARAM-777} とし、3 日で通知する。申込も同様。")  # CHK-16, CHK-14, CHK-15
    bad = bad.replace("  - BLOCKED: Q-001", "  - BLOCKED: Q-404")                                  # CHK-18
    bad = bad.replace("  - 検証レベル: system\n", "")                                              # CHK-20
    bad += "\n#### FR-001 重複\n- 要求: x\n"                                                       # CHK-01
    sample.write("docs/requirements-definition.md", bad)
    sample.write("docs/catalog.md", "| 要求 ID | 題名 | 決定状態 | 実装ファイル | テスト | 使っている共通部品 |\n|---|---|---|---|---|---|\n"
                                    "| FR-001 | x | 承認待ち | src/missing.ts | 未実装 | なし |\n| FR-999 | x | 承認済み | 未実装 | 未実装 | なし |\n")  # CHK-07, 08
    sample.write("src/app.py", "# FR-123 AC-001\n")                                               # CHK-19
    proc = sample.py("rdcheck.py", "check", "--base", "none")
    got = set(codes(proc))
    for c in ("CHK-01", "CHK-04", "CHK-06", "CHK-07", "CHK-08", "CHK-16", "CHK-18", "CHK-19", "CHK-20"):
        assert c in got, (c, proc.stdout)
    assert "WARN CHK-14" in proc.stdout and "WARN CHK-15" in proc.stdout


def test_unregistered_and_reused_ids(sample):
    rd = SAMPLE_RD.replace("## 10. 仮定", "#### FR-002 手で振った ID\n- 要求: x\n\n## 10. 仮定")
    sample.write("docs/requirements-definition.md", rd)
    proc = sample.py("rdcheck.py", "check", "--base", "none")
    assert any("FR-002 が ID 台帳にありません" in l for l in proc.stdout.splitlines())
    reg = sample.read("docs/id-registry.md").replace("| FR-001 | FR | 使用中 |", "| FR-001 | FR | 削除済み |")
    sample.write("docs/id-registry.md", reg)
    proc = sample.py("rdcheck.py", "check", "--base", "none")
    assert "CHK-02" in codes(proc)


def test_gitignore_and_temp_files(sample):
    sample.write(".gitignore", "node_modules/\n")
    sample.write("tests/system/run.log", "x")
    sample.commit("bad placement")
    proc = sample.py("rdcheck.py", "check", "--base", "none")
    msgs = [l for l in proc.stdout.splitlines() if "CHK-23" in l]
    assert any(".gitignore" in m for m in msgs) and any("run.log" in m for m in msgs)


def test_chk12_ledger_case_removed(sample):
    sample.py("ledger.py", "add", "--req", "FR-001", "--ac", "AC-001", "--title", "t", "--layer", "e2e",
              "--command", "python -c \"raise SystemExit(0)\"", check=True)
    sample.commit("add case")
    git_base = __import__("conftest").git(sample.path, "rev-parse", "HEAD")
    data = json.loads(sample.read("tests/system/ledger.json"))
    data["cases"] = []
    sample.write("tests/system/ledger.json", json.dumps(data))
    proc = sample.py("rdcheck.py", "check", "--base", git_base)
    assert any("CHK-12" in l and "削除" in l for l in proc.stdout.splitlines()), proc.stdout
