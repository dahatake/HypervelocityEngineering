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

def test_structural_links_are_enforced(sample):
    rd = SAMPLE_RD
    rd = rd.replace("- 対象エンティティ: 申請　関係する状態: 下書き　参照パラメータ: PARAM-001",
                    "- 対象エンティティ: 申請、伝票　関係する状態: 下書き→提出済み　参照パラメータ: なし")          # CHK-25 x3
    rd = rd.replace("- 上位: G-001　出典: 依頼原文", "- 上位: G-001　出典: SRC-404\n- 関連する既存資産: 共通部品「下書き保存」　関連: FR-404")  # CHK-24, CHK-27
    rd = rd.replace("## 10. 仮定", "#### FR-002 申請の取消\n- 要求: 申請者は提出前の申請を取り消せる。\n"
                    "- 決定状態: 承認済み（依頼 2026-10-08）　出自: 依頼原文　優先度: SHOULD（誤入力の回復）\n"
                    "- 上位: G-001　出典: 依頼原文\n- 対象エンティティ: 申請　関係する状態: 下書き　参照パラメータ: なし\n\n## 10. 仮定")
    sample.write("docs/requirements-definition.md", rd)
    sample.py("next-id.py", "--sync", "--adopt", check=True)
    sample.write("docs/catalog.md",
                 "## 機能\n\n| 要求 ID | 題名 | 決定状態 | 実装ファイル | テスト | 使っている共通部品 |\n|---|---|---|---|---|---|\n"
                 "| FR-001 | 古い題名 | 承認済み | 未実装 | 未実装 | 下書き保存、通知 |\n\n"
                 "## テーブル\n\n| テーブル名 | 定義ファイル | 正本のシステム | 関連する要求 ID |\n|---|---|---|---|\n"
                 "| drafts | - | 本システム | FR-777 |\n\n"
                 "## 共通部品\n\n| 部品名 | ファイル | 用途 | 使っている要求 ID |\n|---|---|---|---|\n"
                 "| 下書き保存 | - | 下書きの保持 | なし |\n")
    proc = sample.py("rdcheck.py", "check", "--base", "none")
    lines = [l for l in proc.stdout.splitlines() if l.startswith("ERROR")]
    def has(chk, text):
        return any(chk in l and text in l for l in lines)
    assert has("CHK-24", "SRC-404") and has("CHK-24", "FR-404") and has("CHK-24", "FR-777"), proc.stdout
    assert has("CHK-25", "伝票") and has("CHK-25", "提出済み") and has("CHK-25", "{PARAM-001}"), proc.stdout
    assert has("CHK-07", "FR-002") and has("CHK-07", "題名"), proc.stdout
    assert has("CHK-27", "通知") and has("CHK-27", "下書き保存"), proc.stdout
    assert proc.returncode == 1


def test_orphans_are_warned(sample):
    rd = SAMPLE_RD.replace("| PARAM-001 | 下書きの保持期間 | 30 | 日 | 依頼原文 | 承認済み |",
                           "| PARAM-001 | 下書きの保持期間 | 30 | 日 | 依頼原文 | 承認済み |\n| PARAM-002 | 未使用 | 5 | 件 | 依頼原文 | 承認済み |")
    rd = rd.replace("| 申請 | 下書き | 入力を始めたとき |", "| 申請 | 下書き | 入力を始めたとき |\n| 請求 | 発行済み | 発行したとき |")
    sample.write("docs/requirements-definition.md", rd)
    sample.py("next-id.py", "--sync", "--adopt", check=True)
    proc = sample.py("rdcheck.py", "check", "--base", "none")
    assert proc.returncode == 0, proc.stdout
    warns = [l for l in proc.stdout.splitlines() if l.startswith("WARN CHK-26")]
    assert any("PARAM-002" in l for l in warns) and any("請求" in l for l in warns), proc.stdout
    assert not any("PARAM-001" in l or "SRC-001" in l for l in warns), proc.stdout


def test_trace_follows_links_both_ways(sample):
    sample.py("ledger.py", "add", "--req", "FR-001", "--ac", "AC-001", "--title", "t", "--layer", "e2e",
              "--command", "python -c \"raise SystemExit(0)\"", check=True)
    sample.write("tests/unit/test_drafts.py", "# FR-001 AC-002\n")
    data = json.loads(sample.py("rdcheck.py", "trace", "FR-001", "G-001", "申請", "PARAM-001", "--json", check=True).stdout)
    fr, g, ent, param = data
    assert fr["upper"][0]["id"] == "G-001" and fr["params"] == {"PARAM-001": "30日"}
    assert fr["entities"] == {"申請": ["下書き"]} and fr["catalog"]["題名"] == "入力の中断と再開"
    acs = {a["id"]: a for a in fr["acs"]}
    assert acs["AC-001"]["cases"] == ["E2E-001(not_run)"] and acs["AC-002"]["code"] == ["tests/unit/test_drafts.py"]
    assert g["requirements"] == ["FR-001"] and ent["requirements"] == ["FR-001"]
    assert "FR-001" in param["referenced_by"]
    text = sample.py("rdcheck.py", "trace", "FR-001", check=True).stdout
    assert "G-001" in text and "AC-001 [system]" in text
    assert sample.py("rdcheck.py", "trace", "FR-999").returncode == 1
