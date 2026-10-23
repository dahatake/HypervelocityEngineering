"""要求・受入基準・System Test のケースの数の最適化（FR-1078 AC-421〜AC-424）の統合試験。"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("eabk_toolkit_fixtures", SOURCE / "tests" / "toolkit" / "conftest.py")
_fx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fx)
empty_repo, repo, sample = _fx.empty_repo, _fx.repo, _fx.sample  # pytest fixtures


def test_ledger_add_refuses_duplicate_ac_and_check_warns(sample):
    """似た System Test を増やさない: 同じ AC の有効なケースがあれば add を拒否し、update で拡張させる。"""
    # FR-1078 AC-422 AC-423
    sample.py("ledger.py", "add", "--req", "FR-001", "--ac", "AC-001", "--title", "再開", "--layer", "e2e",
              "--command", "python -c \"raise SystemExit(0)\"", check=True)
    proc = sample.py("ledger.py", "add", "--req", "FR-001", "--ac", "AC-001", "--title", "再開2", "--layer", "e2e",
                     "--command", "python -c \"raise SystemExit(0)\"")
    assert proc.returncode != 0 and "E2E-001" in (proc.stdout + proc.stderr) and "update" in (proc.stdout + proc.stderr)
    led = json.loads(sample.read("tests/system/ledger.json"))
    assert [c["id"] for c in led["cases"]] == ["E2E-001"]

    # 明示的な理由があれば別のケースにでき、理由は history に残り、CHK-33 が警告する
    cid = sample.py("ledger.py", "add", "--req", "FR-001", "--ac", "AC-001", "--title", "API 層", "--layer", "api",
                    "--command", "python -c \"raise SystemExit(0)\"", "--new-case-reason", "API 層の契約は別に確かめる",
                    check=True).stdout.strip()
    led = json.loads(sample.read("tests/system/ledger.json"))
    case = next(c for c in led["cases"] if c["id"] == cid)
    assert any("API 層の契約" in x["reason"] for x in case["history"])
    out = sample.py("rdcheck.py", "check", "--base", "none").stdout
    assert "WARN CHK-33" in out and "AC-001" in out

    # 統合（片方を block）すれば警告は消え、block 済みのケースしかない AC には add できる
    sample.py("ledger.py", "block", cid, "--reason", "E2E-001 に統合", check=True)
    assert "CHK-33" not in sample.py("rdcheck.py", "check", "--base", "none").stdout
    sample.py("ledger.py", "block", "E2E-001", "--reason", "作り直し", check=True)
    sample.py("ledger.py", "add", "--req", "FR-001", "--ac", "AC-001", "--title", "再開3", "--layer", "e2e",
              "--command", "python -c \"raise SystemExit(0)\"", check=True)


def test_rdcheck_similar(sample):
    # FR-1078 AC-421
    rd =  sample.read("docs/requirements-definition.md").replace(
        "## 10. 仮定・未解決事項",
        "#### FR-002 入力の一時保存と再開\n"
        "- 要求: 申請を入力している利用者は、入力を中断して後で再開したときに、入力済みの内容を確認できる。\n"
        "- 決定状態: 承認済み（依頼 2026-10-08）　出自: 依頼原文　優先度: SHOULD（同上）\n"
        "- 上位: G-001　出典: 依頼原文\n"
        "- 対象エンティティ: 申請　関係する状態: 下書き　参照パラメータ: なし\n"
        "- 受入基準 AC-003: 入力途中で画面を閉じた利用者が再び開いたとき、入力済みの値が失われない。\n"
        "  - 検証レベル: integration\n\n"
        "## 10. 仮定・未解決事項")
    sample.write("docs/requirements-definition.md", rd)
    out = sample.py("rdcheck.py", "similar", "入力を中断して再開したときに入力済みの内容を確認できる", "--kind", "FR", check=True).stdout
    assert out.splitlines()[0].split("\t")[1] in ("FR-001", "FR-002") and "既存" in out
    out = sample.py("rdcheck.py", "similar", "FR-001", "--json", check=True).stdout
    hits = json.loads(out)
    assert hits[0]["id"] == "FR-002" and all(x["id"] != "FR-001" for x in hits)
    out = sample.py("rdcheck.py", "similar", "--pairs", "--json", check=True).stdout
    pairs = {(p["a"], p["b"]) for p in json.loads(out)}
    assert ("FR-001", "FR-002") in pairs and ("AC-001", "AC-003") in pairs
    assert "似た項目はありません" in sample.py("rdcheck.py", "similar", "請求書の PDF を出力する", check=True).stdout
    stats = json.loads(sample.py("rdcheck.py", "stats", check=True).stdout)
    assert stats["similar_pairs"] >= 2 and stats["ledger_shared_acs"] == 0


def test_role_docs_require_reuse_and_are_distributed():
    # FR-1078 AC-424
    import importlib.util
    docs = {
        ".github/agents/rd-author.agent.md": ("rdcheck.py similar", "統合"),
        ".github/skills/requirement-definition/SKILL.md": ("rdcheck.py similar", "既存の項目を変更"),
        ".github/agents/test-designer.agent.md": ("CHK-33", "ledger.py update", "統合"),
        ".github/agents/conductor.agent.md": ("既存の項目を変更", "similar_pairs"),
        ".github/skills/rd-audit/SKILL.md": ("rdcheck.py similar --pairs", "CHK-33"),
    }
    for rel, words in docs.items():
        text = (SOURCE / rel).read_text(encoding="utf-8")
        assert all(w in text for w in words), rel
    spec = importlib.util.spec_from_file_location("eabk_install", SOURCE / "tools" / "install.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for rel in [*docs, "scripts/rdcheck.py", "scripts/ledger.py"]:
        assert rel in mod.MANAGED, rel
