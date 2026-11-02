"""System acceptance test for FR-1081 (prompt prefix attached by the user-prompt hook).

The oracle is FR-1081 AC-453..457 only, not the implementation of gate.py / install.py.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from conftest import SOURCE, run

DEFAULT_REL = ".github/ebak-prompt-prefix.md"
CONFIG_REL = "scripts/ebak.config.json"


def user_prompt(repo: Path, prompt: str, session: str = "s-pp") -> dict:
    payload = {"cwd": str(repo), "prompt": prompt, "sessionId": session}
    proc = subprocess.run(
        [sys.executable, str(repo / "scripts" / "hooks" / "gate.py"), "user-prompt"],
        cwd=repo, input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    return json.loads(out) if out else {}


def context_of(res: dict) -> str:
    ctx = res.get("additionalContext")
    if ctx is None:
        ctx = (res.get("hookSpecificOutput") or {}).get("additionalContext")
    return ctx or ""


def set_prefix_config(repo: Path, **kv) -> None:
    path = repo / CONFIG_REL
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg["prompt_prefix"] = kv
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# FR-1081 AC-453 AC-454 AC-455 AC-456 AC-457
def test_prompt_prefix_install_attach_disable_rewrite_ac453_457(installed_repo: Path, tmp_path: Path) -> None:
    repo = installed_repo
    prefix = repo / DEFAULT_REL

    # AC-456: the installer creates the default text with the 4 points and the rewrite instruction
    assert prefix.is_file(), "installer must create the default prefix file"
    default_text = prefix.read_text(encoding="utf-8")
    assert default_text.strip()
    for word in ("専門家", "生の素材", "手法", "ツール", "検証", "書き直"):
        assert word in default_text, word

    # AC-453: enabled by default, non-empty file -> additionalContext is that text
    res = user_prompt(repo, "この機能の設計を見直して")
    assert default_text.strip() in context_of(res)

    # AC-455: `/build template` gets no prefix
    assert default_text.strip() not in context_of(user_prompt(repo, "/build template", "s-tpl"))

    # AC-457: rewriting the file applies from the next prompt
    marker = "CUSTOM-PREFIX-FR1081-ZZ"
    prefix.write_text(marker + "\n", encoding="utf-8")
    ctx = context_of(user_prompt(repo, "次の依頼"))
    assert marker in ctx and default_text.strip() not in ctx

    # AC-454: disabled / empty / whitespace-only / missing -> no prefix
    set_prefix_config(repo, enabled=False, file=DEFAULT_REL)
    assert marker not in context_of(user_prompt(repo, "無効化中"))
    set_prefix_config(repo, enabled=True, file=DEFAULT_REL)
    prefix.write_text(" \n\t\n", encoding="utf-8")
    assert context_of(user_prompt(repo, "空白のみ")).strip() == ""
    prefix.write_text("", encoding="utf-8")
    assert context_of(user_prompt(repo, "空")).strip() == ""
    prefix.unlink()
    assert context_of(user_prompt(repo, "ファイル無し")).strip() == ""

    # AC-456: reinstall creates the file only when missing, never overwrites an existing one
    install = [sys.executable, SOURCE / "tools" / "install.py", "--target", repo, "--skip-verify"]
    run(install, repo)
    assert prefix.is_file() and prefix.read_text(encoding="utf-8").strip()
    prefix.write_text(marker + "\n", encoding="utf-8")
    run(install, repo)
    assert prefix.read_text(encoding="utf-8").strip() == marker

    # AC-457: a second installed repository works with the same setting and the same mechanism
    other = tmp_path / "other repo"
    other.mkdir()
    for cmd in (["git", "init", "-q", "-b", "main"],
                ["git", "config", "user.email", "st@example.invalid"],
                ["git", "config", "user.name", "ST"],
                ["git", "config", "commit.gpgsign", "false"]):
        run(cmd, other)
    (other / "README.md").write_text("other\n", encoding="utf-8")
    run(["git", "add", "-A"], other)
    run(["git", "commit", "-q", "-m", "initial"], other)
    run([sys.executable, SOURCE / "tools" / "install.py", "--target", other, "--skip-verify"], other)
    other_prefix = other / DEFAULT_REL
    assert other_prefix.is_file()
    other_prefix.write_text("OTHER-REPO-PREFIX\n", encoding="utf-8")
    assert "OTHER-REPO-PREFIX" in context_of(user_prompt(other, "別リポジトリ", "s-other"))
