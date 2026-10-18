"""System tests for FR-1016 AC-104 (time-only /build request generation).

Run in a disposable repository (installed_repo fixture).  Expected values come
only from the acceptance criteria.  The command name/arguments are not fixed by
the requirements; the assumption below is the single place to adjust:
    python scripts/build-request.py <許容時間>
"""
import hashlib
import re
import sys

import pytest

from conftest import run

COMMAND = ["scripts/build-request.py"]

REQ = """# 要求定義書

## 要求

#### FR-@@9001@@ 承認済み・未着手
- 要求: 利用者は A できる。
- 決定状態: 承認済み　優先度: MUST
- 関連する既存資産: なし
- 受入基準 AC-@@9001@@: A のとき A になる。
  - 検証レベル: system

#### FR-@@9002@@ 承認済み・未着手 2
- 要求: 利用者は B できる。
- 決定状態: 承認済み　優先度: SHOULD
- 関連する既存資産: FR-@@9001@@
- 受入基準 AC-@@9002@@: B のとき B になる。
  - 検証レベル: system

#### FR-@@9003@@ 承認待ち
- 要求: 利用者は C できる。
- 決定状態: 承認待ち　優先度: MUST
- 関連する既存資産: なし
- 受入基準 AC-@@9003@@: C のとき C になる。
  - 検証レベル: system

#### FR-@@9004@@ 承認済み・AC がすべて停止中
- 要求: 利用者は D できる。
- 決定状態: 承認済み　優先度: MUST
- 関連する既存資産: なし
- 受入基準 AC-@@9004@@: D のとき D になる。
  - 検証レベル: system
  - BLOCKED: Q-@@9004@@
"""


def _f(text):
    return text.replace("@@", "")


def _snapshot(repo):
    return {
        p.relative_to(repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in repo.rglob("*")
        if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts
    }


@pytest.fixture
def repo_with_backlog(installed_repo):
    docs = installed_repo / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "requirements-definition.md").write_text(_f(REQ), encoding="utf-8")
    run(["git", "add", "-A"], installed_repo)
    run(["git", "commit", "-q", "-m", "backlog fixture"], installed_repo)
    return installed_repo


def _scope_ids(out):
    m = re.search(r"scope\s*[:=]\s*\[?([^\]\n]*)\]?", out)
    assert m, out
    return set(re.findall(r"(?:NFR-[A-Z0-9]+|FR)-\d+", m.group(1)))


# FR-1016 AC-104
def test_time_only_generates_pasteable_request_without_side_effects(repo_with_backlog):
    repo = repo_with_backlog
    before = _snapshot(repo)
    r = run([sys.executable, *COMMAND, "120分"], repo)
    for tag in ("<request>", "<answers>", "<references>", "<run_options>"):
        assert tag in r.stdout
    assert "max_hours" in r.stdout
    ids = _scope_ids(r.stdout)
    assert ids, r.stdout
    assert ids <= {_f("FR-@@9001@@"), _f("FR-@@9002@@")}
    assert _f("FR-@@9003@@") not in ids and _f("FR-@@9004@@") not in ids
    assert _snapshot(repo) == before
    assert not (repo / "work" / "runs").exists() or not any((repo / "work" / "runs").iterdir())
    assert run(["git", "status", "--porcelain"], repo).stdout.strip() == ""


# FR-1016 AC-104 (abnormal: no candidates -> nothing to paste, normal exit, no change)
def test_no_candidates_outputs_no_request_and_changes_nothing(installed_repo):
    repo = installed_repo
    docs = repo / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "requirements-definition.md").write_text(
        _f(REQ.split("#### FR-@@9001@@")[0] + "#### FR-@@9003@@ 承認待ち\n- 要求: C\n- 決定状態: 承認待ち　優先度: MUST\n"
        "- 受入基準 AC-@@9003@@: C。\n  - 検証レベル: system\n"),
        encoding="utf-8",
    )
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-q", "-m", "no candidates"], repo)
    before = _snapshot(repo)
    r = run([sys.executable, *COMMAND, "60分"], repo, check=False)
    assert r.returncode == 0, r.stderr
    assert "<run_options>" not in r.stdout
    assert _f("FR-@@9003@@") in r.stdout  # exclusion reason is shown
    assert _snapshot(repo) == before


# FR-1016 AC-104 (abnormal: invalid duration -> error, no request, no change)
@pytest.mark.parametrize("bad", ["60", "0分", "abc", "10x"])
def test_invalid_duration_fails_without_request_or_changes(repo_with_backlog, bad):
    repo = repo_with_backlog
    before = _snapshot(repo)
    r = run([sys.executable, *COMMAND, bad], repo, check=False)
    assert r.returncode != 0
    assert "<run_options>" not in r.stdout
    assert _snapshot(repo) == before

