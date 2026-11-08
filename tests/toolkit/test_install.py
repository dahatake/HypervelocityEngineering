import hashlib
import json
import re
import sys

from conftest import SOURCE, run


def install(target, *args):
    return run([sys.executable, str(SOURCE / "tools" / "install.py"), "--target", str(target), "--skip-verify", *args], target)


def test_fresh_install_layout(empty_repo):
    proc = install(empty_repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for rel in (".github/agents/rd-auditor.agent.md", ".github/skills/rd-audit/SKILL.md",
                ".github/skills/requirement-definition/SKILL.md", ".github/workflows/ebak-verify.yml",
                ".github/workflows/ebak-data-layer.yml", "scripts/next-id.py", "scripts/ledger.py",
                "scripts/verify.sh", "docs/requirements-definition.md", "tests/system/ledger.json", ".github/ebak-toolkit.json"):
        assert (empty_repo / rel).exists(), rel
    # EABK Lite: no orchestration, no role gates
    for rel in (".github/agents/conductor.agent.md", ".github/agents/implementer.agent.md", ".github/skills/build/SKILL.md",
                ".github/hooks", "scripts/hooks", ".github/ebak-prompt-prefix.md",
                "scripts/run-state.py", "scripts/integrate.py", "scripts/clean-work.py"):
        assert not (empty_repo / rel).exists(), rel
    cfg = json.loads((empty_repo / "scripts/ebak.config.json").read_text(encoding="utf-8"))
    assert cfg["checks"]["profile"] == "lite" and not {"gates", "limits", "credits", "worktree_share", "prompt_prefix"} & set(cfg)
    assert not (empty_repo / ".github/prompts").exists()
    assert "/work/" in (empty_repo / ".gitignore").read_text(encoding="utf-8")
    assert "merge=union" in (empty_repo / ".gitattributes").read_text(encoding="utf-8")
    agents = (empty_repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "ebak-abk:begin" in agents and "Build Kit Lite" in agents and "next-id.py" in agents and "conductor" not in agents
    assert not (empty_repo / ".github/workflows/toolkit-tests.yml").exists()
    assert not (empty_repo / "tests/toolkit/test_install.py").exists()


def test_upgrade_from_orchestration_version_removes_it(empty_repo):
    """0.5.x -> Lite: unmodified orchestration files and config keys go away, modified ones and the data stay."""
    install(empty_repo)
    manifest_p = empty_repo / ".github/ebak-toolkit.json"
    manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
    old = {".github/agents/conductor.agent.md": "conductor\n", "scripts/run-state.py": "print('run')\n",
           ".github/hooks/quality-gates.json": "{}\n", "tests/toolkit/test_clean_work.py": "def test_x():\n    pass\n"}
    for rel, text in old.items():
        (empty_repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (empty_repo / rel).write_text(text, encoding="utf-8", newline="")
        manifest["files"][rel] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    for rel in (".github/agents/implementer.agent.md", ".github/hooks/prompt-prefix.json"):
        (empty_repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (empty_repo / rel).write_text("利用者が直した\n", encoding="utf-8")
        manifest["files"][rel] = "hash-of-the-shipped-copy"
    manifest_p.write_text(json.dumps(manifest), encoding="utf-8")
    cfg_p = empty_repo / "scripts/ebak.config.json"
    cfg = json.loads(cfg_p.read_text(encoding="utf-8"))
    cfg.update({"gates": {"enabled": True}, "limits": {"max_hours_cap": 3}, "credits": {}, "worktree_share": {},
                "prompt_prefix": {"enabled": True}})
    cfg["verify"]["commands"] = [{"name": "toolkit-unit", "run": "python -m pytest -q tests/toolkit/test_clean_work.py"},
                                 {"name": "unit", "run": "npm test"}]
    cfg_p.write_text(json.dumps(cfg), encoding="utf-8")
    proc = install(empty_repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for rel in old:
        assert not (empty_repo / rel).exists(), rel
    assert (empty_repo / ".github/agents/implementer.agent.md").exists() and "KEEP-LOCAL" in proc.stdout
    # a kept old hook would call the removed gate.py and make Copilot deny every tool: the installer says so
    assert (empty_repo / ".github/hooks/prompt-prefix.json").exists() and "WARN-HOOK  .github/hooks/prompt-prefix.json" in proc.stdout
    cfg = json.loads(cfg_p.read_text(encoding="utf-8"))
    assert not {"gates", "limits", "credits", "worktree_share", "prompt_prefix"} & set(cfg) and "PRUNE" in proc.stdout
    assert [c["run"] for c in cfg["verify"]["commands"]] == ["npm test"]
    assert (empty_repo / "docs/requirements-definition.md").exists() and (empty_repo / "tests/system/ledger.json").exists()


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
    for rel in ("docs/requirements-definition.md", "docs/catalog.md", "docs/id-registry.md", "docs/run-history.md",
                "docs/manual-tests.md", "tests/system/ledger.json", "scripts/ebak.config.json", "work", ".github",
                ".gitattributes", "AGENTS.md", "scripts/verify.py", "scripts/__pycache__"):
        assert not (empty_repo / rel).exists(), rel
    assert (empty_repo / ".gitignore").read_text(encoding="utf-8") == "node_modules/\n"
    for rel in ("docs/notes.md", "scripts/build.sh", "tests/system/test_flow.py", "README.md"):
        assert (empty_repo / rel).exists(), rel
    # the repository can be installed again afterwards
    assert install(empty_repo).returncode == 0 and (empty_repo / ".github/ebak-toolkit.json").exists()


def test_uninstall_wrappers_pass_uninstall():
    ps1 = (SOURCE / "tools/uninstall.ps1").read_text(encoding="utf-8")
    assert "Uninstall = $true" in ps1 and "Purge" in ps1 and "install.ps1" in ps1
    sh = (SOURCE / "tools/uninstall.sh").read_text(encoding="utf-8")
    assert "install.sh\" --uninstall \"$@\"" in sh and "bash -s -- --uninstall \"$@\"" in sh
    assert "[switch]$Purge" in (SOURCE / "tools/install.ps1").read_text(encoding="utf-8")


def test_refuses_non_git_and_self(tmp_path):
    proc = install(tmp_path)
    assert proc.returncode != 0 and "git" in proc.stderr
    proc = run([sys.executable, str(SOURCE / "tools" / "install.py"), "--target", str(SOURCE)], SOURCE)
    assert proc.returncode != 0
