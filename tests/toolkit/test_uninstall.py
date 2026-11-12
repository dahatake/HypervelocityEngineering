"""tools/uninstall.py: remove EABK installed by any version (FR-1087)."""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile

import pytest

from conftest import SOURCE, git, init_git, run

UNINSTALL = SOURCE / "tools" / "uninstall.py"
CATALOG = SOURCE / "tools" / "uninstall-catalog.json"


def sha(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def uninstall(target, *args, catalog=None):
    cmd = [sys.executable, str(UNINSTALL), "--target", str(target), *args]
    if catalog:
        cmd += ["--catalog", str(catalog)]
    return run(cmd, target)


def install(target, *args):
    return run([sys.executable, str(SOURCE / "tools" / "install.py"), "--target", str(target), "--skip-verify", *args], target)


def baseline(repo):
    """A repository with the user's own files and a commit: the state the uninstaller must give back."""
    git(repo, "config", "core.autocrlf", "false")
    (repo / "AGENTS.md").write_bytes(b"# Our agents\r\n\r\nBe careful with payments.\r\n")
    (repo / ".gitignore").write_bytes(b"node_modules/\r\n")
    (repo / "users-guide").mkdir()
    (repo / "users-guide/README.md").write_text("# our own guide\n", encoding="utf-8")
    (repo / "app.py").write_text("print(1)\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "baseline")


def status(repo) -> str:
    return git(repo, "status", "--porcelain", "--ignored", "--untracked-files=all")


# FR-1087 AC-476: the catalog is generated from the installer history and covers what this version ships
def test_catalog_covers_this_version():
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    sys.path.insert(0, str(SOURCE / "tools"))
    try:
        import install as inst  # noqa: E402
    finally:
        sys.path.pop(0)
    ver = [l for l in (SOURCE / "scripts/ebaklib.py").read_text(encoding="utf-8").splitlines() if l.startswith("TOOLKIT_VERSION")]
    assert cat["schema"] == 1 and f'"{cat["toolkit_version"]}"' in ver[0], "python tools/build-uninstall-catalog.py で作り直します"
    assert cat["installer_versions"] >= 40
    for rel in inst.MANAGED:
        assert inst.dest_of(rel) in cat["files"] and inst.dest_of(rel) in cat["current"], rel
        assert inst.sha(SOURCE / rel) in cat["files"][inst.dest_of(rel)], rel
    for rel in inst.TEMPLATES:
        assert rel in cat["data"], rel
    assert {".github/ebak-toolkit.json", ".github/hve-toolkit.json"} <= set(cat["manifests"])
    assert {"scripts/ebak.config.json", "scripts/hve.config.json"} <= set(cat["configs"])
    assert ["<!-- hve-conductor:begin -->", "<!-- hve-conductor:end -->"] in cat["markers"]
    assert inst.GITIGNORE_HEADER in cat["ignore"][".gitignore"]["headers"]
    assert any(h.startswith("# conductor toolkit") for h in cat["ignore"][".gitignore"]["headers"])
    assert {".ebak-backup-", ".hve-backup-"} <= set(cat["backup_infixes"])


# FR-1087 AC-476: the committed catalog matches the history and this version's shipped content (a stale one would keep
# this version's files as KEEP-LOCAL for users who download the catalog)
def test_catalog_is_up_to_date():
    if run(["git", "rev-parse", "--is-shallow-repository"], SOURCE).stdout.strip() == "true":
        pytest.skip("浅い clone では履歴から作れません")
    proc = run([sys.executable, str(SOURCE / "tools/build-uninstall-catalog.py"), "--check"], SOURCE)
    assert proc.returncode == 0, proc.stdout + proc.stderr + "\npython tools/build-uninstall-catalog.py で作り直します"


# FR-1087 AC-478: install -> uninstall --purge gives back the pre-install commit byte for byte (CRLF kept)
def test_purge_round_trip_is_byte_identical(empty_repo):
    baseline(empty_repo)
    assert install(empty_repo).returncode == 0
    assert install(empty_repo).returncode == 0
    (empty_repo / "work").mkdir(exist_ok=True)
    (empty_repo / "work/log.txt").write_text("x", encoding="utf-8")
    dry = uninstall(empty_repo, "--purge", "--dry-run")
    assert dry.returncode == 0 and "REMOVE" in dry.stdout and "(dry-run)" in dry.stdout
    assert (empty_repo / ".github/ebak-toolkit.json").exists()  # nothing written
    proc = uninstall(empty_repo, "--purge")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert status(empty_repo) == "", status(empty_repo)
    again = uninstall(empty_repo, "--purge")
    assert again.returncode == 0 and "changes=0" in again.stdout and "痕跡はありません" in again.stdout


# FR-1087 AC-475: without a manifest, the names / markers / headers / backups of every version are removed; the user's
# files, a file of theirs at an old path and their own lines stay; --force never touches a path only an old version used
def test_old_version_without_manifest(empty_repo, tmp_path):
    baseline(empty_repo)
    files = {
        ".github/agents/conductor.agent.md": "conductor v0\n",
        "scripts/hooks/gate.py": "print('gate')\n",
        ".github/agents/old-modified.agent.md": "the user changed this\n",
        "users-guide/README.md": None,  # the user's own file at a path old versions installed into
    }
    cat = {"schema": 1, "toolkit_version": "9.9.9", "installer_versions": 1,
           "files": {rel: [sha(t or "old guide\n")] for rel, t in files.items()},
           "current": {}, "templates": {}, "manifests": [".github/ebak-toolkit.json", ".github/hve-toolkit.json"],
           "configs": ["scripts/hve.config.json"],
           "markers": [["<!-- hve-conductor:begin -->", "<!-- hve-conductor:end -->"]],
           "blocks": [["AGENTS.md", "# AGENTS.md"], [".github/copilot-instructions.md", "# Copilot instructions"]],
           "ignore": {".gitignore": {"headers": ["# conductor toolkit: temporary run files (kept 14 days)"], "lines": ["/work/"]}},
           "backup_infixes": [".hve-backup-"], "data": ["docs/run-history.md"], "work_dirs": ["work"],
           "runs": {"branch_prefix": "run/", "worktree_infix": "-run-", "pool_dir": "worktrees"}}
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(cat), encoding="utf-8")
    for rel, text in files.items():
        if text:
            (empty_repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (empty_repo / rel).write_text(text if "modified" not in rel else "edited by the user\n", encoding="utf-8")
    (empty_repo / "scripts/hooks/gate.py.hve-backup-20261001").write_text("old\n", encoding="utf-8")
    (empty_repo / "scripts/hve.config.json").write_text("{\"files\": {\"catalog\": \"docs/hve-catalog.md\"}}\n", encoding="utf-8")
    (empty_repo / "docs").mkdir()
    (empty_repo / "docs/hve-catalog.md").write_text("# catalog\n", encoding="utf-8")
    (empty_repo / "docs/run-history.md").write_text("# runs\n", encoding="utf-8")
    agents = empty_repo / "AGENTS.md"
    agents.write_bytes(agents.read_bytes() + b"\r\n<!-- hve-conductor:begin -->\r\nold rules\r\n<!-- hve-conductor:end -->\r\n")
    (empty_repo / ".gitignore").write_bytes(b"node_modules/\r\n\r\n# conductor toolkit: temporary run files (kept 14 days)\r\n/work/\r\n")

    proc = uninstall(empty_repo, "--purge", "--force", catalog=catalog)
    out = proc.stdout
    assert "KEEP-UNKNOWN  .github/agents/old-modified.agent.md" in out and "KEEP-UNKNOWN  users-guide/README.md" in out
    assert proc.returncode == 0, out + proc.stderr  # KEEP-UNKNOWN is not the toolkit's: no residue
    assert (empty_repo / ".github/agents/old-modified.agent.md").read_text(encoding="utf-8") == "edited by the user\n"
    for rel in (".github/agents/conductor.agent.md", "scripts/hooks", "scripts/hve.config.json", "docs/hve-catalog.md",
                "docs/run-history.md"):
        assert not (empty_repo / rel).exists(), rel
    (empty_repo / ".github/agents/old-modified.agent.md").unlink()
    assert status(empty_repo) == "", status(empty_repo)  # AGENTS.md, .gitignore: byte for byte, CRLF included


# FR-1087 AC-475 AC-478: a modified file this version ships is kept (exit 1, RESIDUE) unless --force
def test_modified_file_is_residue_unless_forced(empty_repo):
    baseline(empty_repo)
    install(empty_repo)
    agent = empty_repo / ".github/agents/rd-auditor.agent.md"
    agent.write_text(agent.read_text(encoding="utf-8") + "\nours\n", encoding="utf-8")
    proc = uninstall(empty_repo)
    assert proc.returncode == 1 and "KEEP-LOCAL" in proc.stdout and "RESIDUE" in proc.stdout
    assert agent.exists() and (empty_repo / "docs/requirements-definition.md").exists()  # data kept without --purge
    proc = uninstall(empty_repo, "--force")
    assert proc.returncode == 0 and not agent.exists()


def test_refuses_toolkit_source_and_non_git(tmp_path):
    proc = run([sys.executable, str(UNINSTALL), "--target", str(SOURCE), "--dry-run"], SOURCE)
    assert proc.returncode != 0 and "toolkit のソース" in proc.stderr
    proc = run([sys.executable, str(UNINSTALL), "--target", str(tmp_path)], tmp_path)
    assert proc.returncode != 0 and "git" in proc.stderr


def make_link(link, target):
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    else:
        os.symlink(target, link, target_is_directory=True)


# FR-1087 AC-477: the old conductor's worktrees are only listed by default; --runs removes them without following the
# shared dependency link, deletes merged run/* branches and keeps unmerged ones
def test_runs_worktrees_and_branches(tmp_path):
    repo = tmp_path / "app"
    repo.mkdir()
    init_git(repo)
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    shared = tmp_path / "shared_node_modules"
    shared.mkdir()
    (shared / "dep.js").write_text("keep me\n", encoding="utf-8")
    git(repo, "branch", "run/merged")
    wt = tmp_path / "app-run-202610010000"
    git(repo, "worktree", "add", "-q", "-b", "run/202610010000", str(wt))
    (wt / "x.txt").write_text("x\n", encoding="utf-8")
    git(wt, "add", "-A")
    git(wt, "commit", "-qm", "unmerged work")
    make_link(wt / "node_modules", shared)

    proc = uninstall(repo)
    assert "RUN-WORKTREE" in proc.stdout and "RUN-BRANCH" in proc.stdout and wt.exists()
    proc = uninstall(repo, "--runs")
    assert "UNLINK" in proc.stdout and "REMOVE-WORKTREE" in proc.stdout
    assert not wt.exists() and (shared / "dep.js").read_text(encoding="utf-8") == "keep me\n"
    branches = git(repo, "branch", "--format=%(refname:short)").split()
    assert "run/merged" not in branches and "run/202610010000" in branches
    assert proc.returncode == 1 and "KEEP-BRANCH(unmerged)" in proc.stdout


# FR-1087 AC-475 AC-478: the oldest committed installer (an "hve" version), run for real, then removed with no manifest
@pytest.mark.parametrize("commit", ["a62da1fa"])
def test_real_old_version_install_is_removed(empty_repo, tmp_path, commit):
    if run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], SOURCE).returncode != 0:
        pytest.skip(f"{commit} がありません（浅い clone）")
    src = tmp_path / "old"
    data = subprocess.run(["git", "archive", commit], cwd=str(SOURCE), capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        if hasattr(tarfile, "data_filter"):
            tf.extractall(src, filter="data")
        else:
            tf.extractall(src)  # noqa: S202 - our own git archive
    git(empty_repo, "config", "core.autocrlf", "false")
    # LF: installers before FR-1087 rewrote a CRLF file as LF
    (empty_repo / ".gitignore").write_bytes(b"node_modules/\n")
    (empty_repo / "AGENTS.md").write_bytes(b"# Our agents\n\nrules\n")
    git(empty_repo, "add", "-A")
    git(empty_repo, "commit", "-qm", "baseline")
    run([sys.executable, str(src / "tools/install.py"), "--target", str(empty_repo)], empty_repo)
    assert (empty_repo / ".github/hve-toolkit.json").exists() and "hve-conductor:begin" in (empty_repo / "AGENTS.md").read_text(encoding="utf-8")
    (empty_repo / ".github/hve-toolkit.json").unlink()
    proc = uninstall(empty_repo, "--purge")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert status(empty_repo) == "", status(empty_repo)
    shutil.rmtree(src, ignore_errors=True)


def test_install_py_delegates_uninstall(empty_repo):
    baseline(empty_repo)
    install(empty_repo)
    proc = run([sys.executable, str(SOURCE / "tools/install.py"), "--target", str(empty_repo), "--purge"], empty_repo)
    assert proc.returncode == 0 and "installer versions" in proc.stdout
    assert status(empty_repo) == ""


# FR-1087 AC-478: a folder inside another repository (no .git of its own, or a broken one) is refused, not treated as git
def test_refuses_folder_inside_another_repository(empty_repo):
    sub = empty_repo / "sub"
    (sub / ".git").mkdir(parents=True)
    (sub / "AGENTS.md").write_text("x\n", encoding="utf-8")
    proc = uninstall(sub, "--purge")
    assert proc.returncode != 0 and "git リポジトリの最上位ではありません" in proc.stderr
    assert (sub / "AGENTS.md").exists()