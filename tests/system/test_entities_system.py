"""System tests for FR-1020 / FR-1023 / FR-1024 / NFR-COMPAT-003 (command side).

Expected values come from the acceptance criteria only.  Command names are NOT in the requirements
or docs/catalog.md; the contract `python scripts/entities.py list|check|todo` is a provisional
assumption (see tests/system/entity_repo.py).  Failing because the command does not exist is expected
until the feature is implemented.
"""
from __future__ import annotations

import re
import subprocess
import sys

from entity_repo import CAT, DOC, make_other, make_standard, run_entities, snapshot


def _lines_with(out: str, *needles: str):
    return [ln for ln in out.splitlines() if all(n in ln for n in needles)]


# FR-1020 AC-151
def test_ac151_list_has_name_description_table_usecase_usage_and_no_new_file(tmp_path):
    repo = make_standard(tmp_path / "r")
    before = set(snapshot(repo))
    r = run_entities(repo, "list")
    assert r.returncode == 0, r.stdout + r.stderr
    order = _lines_with(r.stdout, "注文")
    assert order, r.stdout
    row = " ".join(order)
    assert "購入者が確定した購入内容" in row  # 説明（用語の定義）
    assert "orders" in row  # 管理テーブル
    assert "FR-001" in row and "FR-002" in row  # 使うユースケース
    assert "作成" in row and "参照" in row  # 使い方
    # union of 用語表 and 対象エンティティ: 顧客 appears only in 対象エンティティ, 在庫 only in 用語表
    assert _lines_with(r.stdout, "顧客") and _lines_with(r.stdout, "在庫")
    assert set(snapshot(repo)) == before, "導出で新しいファイルが作られた"


# FR-1020 AC-151 (reload reflects a change of the management data)
def test_ac151_list_changes_after_management_data_changes(tmp_path):
    repo = make_standard(tmp_path / "r")
    assert not _lines_with(run_entities(repo, "list").stdout, "出荷指示")
    p = repo / DOC
    p.write_text(p.read_text(encoding="utf-8").replace("対象エンティティ: 注文、顧客", "対象エンティティ: 注文、顧客、出荷指示", 1), encoding="utf-8")
    assert _lines_with(run_entities(repo, "list").stdout, "出荷指示")


# FR-1020 AC-151 (abnormal: nothing is inferred for an entity without data)
def test_ac151_entity_without_table_is_not_given_a_guessed_table(tmp_path):
    repo = make_standard(tmp_path / "r")
    row = " ".join(_lines_with(run_entities(repo, "list").stdout, "顧客"))
    assert "orders" not in row


# FR-1023 AC-159
def test_ac159_check_without_source_reports_unset_and_keeps_verify_result(tmp_path):
    repo = make_standard(tmp_path / "r")
    verify = [sys.executable, "scripts/verify.py", "--docs-only"]
    kw = dict(cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace")
    v0 = subprocess.run(verify, **kw)
    r = run_entities(repo, "check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "企業データカタログ: 未設定（照合していない）" in r.stdout
    v1 = subprocess.run(verify, **kw)
    def _stable(out):  # 日時入りのログパス（work/logs/verify-<日時>-*.log）の行は比較しない
        return [ln for ln in out.splitlines() if not re.search(r"verify-\d[\w-]*\.log", ln)]
    assert (v0.returncode, _stable(v0.stdout)) == (v1.returncode, _stable(v1.stdout))


# FR-1024 AC-163
def test_ac163_todo_one_per_entity_with_reason_when_source_unset(tmp_path):
    repo = make_standard(tmp_path / "r")
    names = ["注文", "顧客", "在庫"]  # FR-1020 の一覧の全行
    before = snapshot(repo)
    r = run_entities(repo, "todo")
    assert r.returncode == 0, r.stdout + r.stderr
    todo = _lines_with(r.stdout, "企業カタログ未確認")
    assert len(todo) == len(names), r.stdout
    for n in names:
        assert len([ln for ln in todo if n in ln]) == 1, f"{n} は 1 件でなければならない\n{r.stdout}"
    assert all("中" in ln for ln in todo)  # 重要度
    assert snapshot(repo) == before, "検査コマンドが管理データを書き換えた"


# FR-1024 AC-163 (zero entities -> 0 ToDo and says so)
def test_ac163_zero_entities_yields_zero_todo_and_says_so(tmp_path):
    repo = make_other(tmp_path / "o")
    r = run_entities(repo, "todo")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not _lines_with(r.stdout, "企業カタログ未確認")
    assert "0 件" in r.stdout or "0件" in r.stdout


# NFR-COMPAT-003 AC-168
def test_ac168_other_repo_runs_without_error_and_has_no_repo_specific_names(tmp_path):
    repo = make_other(tmp_path / "o")  # 別パス・0 件・カタログなし・任意欄なし・企業カタログ設定なし
    assert not (repo / CAT).exists() and not (repo / "docs").exists()
    for cmd in ("list", "check", "todo"):
        r = run_entities(repo, cmd)
        assert r.returncode == 0, f"{cmd}\n{r.stdout}\n{r.stderr}"
        assert "Traceback" not in r.stderr
        for foreign in ("run 清掃", "EABK run", "データ層", "正常完了 run"):
            assert foreign not in r.stdout, f"{cmd} がこのリポジトリ固有の名前を表示した: {foreign}"
    assert "エンティティなし" in run_entities(repo, "list").stdout

