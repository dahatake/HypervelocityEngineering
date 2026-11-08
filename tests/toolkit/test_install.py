import hashlib
import json
import re
import shutil
import sys

import pytest

from conftest import SOURCE, git, init_git, run


def install(target, *args):
    return run([sys.executable, str(SOURCE / "tools" / "install.py"), "--target", str(target), "--skip-verify", *args], target)


# FR-1085 AC-467 AC-473: a fresh install has no orchestration, hooks, repairing workflow or Studio tests
def test_fresh_install_layout(empty_repo):
    proc = install(empty_repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for rel in (".github/agents/rd-auditor.agent.md", ".github/skills/rd-audit/SKILL.md",
                ".github/skills/requirement-definition/SKILL.md", ".github/workflows/ebak-verify.yml",
                "scripts/next-id.py", "scripts/ledger.py",
                "scripts/verify.sh", "docs/requirements-definition.md", "tests/system/ledger.json", ".github/ebak-toolkit.json"):
        assert (empty_repo / rel).exists(), rel
    # EABK Lite: no orchestration, no role gates
    for rel in (".github/agents/conductor.agent.md", ".github/agents/implementer.agent.md", ".github/skills/build/SKILL.md",
                ".github/hooks", "scripts/hooks", ".github/ebak-prompt-prefix.md",
                ".github/workflows/ebak-data-layer.yml", "EABK-Studio/tests",
                "scripts/run-state.py", "scripts/integrate.py", "scripts/clean-work.py"):
        assert not (empty_repo / rel).exists(), rel
    cfg = json.loads((empty_repo / "scripts/ebak.config.json").read_text(encoding="utf-8"))
    assert cfg["checks"]["profile"] == "lite" and not {"gates", "limits", "credits", "worktree_share", "prompt_prefix"} & set(cfg)
    assert cfg["verify"]["commands"] == [] and "retention_days" not in cfg["work"]  # the target registers its own
    assert "run_history" not in cfg["management_files"]
    assert not (empty_repo / ".github/prompts").exists()
    assert "/work/" in (empty_repo / ".gitignore").read_text(encoding="utf-8")
    assert "merge=union" in (empty_repo / ".gitattributes").read_text(encoding="utf-8")
    agents = (empty_repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "ebak-abk:begin" in agents and "Build Kit Lite" in agents and "next-id.py" in agents and "conductor" not in agents
    assert not (empty_repo / ".github/workflows/toolkit-tests.yml").exists()
    assert not (empty_repo / "tests/toolkit/test_install.py").exists()


OLD_FILES = {".github/agents/conductor.agent.md": "conductor\n", "scripts/hooks/gate.py": "print('gate')\n",
             ".github/hooks/quality-gates.json": "{}\n", "tests/toolkit/test_clean_work.py": "def test_x():\n    pass\n"}


def plant_old_version(repo) -> None:
    """Files and settings an older version installed and this version does not ship (recorded in the manifest)."""
    install(repo)
    manifest_p = repo / ".github/ebak-toolkit.json"
    manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
    for rel, text in OLD_FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8", newline="")
        manifest["files"][rel] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    (repo / ".github/hooks/quality-gates.json").write_text("{\"利用者が直した\": true}\n", encoding="utf-8")
    manifest_p.write_text(json.dumps(manifest), encoding="utf-8")
    cfg_p = repo / "scripts/ebak.config.json"
    cfg = json.loads(cfg_p.read_text(encoding="utf-8"))
    cfg.update({"gates": {"enabled": True}, "prompt_prefix": {"enabled": True}})
    cfg_p.write_text(json.dumps(cfg), encoding="utf-8")
    gi = repo / ".gitignore"
    gi.write_text(gi.read_text(encoding="utf-8").replace("temporary files (logs, evidence, notes)", "temporary run files (kept 14 days)"),
                  encoding="utf-8")
    agents = repo / "AGENTS.md"
    agents.write_text(agents.read_text(encoding="utf-8") + "\n利用者の規則\n", encoding="utf-8")
    (repo / "docs/requirements-definition.md").write_text("# 利用者の要求定義書\n", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src/app.py").write_text("print('FR-001')\n", encoding="utf-8")


def tree(repo) -> dict:
    return {p.relative_to(repo).as_posix(): p.read_bytes() for p in repo.rglob("*")
            if p.is_file() and ".git" not in p.relative_to(repo).parts and p.name != "ebak-toolkit.json"}


# FR-1085 AC-468: --clean deletes everything any version installed (modified or not) and installs from scratch
def test_clean_install_replaces_an_old_version(empty_repo, tmp_path):
    plant_old_version(empty_repo)
    git(empty_repo, "add", "-A")
    git(empty_repo, "commit", "-q", "-m", "old version")
    proc = install(empty_repo, "--clean")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for rel in OLD_FILES:
        assert not (empty_repo / rel).exists(), rel
    for rel in (".github/hooks", "scripts/hooks"):
        assert not (empty_repo / rel).exists(), rel
    cfg = json.loads((empty_repo / "scripts/ebak.config.json").read_text(encoding="utf-8"))
    assert not {"gates", "prompt_prefix"} & set(cfg) and "CLEAN" in proc.stdout
    assert (empty_repo / "docs/requirements-definition.md").read_text(encoding="utf-8") == "# 利用者の要求定義書\n"
    assert (empty_repo / "src/app.py").exists()
    agents = (empty_repo / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.count("ebak-abk:begin") == 1 and "利用者の規則" in agents
    assert "kept 14 days" not in (empty_repo / ".gitignore").read_text(encoding="utf-8")
    # the toolkit files equal a fresh install of this version (the data layer and the user's files aside)
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    init_git(fresh)
    (fresh / "README.md").write_text("# test\n", encoding="utf-8")
    install(fresh)
    mine = {"docs/requirements-definition.md", "src/app.py", "AGENTS.md", "README.md"}
    got, want = tree(empty_repo), tree(fresh)
    assert set(got) - mine == set(want) - mine
    assert [r for r in set(want) - mine if got[r].replace(b"\r\n", b"\n") != want[r].replace(b"\r\n", b"\n")] == []
    # running it again changes nothing
    git(empty_repo, "add", "-A")
    git(empty_repo, "commit", "-q", "-m", "clean install")
    before = tree(empty_repo)
    assert install(empty_repo, "--clean").returncode == 0
    assert tree(empty_repo) == before


# FR-1085 AC-469: --clean is safe (committed git repos only, dry-run writes nothing); a normal update only points to it
def test_clean_safety_and_update_without_migration(empty_repo):
    plant_old_version(empty_repo)
    before = tree(empty_repo)
    proc = install(empty_repo, "--clean")
    assert proc.returncode == 1 and "commit" in proc.stderr and tree(empty_repo) == before
    git(empty_repo, "add", "-A")
    git(empty_repo, "commit", "-q", "-m", "old version")
    for opts in (("--clean", "--check"), ("--clean", "--uninstall")):
        assert install(empty_repo, *opts).returncode != 0
    proc = install(empty_repo, "--clean", "--dry-run")
    assert proc.returncode == 0 and re.search(r"^CLEAN\s+scripts/hooks/gate.py$", proc.stdout, re.M) and tree(empty_repo) == before
    # a normal update keeps the old files, warns with no WARN-* line, and keeps them in the manifest for --clean
    proc = install(empty_repo)
    assert proc.returncode == 0 and all((empty_repo / rel).exists() for rel in OLD_FILES)
    assert "--clean" in proc.stdout and "WARN-" not in proc.stdout and "PRUNE" not in proc.stdout
    manifest = json.loads((empty_repo / ".github/ebak-toolkit.json").read_text(encoding="utf-8"))
    assert set(OLD_FILES) <= set(manifest["files"])


def test_clean_refuses_non_git(tmp_path):
    proc = install(tmp_path, "--clean", "--allow-non-git")
    assert proc.returncode != 0 and "git" in proc.stderr


def test_reinstall_is_idempotent_and_check(empty_repo):
    install(empty_repo)
    assert install(empty_repo, "--check").returncode == 0
    proc = install(empty_repo)
    assert "changes=0" in proc.stdout


def test_local_modifications_are_kept(empty_repo):
    install(empty_repo)
    agent = empty_repo / ".github/agents/rd-auditor.agent.md"
    agent.write_text(agent.read_text(encoding="utf-8") + "\n# local note\n", encoding="utf-8")
    manifest = json.loads((empty_repo / ".github/ebak-toolkit.json").read_text(encoding="utf-8"))
    manifest["files"][".github/skills/requirement-definition/SKILL.md"] = "outdated"
    (empty_repo / ".github/ebak-toolkit.json").write_text(json.dumps(manifest), encoding="utf-8")
    proc = install(empty_repo)
    assert "SAME" in proc.stdout
    assert "local note" in agent.read_text(encoding="utf-8")
    src = (SOURCE / ".github/agents/rd-auditor.agent.md").read_text(encoding="utf-8")
    # simulate a toolkit update: the manifest hash is the old one, so the locally edited file is kept
    manifest = json.loads((empty_repo / ".github/ebak-toolkit.json").read_text(encoding="utf-8"))
    manifest["files"][".github/agents/rd-auditor.agent.md"] = "something-else"
    (empty_repo / ".github/ebak-toolkit.json").write_text(json.dumps(manifest), encoding="utf-8")
    proc = install(empty_repo)
    assert "KEEP-LOCAL" in proc.stdout and "local note" in agent.read_text(encoding="utf-8")
    proc = install(empty_repo, "--force")
    assert "OVERWRITE" in proc.stdout and agent.read_text(encoding="utf-8") == src
    assert list(agent.parent.glob("rd-auditor.agent.md.ebak-backup-*"))


def test_existing_files_and_config_are_merged(empty_repo):
    (empty_repo / "docs").mkdir()
    (empty_repo / "docs/requirements-definition.md").write_text("# 既存の要求定義書\n", encoding="utf-8")
    (empty_repo / "scripts").mkdir()
    (empty_repo / "scripts/ebak.config.json").write_text(json.dumps({"verify": {"commands": [{"name": "unit", "run": "npm test"}]}}), encoding="utf-8")
    (empty_repo / "AGENTS.md").write_text("# 既存\n\n独自の指示\n", encoding="utf-8")
    install(empty_repo)
    assert (empty_repo / "docs/requirements-definition.md").read_text(encoding="utf-8") == "# 既存の要求定義書\n"
    cfg = json.loads((empty_repo / "scripts/ebak.config.json").read_text(encoding="utf-8"))
    assert cfg["verify"]["commands"][0]["run"] == "npm test" and cfg["checks"]["profile"] == "lite"
    agents = (empty_repo / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.startswith("# 既存") and "独自の指示" in agents and agents.count("ebak-abk:begin") == 1
    install(empty_repo)
    assert (empty_repo / "AGENTS.md").read_text(encoding="utf-8").count("ebak-abk:begin") == 1


def test_uninstall(empty_repo):
    install(empty_repo)
    (empty_repo / "AGENTS.md").write_text((empty_repo / "AGENTS.md").read_text(encoding="utf-8") + "\n追記\n", encoding="utf-8")
    proc = install(empty_repo, "--uninstall")
    assert proc.returncode == 0
    assert not (empty_repo / ".github/agents/rd-auditor.agent.md").exists()
    assert not (empty_repo / "scripts/rdcheck.py").exists()
    assert (empty_repo / "docs/requirements-definition.md").exists()
    assert "ebak-abk" not in (empty_repo / "AGENTS.md").read_text(encoding="utf-8")
    # empty toolkit directories are removed; management data and config are kept
    for rel in (".github/agents", ".github/skills", ".github/hooks", ".github/workflows", "scripts/hooks", ".github/ebak-toolkit.json",
                ".github/copilot-instructions.md"):
        assert not (empty_repo / rel).exists(), rel
    assert (empty_repo / "scripts/ebak.config.json").exists() and (empty_repo / "tests/system/ledger.json").exists()
    assert "/work/" in (empty_repo / ".gitignore").read_text(encoding="utf-8")
    # running it again is harmless
    proc = install(empty_repo, "--uninstall")
    assert proc.returncode == 0 and "changes=0" in proc.stdout


def test_uninstall_keeps_modified_files_unless_forced(empty_repo):
    install(empty_repo)
    agent = empty_repo / ".github/agents/rd-auditor.agent.md"
    agent.write_text("利用者の変更\n", encoding="utf-8")
    proc = install(empty_repo, "--uninstall", "--dry-run")
    assert "REMOVE" in proc.stdout and (empty_repo / "scripts/rdcheck.py").exists()
    proc = install(empty_repo, "--uninstall")
    assert "KEEP-LOCAL" in proc.stdout and agent.exists()
    assert not (empty_repo / ".github/skills/requirement-definition/SKILL.md").exists()
    # the manifest is gone now: the fallback compares with the toolkit's own copies, --force removes the rest
    proc = install(empty_repo, "--uninstall")
    assert "KEEP-LOCAL" in proc.stdout and agent.exists()
    proc = install(empty_repo, "--uninstall", "--force")
    assert not agent.exists() and not (empty_repo / ".github/agents").exists()


def test_purge_removes_everything_the_toolkit_added(empty_repo):
    (empty_repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    install(empty_repo)
    (empty_repo / "work/runs/r1").mkdir(parents=True)
    (empty_repo / "work/runs/r1/log.txt").write_text("log\n", encoding="utf-8")
    (empty_repo / "docs/manual-tests.md").write_text("# 手動テスト\n", encoding="utf-8")
    (empty_repo / "docs/notes.md").write_text("利用者の文書\n", encoding="utf-8")
    (empty_repo / "scripts/build.sh").write_text("echo build\n", encoding="utf-8")
    (empty_repo / "tests/system/test_flow.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    backup = empty_repo / ".github/agents/rd-auditor.agent.md.ebak-backup-20260101000000"
    backup.write_text("old\n", encoding="utf-8")
    (empty_repo / "scripts/__pycache__").mkdir()
    (empty_repo / "scripts/__pycache__/ebaklib.cpython-312.pyc").write_bytes(b"\0")
    proc = install(empty_repo, "--purge", "--dry-run")
    assert proc.returncode == 0 and (empty_repo / "docs/catalog.md").exists() and backup.exists()
    proc = install(empty_repo, "--purge")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for rel in ("docs/requirements-definition.md", "docs/catalog.md", "docs/id-registry.md",
                "docs/manual-tests.md", "tests/system/ledger.json", "scripts/ebak.config.json", "work", ".github",
                ".gitattributes", "AGENTS.md", "scripts/verify.py", "scripts/__pycache__"):
        assert not (empty_repo / rel).exists(), rel
    assert (empty_repo / ".gitignore").read_text(encoding="utf-8") == "node_modules/\n"
    for rel in ("docs/notes.md", "scripts/build.sh", "tests/system/test_flow.py", "README.md"):
        assert (empty_repo / rel).exists(), rel
    # the repository can be installed again afterwards
    assert install(empty_repo).returncode == 0 and (empty_repo / ".github/ebak-toolkit.json").exists()


# FR-1087 AC-478: the wrappers run tools/uninstall.py with its catalog (local clone or the two downloaded files)
def test_uninstall_wrappers_pass_uninstall():
    ps1 = (SOURCE / "tools/uninstall.ps1").read_text(encoding="utf-8")
    for s in ("uninstall.py", "uninstall-catalog.json", "[switch]$Purge", "[switch]$Runs", "'--runs'", "'--purge'", "'--dry-run'"):
        assert s in ps1, s
    sh = (SOURCE / "tools/uninstall.sh").read_bytes()
    assert b"\r\n" not in sh
    for s in (b"uninstall.py", b"uninstall-catalog.json", b'"$PY" "$DIR/uninstall.py" "$@"'):
        assert s in sh, s
    ps = (SOURCE / "tools/install.ps1").read_text(encoding="utf-8")
    assert "[switch]$Purge" in ps and "[switch]$Clean" in ps and "'--clean'" in ps


@pytest.mark.skipif(not shutil.which("powershell") and not shutil.which("pwsh"), reason="PowerShell がありません")
def test_uninstall_ps1_runs_local_uninstaller(empty_repo):
    assert install(empty_repo).returncode == 0
    shell = shutil.which("pwsh") or shutil.which("powershell")
    proc = run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SOURCE / "tools/uninstall.ps1"),
                "-Target", str(empty_repo), "-Purge"], empty_repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "installer versions" in proc.stdout and not (empty_repo / ".github/ebak-toolkit.json").exists()


def test_refuses_non_git_and_self(tmp_path):
    proc = install(tmp_path)
    assert proc.returncode != 0 and "git" in proc.stderr
    proc = run([sys.executable, str(SOURCE / "tools" / "install.py"), "--target", str(SOURCE)], SOURCE)
    assert proc.returncode != 0
