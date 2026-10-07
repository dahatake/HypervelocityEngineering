import hashlib
import json
import sys

from conftest import SOURCE, run


def install(target, *args):
    return run([sys.executable, str(SOURCE / "tools" / "install.py"), "--target", str(target), "--skip-verify", *args], target)


def test_fresh_install_layout(empty_repo):
    proc = install(empty_repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for rel in (".github/agents/conductor.agent.md", ".github/skills/rd-audit/SKILL.md", ".github/hooks/quality-gates.json",
                ".github/skills/build/SKILL.md", ".github/workflows/hve-verify.yml", "scripts/hooks/gate.py",
                "scripts/verify.sh", "docs/requirements-definition.md", "tests/system/ledger.json", ".github/hve-toolkit.json"):
        assert (empty_repo / rel).exists(), rel
    assert not (empty_repo / ".github/prompts").exists()
    skill = (empty_repo / ".github/skills/build/SKILL.md").read_text(encoding="utf-8")
    assert "name: build" in skill and "disable-model-invocation: true" in skill
    assert "/build template" in skill and "max_hours: 24" in skill
    assert "/work/" in (empty_repo / ".gitignore").read_text(encoding="utf-8")
    assert "merge=union" in (empty_repo / ".gitattributes").read_text(encoding="utf-8")
    assert "hve-abk:begin" in (empty_repo / "AGENTS.md").read_text(encoding="utf-8")
    assert not (empty_repo / ".github/workflows/toolkit-tests.yml").exists()
    assert not (empty_repo / "tests/toolkit").exists()


def test_reinstall_is_idempotent_and_check(empty_repo):
    install(empty_repo)
    assert install(empty_repo, "--check").returncode == 0
    proc = install(empty_repo)
    assert "changes=0" in proc.stdout


def test_local_modifications_are_kept(empty_repo):
    install(empty_repo)
    agent = empty_repo / ".github/agents/conductor.agent.md"
    agent.write_text(agent.read_text(encoding="utf-8") + "\n# local note\n", encoding="utf-8")
    manifest = json.loads((empty_repo / ".github/hve-toolkit.json").read_text(encoding="utf-8"))
    manifest["files"][".github/agents/reviewer.agent.md"] = "outdated"
    (empty_repo / ".github/hve-toolkit.json").write_text(json.dumps(manifest), encoding="utf-8")
    proc = install(empty_repo)
    assert "SAME" in proc.stdout
    assert "local note" in agent.read_text(encoding="utf-8")
    src = (SOURCE / ".github/agents/conductor.agent.md").read_text(encoding="utf-8")
    # simulate a toolkit update: the manifest hash is the old one, so the locally edited file is kept
    manifest = json.loads((empty_repo / ".github/hve-toolkit.json").read_text(encoding="utf-8"))
    manifest["files"][".github/agents/conductor.agent.md"] = "something-else"
    (empty_repo / ".github/hve-toolkit.json").write_text(json.dumps(manifest), encoding="utf-8")
    proc = install(empty_repo)
    assert "KEEP-LOCAL" in proc.stdout and "local note" in agent.read_text(encoding="utf-8")
    proc = install(empty_repo, "--force")
    assert "OVERWRITE" in proc.stdout and agent.read_text(encoding="utf-8") == src
    assert list(agent.parent.glob("conductor.agent.md.hve-backup-*"))


def test_existing_files_and_config_are_merged(empty_repo):
    (empty_repo / "docs").mkdir()
    (empty_repo / "docs/requirements-definition.md").write_text("# 既存の要求定義書\n", encoding="utf-8")
    (empty_repo / "scripts").mkdir()
    (empty_repo / "scripts/hve.config.json").write_text(json.dumps({"verify": {"commands": [{"name": "unit", "run": "npm test"}]}}), encoding="utf-8")
    (empty_repo / "AGENTS.md").write_text("# 既存\n\n独自の指示\n", encoding="utf-8")
    install(empty_repo)
    assert (empty_repo / "docs/requirements-definition.md").read_text(encoding="utf-8") == "# 既存の要求定義書\n"
    cfg = json.loads((empty_repo / "scripts/hve.config.json").read_text(encoding="utf-8"))
    assert cfg["verify"]["commands"][0]["run"] == "npm test" and "gates" in cfg
    agents = (empty_repo / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.startswith("# 既存") and "独自の指示" in agents and agents.count("hve-abk:begin") == 1
    install(empty_repo)
    assert (empty_repo / "AGENTS.md").read_text(encoding="utf-8").count("hve-abk:begin") == 1


def test_obsolete_prompt_file_is_removed_on_update(empty_repo):
    install(empty_repo)
    old = empty_repo / ".github/prompts/build.prompt.md"
    old.parent.mkdir(parents=True)
    old.write_text("---\nagent: conductor\n---\n旧版の雛形\n", encoding="utf-8")
    manifest_path = empty_repo / ".github/hve-toolkit.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][".github/prompts/build.prompt.md"] = hashlib.sha256(old.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert install(empty_repo, "--check").returncode == 1
    proc = install(empty_repo)
    assert "REMOVE" in proc.stdout and not old.exists() and not old.parent.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert ".github/prompts/build.prompt.md" not in manifest["files"]
    assert install(empty_repo, "--check").returncode == 0


def test_modified_obsolete_file_is_kept(empty_repo):
    install(empty_repo)
    old = empty_repo / ".github/prompts/build.prompt.md"
    old.parent.mkdir(parents=True)
    old.write_text("利用者が書き換えた雛形\n", encoding="utf-8")
    manifest_path = empty_repo / ".github/hve-toolkit.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][".github/prompts/build.prompt.md"] = "hash-of-the-original"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    proc = install(empty_repo)
    assert "KEEP-LOCAL" in proc.stdout and old.exists()


def test_uninstall(empty_repo):
    install(empty_repo)
    (empty_repo / "AGENTS.md").write_text((empty_repo / "AGENTS.md").read_text(encoding="utf-8") + "\n追記\n", encoding="utf-8")
    proc = install(empty_repo, "--uninstall")
    assert proc.returncode == 0
    assert not (empty_repo / ".github/agents/conductor.agent.md").exists()
    assert not (empty_repo / "scripts/rdcheck.py").exists()
    assert (empty_repo / "docs/requirements-definition.md").exists()
    assert "hve-abk" not in (empty_repo / "AGENTS.md").read_text(encoding="utf-8")


def test_refuses_non_git_and_self(tmp_path):
    proc = install(tmp_path)
    assert proc.returncode != 0 and "git" in proc.stderr
    proc = run([sys.executable, str(SOURCE / "tools" / "install.py"), "--target", str(SOURCE)], SOURCE)
    assert proc.returncode != 0
