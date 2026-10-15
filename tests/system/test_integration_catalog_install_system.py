"""System test for FR-1037 AC-214 (外部連携カタログの雛形の配布).

Expected values come only from AC-214 in docs/requirements-definition.md.  The installed repository is the
disposable `installed_repo` fixture (conftest.py).  PROVISIONAL: the template path is `docs/integrations.md`
(FR-1035 [ASSUMPTION]); the "index table" is checked by the column names FR-1035 lists
(ID・名前・連携先・方向・状態・関連する要求).  A managed check/checklist file is recognised by a path that
contains "integration" (case-insensitive) in .github/ebak-toolkit.json "files"; if the implementation names it
otherwise, return it as a CONFLICT instead of changing this oracle.
"""
import json
import re
import subprocess
import sys

from conftest import SOURCE, run

CATALOG = "docs/integrations.md"
INDEX_COLUMNS = ("ID", "名前", "連携先", "方向", "状態", "関連する要求")


def _install(repo, *extra, check=True):
    return run([sys.executable, SOURCE / "tools" / "install.py", "--target", repo, "--skip-verify", *extra], repo, check=check)


# FR-1037 AC-214
def test_ac214_install_creates_template_with_format_note_and_empty_index_table(installed_repo):
    text = (installed_repo / CATALOG).read_text(encoding="utf-8")
    header = [ln for ln in text.splitlines() if ln.lstrip().startswith("|") and all(c in ln for c in INDEX_COLUMNS)]
    assert header, "空の索引表（ID・名前・連携先・方向・状態・関連する要求）がない"
    assert not re.search(r"^####\s+INT-\d+", text, re.M), "雛形に実在しない連携項目が入っている"
    assert re.search(r"INT-\d{3}", text), "書式の説明（#### INT-001 <名前> の例）がない"


# FR-1037 AC-214 (abnormal: 既存の導入先のカタログは上書きされず、再実行でも変わらない)
def test_ac214_existing_catalog_is_never_overwritten_and_rerun_is_idempotent(installed_repo):
    path = installed_repo / CATALOG
    mine = "# 外部連携カタログ\n\n#### INT-001 受注 API\n- 連携先: 取引先 A\n"
    path.write_text(mine, encoding="utf-8")
    _install(installed_repo)
    _install(installed_repo, "--force")
    assert path.read_text(encoding="utf-8") == mine
    run(["git", "add", "-A"], installed_repo)
    run(["git", "commit", "-q", "-m", "mine"], installed_repo)
    _install(installed_repo)
    assert run(["git", "status", "--porcelain"], installed_repo).stdout.strip() == ""


# FR-1037 AC-214 (abnormal: 雛形を消した導入先では、再実行で作られる)
def test_ac214_missing_template_is_created_on_update_only_when_absent(installed_repo):
    (installed_repo / CATALOG).unlink()
    _install(installed_repo)
    assert (installed_repo / CATALOG).is_file()


# FR-1037 AC-214
def test_ac214_catalog_related_managed_files_follow_the_normal_update_path_and_no_ci_is_unchanged(installed_repo):
    manifest_path = installed_repo / ".github" / "ebak-toolkit.json"
    files = json.loads(manifest_path.read_text(encoding="utf-8"))["files"]
    related = [f for f in files if "integration" in f.lower()]
    assert related, "外部連携の検査・チェックリストの文書が配布物（ebak-toolkit.json の files）にない"
    target = installed_repo / related[0]
    target.unlink()
    _install(installed_repo)
    assert target.is_file(), "配布物が通常の更新（再実行）で復元されない"
    # --no-ci: workflow を入れない挙動は変わらない
    fresh = installed_repo.parent / "no-ci-target"
    fresh.mkdir()
    run(["git", "init", "-q", "-b", "main"], fresh)
    _install(fresh, "--no-ci", "--allow-non-git")
    assert not (fresh / ".github" / "workflows" / "ebak-verify.yml").exists()
    assert (fresh / CATALOG).is_file()
