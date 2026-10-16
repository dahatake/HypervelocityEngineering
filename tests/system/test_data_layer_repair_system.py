"""System Tests for the data-layer check / repair entry points (FR-1045, FR-1046).

Expected values come from the acceptance criteria only (AC-237, AC-238, AC-240, AC-241).
Every test works on a disposable Git repository under tmp_path (see datalayer_repo.py);
the source checkout is never written.

Interface (requirements definition FR-1045 / FR-1046 [ASSUMPTION]):
  check only : python scripts/rdfix.py --full
  apply      : python scripts/rdfix.py --full --apply
  exit codes : 0 = pass / repaired, 1 = manual left / plan exists / not converged, 2 = not run / cancelled
  installer  : tools/install.py  (default: check + repair after install), --no-repair, --skip-verify

Fault injection (AC-241, cancellation by NFR-REL-002) is done from outside the process:
the target file is made unwritable (Windows: read-only attribute; POSIX: read-only file and directory).
No hook inside the implementation is assumed.
"""
from __future__ import annotations

import os
import re

import pytest

import datalayer_repo as d


def out(r) -> str:
    """stdout + stderr; path separators normalised (AC-243 allows them to differ by OS)."""
    return ((r.stdout or "") + "\n" + (r.stderr or "")).replace("\\", "/")


@pytest.fixture
def clean(tmp_path):
    return d.make_clean_installed(tmp_path / "EABK data layer repair with spaces")


# ============================================================================ FR-1046 AC-240 (check only)

# FR-1046 AC-240: consistent data layer -> exit 0, nothing written
def test_ac240_check_clean_exits_0_and_writes_nothing(clean):
    before = d.snapshot(clean)
    r = d.py(clean, *d.CHECK)
    assert d.no_traceback(r), out(r)
    assert r.returncode == 0, f"不整合のないデータ層で exit {r.returncode}\n{out(r)}"
    assert not d.fix_lines(out(r)) and not d.manual_lines(out(r)), out(r)
    assert d.snapshot(clean) == before, "確認だけのコマンドがデータ層のファイル（内容または更新時刻）を変えた"


# FR-1046 AC-240: inconsistent (automatic + manual) -> exit 1, FIX and MANUAL lines, nothing written
def test_ac240_check_inconsistent_exits_1_shows_fix_and_manual_and_writes_nothing(clean):
    d.plant_automatic(clean)
    d.plant_manual(clean)
    d.commit(clean, "plant")
    before = d.snapshot(clean)
    r = d.py(clean, *d.CHECK)
    assert d.no_traceback(r), out(r)
    assert r.returncode == 1, f"不整合のあるデータ層で exit {r.returncode}\n{out(r)}"
    fixes, manual = d.fix_lines(out(r)), d.manual_lines(out(r))
    for rel in (d.CATALOG, d.REGISTRY, d.LEDGER):
        assert any(rel in l for l in fixes), f"{rel} の自動修復の計画（FIX の行）がない\n{out(r)}"
    assert any(d.HISTORY in l for l in manual), f"手動対応（MANUAL の行）がない\n{out(r)}"
    assert d.snapshot(clean) == before, "確認だけのコマンドがデータ層のファイル（内容または更新時刻）を変えた"


# FR-1046 AC-240 (abnormal: only automatic fixes pending is still a failing check, and still no write)
def test_ac240_check_with_only_automatic_fixes_pending_exits_1_without_writing(clean):
    d.plant_automatic(clean)
    d.commit(clean, "plant")
    before = d.snapshot(clean)
    r = d.py(clean, *d.CHECK)
    assert d.no_traceback(r), out(r)
    assert r.returncode == 1, f"自動修復の計画があるのに exit {r.returncode}\n{out(r)}"
    assert d.fix_lines(out(r)), out(r)
    assert not d.manual_lines(out(r)), f"手動対応のないデータ層で MANUAL の行が出た\n{out(r)}"
    assert d.snapshot(clean) == before
    assert not any(d.automatic_repaired(clean).values()), "確認だけのコマンドが修復を書き込んだ"


# ============================================================================ FR-1046 AC-241 (apply)

# FR-1046 AC-241: only automatic inconsistencies -> repaired, re-check passes, exit 0 (canary)
def test_ac241_apply_automatic_only_repairs_and_exits_0(clean):
    d.plant_automatic(clean)
    d.commit(clean, "plant")
    protected = d.bytes_of(clean, d.PROTECTED)
    r = d.py(clean, *d.APPLY)
    assert d.no_traceback(r), out(r)
    assert r.returncode == 0, f"自動修復だけで直るのに exit {r.returncode}\n{out(r)}"
    assert all(d.automatic_repaired(clean).values()), f"修復されていない: {d.automatic_repaired(clean)}\n{out(r)}"
    v = d.py(clean, "scripts/verify.py", "--docs-only")
    assert v.returncode == 0, f"修復後の再検査が不合格\n{v.stdout}"
    assert d.bytes_of(clean, d.PROTECTED) == protected, "要求定義書または外部連携カタログが変わった"


# FR-1046 AC-241: manual items left -> automatic part applied, rest shown, exit 1
def test_ac241_apply_with_manual_left_applies_automatic_part_and_exits_1(clean):
    d.plant_automatic(clean)
    d.plant_manual(clean)
    d.commit(clean, "plant")
    protected = d.bytes_of(clean, d.PROTECTED)
    history = (clean / d.HISTORY).read_bytes()
    r = d.py(clean, *d.APPLY)
    assert d.no_traceback(r), out(r)
    assert r.returncode == 1, f"手動対応が残るのに exit {r.returncode}\n{out(r)}"
    assert all(d.automatic_repaired(clean).values()), f"自動修復できる分が適用されていない: {d.automatic_repaired(clean)}\n{out(r)}"
    assert any(d.HISTORY in l for l in d.manual_lines(out(r))), f"残った手動対応が表示されない\n{out(r)}"
    assert (clean / d.HISTORY).read_bytes() == history, "手動対応のファイルが書き換えられた"
    assert d.bytes_of(clean, d.PROTECTED) == protected, "要求定義書または外部連携カタログが変わった"


# FR-1046 AC-241 (abnormal: refusal on a worker branch work/<run-id>/<item>) -> exit 2, nothing written
def test_ac241_apply_on_worker_branch_is_refused_with_exit_2(clean):
    d.run(["git", "checkout", "-q", "-b", "work/202610160833/item-1"], clean, check=True)
    d.plant_automatic(clean)
    d.commit(clean, "plant")
    before = d.snapshot(clean)
    r = d.py(clean, *d.APPLY)
    assert d.no_traceback(r), out(r)
    assert r.returncode == 2, f"作業役のブランチでの適用が exit {r.returncode}\n{out(r)}"
    assert out(r).strip(), "拒否の理由が表示されない"
    assert {k: v[0] for k, v in d.snapshot(clean).items()} == {k: v[0] for k, v in before.items()}, "拒否したのに書き込んだ"
    # control: the same state on a non-worker branch is applied (the refusal is caused by the branch only)
    d.run(["git", "branch", "-m", "run/202610160833"], clean, check=True)
    r2 = d.py(clean, *d.APPLY)
    assert r2.returncode == 0 and all(d.automatic_repaired(clean).values()), f"統合ブランチでは適用されるはず\n{out(r2)}"


# FR-1046 AC-241 (abnormal: write failure -> NFR-REL-002 cancellation) -> exit 2, everything as before
def test_ac241_apply_cancelled_on_write_failure_exits_2_and_restores(clean):
    if os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root ではファイルの権限で書き込みの失敗を注入できない")
    d.plant_automatic(clean)
    d.commit(clean, "plant")
    before = {k: v[0] for k, v in d.snapshot(clean).items()}
    undo = d.make_unwritable(clean / d.CATALOG)
    try:
        r = d.py(clean, *d.APPLY)
    finally:
        undo()
    assert d.no_traceback(r), out(r)
    assert r.returncode == 2, f"書き込みに失敗したのに exit {r.returncode}\n{out(r)}"
    assert out(r).strip(), "取り消しの理由が表示されない"
    after = {k: v[0] for k, v in d.snapshot(clean).items()}
    assert set(after) == set(before), f"ファイルが増減した（一時ファイルの残り等）: {set(after) ^ set(before)}"
    changed = [k for k in before if after[k] != before[k]]
    assert not changed, f"取り消し後も修復前と一致しない: {changed}"
    # control: once the file is writable again the same apply succeeds (the cancellation was caused by the fault)
    r2 = d.py(clean, *d.APPLY)
    assert r2.returncode == 0 and all(d.automatic_repaired(clean).values()), f"故障を除いた後の適用が成功しない\n{out(r2)}"


# FR-1046 AC-241 (abnormal: protected files byte-identical on every outcome, incl. a clean apply)
def test_ac241_apply_on_clean_data_layer_exits_0_and_protected_files_unchanged(clean):
    protected = d.bytes_of(clean, d.PROTECTED)
    r = d.py(clean, *d.APPLY)
    assert d.no_traceback(r), out(r)
    assert r.returncode == 0, out(r)
    assert d.bytes_of(clean, d.PROTECTED) == protected


# ============================================================================ FR-1045 AC-237 (installer repairs)

def _assert_install_report(r, root, protected, history):
    text = out(r)
    assert d.no_traceback(r), text
    assert r.returncode == 0, f"導入が失敗した\n{text}"
    assert all(d.automatic_repaired(root).values()), f"導入の後に修復されていない: {d.automatic_repaired(root)}\n{text}"
    items = [l for l in text.splitlines() if re.search(r"CHK-\d+", l)]
    for rel in (d.CATALOG, d.REGISTRY, d.LEDGER):
        assert any(rel in l for l in items), f"修復した項目 {rel}（検査項目 ID つき）が表示されない\n{text}"
    man = [l for l in text.splitlines() if d.HISTORY in l and re.search(r"CHK-\d+", l)]
    assert man, f"残った手動対応（検査項目 ID・位置）が表示されない\n{text}"
    assert any(re.search(re.escape(d.HISTORY) + r":\d+", l) for l in man), f"手動対応の位置（行）がない\n{text}"
    assert any(any(role in l for role in d.ROLES) for l in man), f"手動対応の担当の役割がない\n{text}"
    assert re.search(r"不合格|FAIL|fail|NG", text), f"再検査の合否が表示されない\n{text}"
    assert (root / d.HISTORY).read_bytes() == history, "手動対応のファイルが書き換えられた"
    assert d.bytes_of(root, d.PROTECTED) == protected, "要求定義書または外部連携カタログが変わった"


# FR-1045 AC-237: new install into a repository that already has an inconsistent data layer
def test_ac237_new_install_repairs_and_reports(tmp_path):
    root = d.make_clean_uninstalled(tmp_path / "new install target", tmp_path / "scratch")
    d.plant_automatic(root)
    d.plant_manual(root)
    d.commit(root, "plant")
    protected = d.bytes_of(root, d.PROTECTED)
    assert set(protected) == set(d.PROTECTED)
    history = (root / d.HISTORY).read_bytes()
    r = d.install(root, check=False)
    _assert_install_report(r, root, protected, history)


# FR-1045 AC-237: update (re-run of the installer) on an installed repository
def test_ac237_update_install_repairs_and_reports(clean):
    d.plant_automatic(clean)
    d.plant_manual(clean)
    d.commit(clean, "plant")
    protected = d.bytes_of(clean, d.PROTECTED)
    history = (clean / d.HISTORY).read_bytes()
    r = d.install(clean, check=False)
    _assert_install_report(r, clean, protected, history)


# FR-1045 AC-237: only automatic inconsistencies -> repaired and the re-check passes
def test_ac237_update_install_automatic_only_passes_recheck(clean):
    d.plant_automatic(clean)
    d.commit(clean, "plant")
    protected = d.bytes_of(clean, d.PROTECTED)
    r = d.install(clean, check=False)
    text = out(r)
    assert d.no_traceback(r) and r.returncode == 0, text
    assert all(d.automatic_repaired(clean).values()), f"{d.automatic_repaired(clean)}\n{text}"
    assert re.search(r"合格|PASS|pass|OK", text), f"再検査の合否が表示されない\n{text}"
    assert not d.manual_lines(out(r)), f"手動対応のないデータ層で MANUAL の行が出た\n{text}"
    v = d.py(clean, "scripts/verify.py", "--docs-only")
    assert v.returncode == 0, f"導入の後のデータ層が再検査に合格しない\n{v.stdout}"
    assert d.bytes_of(clean, d.PROTECTED) == protected


# ============================================================================ FR-1045 AC-238 (installer options)

@pytest.fixture
def planted(clean):
    d.plant_automatic(clean)
    d.plant_manual(clean)
    d.commit(clean, "plant")
    return clean


def _bytes(root):
    return {k: v[0] for k, v in d.snapshot(root).items()}


# FR-1045 AC-238: --no-repair shows the check result and the repair plan, writes nothing
def test_ac238_no_repair_shows_plan_and_writes_nothing(planted):
    before = _bytes(planted)
    r = d.install(planted, "--no-repair", check=False)
    text = out(r)
    assert d.no_traceback(r) and r.returncode == 0, text
    fixes = [l for l in text.splitlines() if re.match(r"^\s*FIX\b", l)]
    for rel in (d.CATALOG, d.REGISTRY, d.LEDGER):
        assert any(rel in l for l in fixes), f"修復の計画に {rel} がない\n{text}"
    assert any(d.HISTORY in l for l in text.splitlines() if re.match(r"^\s*MANUAL\b", l)), f"検査の結果（手動対応）がない\n{text}"
    assert _bytes(planted) == before, "--no-repair でデータ層のファイルが変わった"


# FR-1045 AC-238: --skip-verify neither checks nor repairs
def test_ac238_skip_verify_neither_checks_nor_repairs(planted):
    before = _bytes(planted)
    r = d.install(planted, "--skip-verify", check=False)
    text = out(r)
    assert d.no_traceback(r) and r.returncode == 0, text
    assert not re.search(r"^\s*(FIX|MANUAL)\b|CHK-\d+", text, re.M), f"--skip-verify で検査または修復が行われた\n{text}"
    assert _bytes(planted) == before, "--skip-verify でデータ層のファイルが変わった"


# FR-1045 AC-238 (abnormal: modes that must never repair)
@pytest.mark.parametrize("mode", ["--dry-run", "--check", "--uninstall", "--purge"])
def test_ac238_non_install_modes_do_not_repair(planted, mode):
    before = _bytes(planted)
    r = d.install(planted, mode, check=False)
    text = out(r)
    assert d.no_traceback(r), text
    assert r.returncode in (0, 1), f"{mode} が異常終了した\n{text}"
    assert not re.search(r"^\s*FIX\b", text, re.M), f"{mode} で修復が行われた\n{text}"
    after = _bytes(planted)
    if mode != "--purge":
        assert set(after) == set(before), f"{mode} でデータ層のファイルが増減した"
    changed = [k for k in after if k in before and after[k] != before[k]]
    assert not changed, f"{mode} でデータ層のファイルが修復された: {changed}"
    assert not (set(after) - set(before)), f"{mode} でデータ層のファイルが作られた: {set(after) - set(before)}"
