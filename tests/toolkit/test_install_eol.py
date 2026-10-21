import hashlib
import json
import sys

from conftest import SOURCE, run

MANIFEST = ".github/ebak-toolkit.json"
AGENT = ".github/agents/reviewer.agent.md"


def install(target, *args):
    return run([sys.executable, str(SOURCE / "tools" / "install.py"), "--target", str(target), "--skip-verify", *args], target)


def to_crlf(path):
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))


def test_crlf_checkout_is_not_a_local_modification(empty_repo):
    # a Windows checkout (core.autocrlf=true) of a committed install turns every managed text file into CRLF
    assert install(empty_repo).returncode == 0
    manifest = json.loads((empty_repo / MANIFEST).read_text(encoding="utf-8"))
    for rel in manifest["files"]:
        if rel.endswith((".md", ".py", ".sh", ".json", ".yml")):
            to_crlf(empty_repo / rel)
    proc = install(empty_repo)
    assert "KEEP-LOCAL" not in proc.stdout, proc.stdout
    assert "changes=0" in proc.stdout
    assert install(empty_repo, "--check").returncode == 0


def test_crlf_file_still_updates_when_manifest_matches_old_content(empty_repo):
    install(empty_repo)
    agent = empty_repo / AGENT
    agent.write_bytes(b"old toolkit text\r\nsecond line\r\n")
    manifest = json.loads((empty_repo / MANIFEST).read_text(encoding="utf-8"))
    manifest["files"][AGENT] = hashlib.sha256(b"old toolkit text\nsecond line\n").hexdigest()
    (empty_repo / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    proc = install(empty_repo)
    assert "UPDATE" in proc.stdout and "KEEP-LOCAL" not in proc.stdout, proc.stdout
    assert agent.read_bytes() == (SOURCE / AGENT).read_bytes()


def test_crlf_file_with_real_edit_is_kept(empty_repo):
    install(empty_repo)
    agent = empty_repo / AGENT
    to_crlf(agent)
    agent.write_bytes(agent.read_bytes() + b"# local note\r\n")
    manifest = json.loads((empty_repo / MANIFEST).read_text(encoding="utf-8"))
    manifest["files"][AGENT] = "older-toolkit-hash"
    (empty_repo / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    proc = install(empty_repo)
    assert "KEEP-LOCAL" in proc.stdout and b"# local note" in agent.read_bytes()
