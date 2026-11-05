"""System test for FR-1082 AC-459 (toolkit 更新後も、登録した検査の拡張が登録を書き直さずに呼ばれる).

Expected values come only from AC-459 / AC-460 (the "1 行 = 名前・呼ばれた対象・結果" line) in
docs/requirements-definition.md.  The installed repository is the disposable `installed_repo` fixture.
PROVISIONAL (the requirement leaves these open; if the implementation differs, return a CONFLICT, do not
change the oracle): `extensions.checks` entries use the keys module / function / target ("rdcheck"|"rdfix"|
"both"); an extension is a callable accepting any arguments and returning a list of findings (empty = pass);
the line verify prints contains the extension's function name.  The extension proves it was called by
appending to a marker file, so the check does not depend on the output format.
"""
import json
import sys

from conftest import SOURCE, run

MARK_CFG = "calls-config.txt"
MARK_EXT = "calls-ext.txt"

CFG_MODULE = '''def project_check_cfg(*args, **kwargs):
    with open("calls-config.txt", "a", encoding="utf-8") as f:
        f.write("called\\n")
    return []
'''

EXT_MODULE = '''def project_check_ext(*args, **kwargs):
    with open("calls-ext.txt", "a", encoding="utf-8") as f:
        f.write("called\\n")
    return []
'''


def _install(repo, *extra):
    return run([sys.executable, SOURCE / "tools" / "install.py", "--target", repo, "--skip-verify", *extra], repo)


def _verify(repo):
    return run([sys.executable, "scripts/verify.py", "--docs-only"], repo, check=False)


def _calls(repo, name):
    p = repo / name
    return p.read_text(encoding="utf-8").count("called") if p.is_file() else 0


def _ext_lines(result, *names):
    return sorted(ln.strip() for ln in (result.stdout + result.stderr).splitlines() if any(n in ln for n in names))


# FR-1082 AC-459 AC-460
def test_ac459_registered_extensions_survive_install_force_and_return_the_same_result(installed_repo):
    repo = installed_repo
    cfg_path = repo / "scripts" / "ebak.config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg.setdefault("extensions", {})["checks"] = [
        {"module": "project_checks_cfg", "function": "project_check_cfg", "target": "rdcheck"}
    ]
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (repo / "scripts" / "project_checks_cfg.py").write_text(CFG_MODULE, encoding="utf-8")
    (repo / "scripts" / "ext").mkdir(exist_ok=True)
    (repo / "scripts" / "ext" / "project_checks_ext.py").write_text(EXT_MODULE, encoding="utf-8")

    before = _verify(repo)
    assert _calls(repo, MARK_CFG) >= 1 and _calls(repo, MARK_EXT) >= 1, "更新前に拡張が呼ばれていない\n" + before.stdout
    before_lines = _ext_lines(before, "project_check_cfg", "project_check_ext")
    assert len(before_lines) == 2, before_lines
    cfg_before = cfg_path.read_text(encoding="utf-8")
    ext_before = (repo / "scripts" / "ext" / "project_checks_ext.py").read_text(encoding="utf-8")

    # 更新: scripts/*.py を toolkit の版で上書きする（通常と --force）
    for extra in ((), ("--force",)):
        for name in (MARK_CFG, MARK_EXT):
            (repo / name).unlink(missing_ok=True)
        _install(repo, *extra)
        after = _verify(repo)
        assert _calls(repo, MARK_CFG) == 1, f"{extra}: config 登録の拡張が更新後に呼ばれない（0 回、または複数回）\n" + after.stdout
        assert _calls(repo, MARK_EXT) == 1, f"{extra}: scripts/ext の拡張が更新後に呼ばれない（0 回、または複数回）\n" + after.stdout
        assert after.returncode == before.returncode, (before.returncode, after.returncode)
        assert _ext_lines(after, "project_check_cfg", "project_check_ext") == before_lines
        # 登録は書き直されていない（利用側の値が残る）
        assert json.loads(cfg_path.read_text(encoding="utf-8"))["extensions"]["checks"] == cfg["extensions"]["checks"]
        assert (repo / "scripts" / "ext" / "project_checks_ext.py").read_text(encoding="utf-8") == ext_before
    assert json.loads(cfg_path.read_text(encoding="utf-8"))["extensions"]["checks"][0]["function"] == "project_check_cfg"
    assert cfg_before  # 設定ファイルは空でない


# FR-1082 AC-459 (abnormal: 更新後に拡張が壊れた・消えたときは、握りつぶさず拡張名つきで不合格にする)
def test_ac459_abnormal_broken_extension_after_update_fails_with_its_name(installed_repo):
    repo = installed_repo
    (repo / "scripts" / "ext").mkdir(exist_ok=True)
    broken = repo / "scripts" / "ext" / "project_broken_ext.py"
    broken.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    _install(repo, "--force")
    result = _verify(repo)
    out = result.stdout + result.stderr
    assert result.returncode != 0, "読み込めない拡張が不合格にならない\n" + out
    assert "project_broken_ext" in out, "不合格に拡張名がない\n" + out
