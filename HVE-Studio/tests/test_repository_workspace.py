"""FR-1086 AC-470..472 / FR-1088 AC-480..483: arbitrary local repositories."""
import json
import os
import subprocess
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from test_studio import m, studio, _snapshot as _bytes_snapshot, RD, CATALOG
from task_state import TaskStore
import remote_github
import repo_scan


def init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path.resolve()


def write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _snapshot(root):
    return {rel: (content, (root / rel).stat().st_mtime_ns) for rel, content in _bytes_snapshot(root).items()}


# FR-1086 AC-471 / FR-1088 AC-480: no requirement IDs or source files are necessary.
@pytest.mark.parametrize("content", ["readme", "assets", "empty"])
def test_document_only_asset_only_and_empty_git_repositories(tmp_path, content, capsys):
    root = init_repo(tmp_path / content)
    if content == "readme":
        write(root, "README.md", "# Project\n- [ ] Ship\n- [x] Design\n```\n- [ ] Not a task\n#### FR-999 Example only\n```\n")
    elif content == "assets":
        (root / "picture.png").write_bytes(b"\x89PNG\0")
    before = _snapshot(root)
    model = m.build_model(root)
    assert model["meta"]["mode"] == "code" and "error" not in model["meta"]
    assert len(model["tasks"]) == (2 if content == "readme" else 0)
    assert not model["reqs"]
    assert studio.main(["--repo", str(root), "--check"]) == 0
    assert "repository:" in capsys.readouterr().out
    assert _snapshot(root) == before


# FR-1086 AC-470 AC-472 / FR-1088 AC-480: packages/ is source, explicit management wins.
def test_partial_management_is_supplemented_with_provenance(tmp_path):
    root = init_repo(tmp_path / "mixed")
    write(root, "docs/requirements-definition.md", RD)
    write(root, "docs/catalog.md", CATALOG)
    write(root, "docs/PRD.md", "#### FR-001 Not authoritative\n\n#### FR-NEW Feature\n- 受入基準 AC-909: Kept\n  - 検証レベル: integration\n")
    write(root, "packages/web/app.ts", "import './helper';\n// FR-001\n// TODO: Handle retries\n")
    write(root, "packages/web/helper.ts", "export const helper = 1;")
    write(root, "package.json", '{"dependencies":{"example":"^1"}}')
    before = _snapshot(root)
    model = m.build_model(root)
    reqs = {r["id"]: r for r in model["reqs"]}
    assert reqs["FR-001"]["title"] == "申請の下書き保存"
    assert reqs["FR-NEW"]["file"] == "docs/PRD.md" and reqs["FR-NEW"]["acs"][0]["id"] == "AC-909"
    feature = next(f for f in model["catalog"]["features"] if f["req"] == "FR-001")
    assert "packages/web/app.ts" in feature["impl"]
    assert model["repository"]["dependencies"] == [{"name": "example", "version": "^1", "kind": "dependencies", "file": "package.json"}]
    assert model["repository"]["links"] == [{"source": "packages/web/app.ts", "target": "packages/web/helper.ts", "kind": "import"}]
    assert model["tasks"][0]["file"] == "packages/web/app.ts" and model["tasks"][0]["line"] == 3
    assert _snapshot(root) == before


# FR-1088 AC-480: schema-free configuration and ledger-only data are not rejected.
def test_ledger_only_and_nested_repository_selection(tmp_path):
    outer = init_repo(tmp_path / "outer")
    write(outer, "docs/catalog.md", CATALOG)
    inner = init_repo(outer / "nested")
    write(inner, "tests/system/ledger.json", '{"cases":[]}')
    assert m.find_root(inner) == inner
    model = m.build_model(inner)
    assert model["meta"]["mode"] == "eabk" and "error" not in model["meta"]


# FR-1088 AC-481: changes to code, untracked files, deletions and configuration invalidate the cache.
def test_code_cache_tracks_edits_additions_deletions_and_config(tmp_path):
    root = init_repo(tmp_path / "code")
    file = write(root, "app.py", "# TODO: First\n")
    state = studio.State(root, tmp_path / "state")
    first = state.fingerprint()
    assert json.loads(state.model_bytes())["tasks"][0]["title"] == "First"
    file.write_text("# TODO: Second, changed\n", encoding="utf-8")
    assert state.fingerprint() != first
    assert json.loads(state.model_bytes())["tasks"][0]["title"] == "Second, changed"
    before = state.fingerprint()
    write(root, "README.md", "New")
    assert state.fingerprint() != before
    before = state.fingerprint()
    file.unlink()
    assert state.fingerprint() != before
    assert json.loads(state.model_bytes())["tasks"] == []
    before = state.fingerprint()
    write(root, "scripts/ebak.config.json", '{"management_files":{"catalog":"custom/catalog.md"}}')
    assert state.fingerprint() != before
    assert json.loads(state.model_bytes())["meta"]["files"]["catalog"] is None
    before = state.fingerprint()
    generated = write(root, "dist/bundle.js", "// generated")
    assert state.fingerprint() != before
    assert any(f["path"] == "dist/bundle.js" for f in json.loads(state.model_bytes())["repository"]["files"])
    before = state.fingerprint()
    generated.unlink()
    assert state.fingerprint() != before


# FR-1088 AC-480 AC-481: all local refs and more than 100 commits, including an unborn HEAD.
def test_history_is_not_truncated_and_ref_updates_invalidate_cache(tmp_path):
    root = init_repo(tmp_path / "history")
    commands = []
    for i in range(102):
        subject = f"History entry {i}"
        commands.append(f"commit refs/heads/history\ncommitter Test <test@example.invalid> {1700000000 + i} +0000\ndata {len(subject)}\n{subject}\n")
    subprocess.run(["git", "fast-import", "--quiet"], cwd=root,
                   input="\n".join(commands).encode("utf-8"), capture_output=True, check=True)
    before = _snapshot(root)
    history = m.build_model(root)["repository"]["history"]
    assert len(history) == 102 and history[0]["subject"] == "History entry 101"
    assert _snapshot(root) == before
    fingerprint = m.fingerprint(root)
    subprocess.run(["git", "update-ref", "refs/heads/other", history[0]["commit"]], cwd=root, check=True)
    assert m.fingerprint(root) != fingerprint


# FR-1088 AC-480: inventories and component files have no old 5000 / 300 record truncation.
def test_inventory_does_not_truncate_large_components(tmp_path):
    root = init_repo(tmp_path / "large")
    for i in range(5002):
        write(root, f"packages/core/file{i}.py", "")
    model = m.build_model(root)
    assert len(model["repository"]["files"]) == 5002
    assert len(model["catalog"]["parts"][0]["files"]) == 5002
    assert len([n for n in model["graph"]["nodes"] if n["type"] == "file"]) == 5002


# FR-1088 AC-480: excluded/unreadable content is explicit, never a successful empty parse.
def test_scan_diagnostics_and_git_failure(tmp_path, monkeypatch):
    root = init_repo(tmp_path / "diagnostics")
    write(root, ".gitignore", "ignored.py\n")
    write(root, "ignored.py", "# TODO: ignored")
    write(root, ".env", "TOKEN=do-not-read")
    write(root, "node_modules/dependency/a.py", "# TODO: generated")
    write(root, "big.py", " " * (repo_scan.TEXT_MAX_BYTES + 1))
    write(root, "boundary.py", " " * repo_scan.TEXT_MAX_BYTES)
    (root / "invalid.py").write_bytes(b"\xff")
    model = m.build_model(root)
    diags = {d["path"]: d["reason"] for d in model["repository"]["diagnostics"]}
    assert "potential credentials" in diags[".env"]
    assert "big.py" in diags and "invalid.py" in diags and "node_modules/dependency/a.py" in diags
    assert next(f for f in model["repository"]["files"] if f["path"] == "boundary.py")["analysis"] == "read"
    assert not model["tasks"]
    kinds = {f["path"]: (f["kind"], f["analysis"]) for f in model["repository"]["files"]}
    assert kinds["ignored.py"] == ("ignored", "inventory-only")
    assert kinds["node_modules/dependency/a.py"] == ("generated", "inventory-only")
    assert not {"file:ignored.py", "file:node_modules/dependency/a.py"} & {n["id"] for n in model["graph"]["nodes"]}
    monkeypatch.setattr(repo_scan, "git", lambda *a: subprocess.CompletedProcess([], 1, b"", b"git unavailable"))
    with pytest.raises(repo_scan.ScanError, match="git unavailable"):
        m.build_model(root)


# FR-1088 AC-480: imports nested in blocks are linked in ast.walk order; one build reads the git inventory once.
def test_nested_python_imports_and_single_git_inventory(tmp_path, monkeypatch):
    import ast
    import sys
    root = init_repo(tmp_path / "nested")
    for rel in ("pkg/__init__.py", "pkg/a.py", "pkg/b.py", "pkg/c.py", "pkg/d.py"):
        write(root, rel, "")
    source = ("try:\n    import pkg.a\nexcept ImportError:\n    pass\n"
              "class K:\n    def f(self):\n        if True:\n            from pkg import b\n"
              "with open(__file__):\n    x = [lambda: 1]\n    from pkg import c\n")
    if sys.version_info >= (3, 10):
        source += "match x:\n    case _:\n        import pkg.d\n"
    write(root, "main.py", source)
    tree = ast.parse(source)
    assert list(repo_scan._imports(tree)) == [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    calls = []
    real = repo_scan.git
    monkeypatch.setattr(repo_scan, "git", lambda path, *a: calls.append(a) or real(path, *a))
    model = m.build_model(root)
    targets = {link["target"] for link in model["repository"]["links"] if link["source"] == "main.py"}
    assert {"pkg/a.py", "pkg/b.py", "pkg/c.py"} <= targets
    assert sys.version_info < (3, 10) or "pkg/d.py" in targets
    for name in ("cached", "others", "ignored", "refs"):
        assert calls.count(repo_scan._INVENTORY_COMMANDS[name]) == 1, name


# FR-1088 AC-482 AC-483: durable task edits never change originals and never bleed into another repository.
def test_task_persistence_overrides_isolation_and_rejection(tmp_path):
    a = init_repo(tmp_path / "a")
    b = init_repo(tmp_path / "b")
    file = write(a, "README.md", "- [ ] Ship\n")
    imported = m.build_model(a)["tasks"]
    original = file.read_bytes()
    store = TaskStore(tmp_path / "state")
    created = store.update(a, {"action": "create", "title": "Plan"}, imported)["id"]
    store.update(a, {"action": "update", "id": imported[0]["id"], "status": "doing"}, imported)
    store.update(a, {"action": "update", "id": created, "title": "Plan release", "status": "done"}, imported)
    saved = TaskStore(tmp_path / "state").list(a, imported)
    assert [(t["title"], t["status"]) for t in saved] == [("Ship", "doing"), ("Plan release", "done")]
    assert store.list(b, []) == []
    with pytest.raises(ValueError):
        store.update(a, {"action": "delete", "id": imported[0]["id"]}, imported)
    with pytest.raises(ValueError):
        store.update(a, {"action": "update", "id": created, "status": "wrong"}, imported)
    store.update(a, {"action": "reset", "id": imported[0]["id"]}, imported)
    assert store.list(a, imported)[0]["status"] == "todo"
    store.update(a, {"action": "delete", "id": created}, imported)
    assert len(store.list(a, imported)) == 1
    assert file.read_bytes() == original
    with pytest.raises(ValueError, match="outside"):
        TaskStore(a / "state").update(a, {"action": "create", "title": "Invalid storage"}, imported)
    assert not (a / "state").exists()


@pytest.fixture
def api(tmp_path):
    root = init_repo(tmp_path / "repo")
    write(root, "README.md", "- [ ] Imported\n")
    studio.STATE = studio.State(root, tmp_path / "state")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), studio.Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", root
    srv.shutdown()
    srv.server_close()
    thread.join()


def post(url, payload, headers=None):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers=headers if headers is not None else {"X-EABK-Studio": "1"}, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


# FR-1088 AC-483: stale-repository and foreign requests cannot mutate tasks; write failures are errors.
def test_task_api_rejects_stale_repo_invalid_payload_and_storage_failure(api, monkeypatch):
    url, root = api
    payload = {"repo": str(root), "action": "create", "title": "Task"}
    assert post(url + "/api/tasks", payload, {})[0] == 403
    assert post(url + "/api/tasks", {**payload, "repo": "other"})[0] == 409
    assert post(url + "/api/tasks", [1])[0] == 400
    assert post(url + "/api/tasks", payload)[0] == 200
    def fail(*args):
        raise OSError("read-only storage")
    monkeypatch.setattr(studio.STATE.tasks, "update", fail)
    code, body = post(url + "/api/tasks", payload)
    assert code == 422 and body["error"] == "task-save-failed" and "read-only" in body["detail"]


# FR-1088 AC-483: failed analysis must not switch away from the working repository.
def test_repository_switch_analysis_failure_preserves_root(api, tmp_path, monkeypatch):
    url, root = api
    other = init_repo(tmp_path / "other")
    def fail(*args):
        raise repo_scan.ScanError("cannot read repository")
    monkeypatch.setattr(m, "build_model", fail)
    code, body = post(url + "/api/repo", {"path": str(other)})
    assert code == 422 and "cannot read" in body["detail"]
    assert studio.STATE.root == root


# FR-1088 AC-482: the real browser can create, transition, reload and filter tasks without EABK.
def test_workspace_browser_persists_tasks_and_keeps_drafts(api, shared_browser, tmp_path, monkeypatch):
    url, root = api
    context = shared_browser.new_context(viewport={"width": 320, "height": 844}, locale="en-US")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    try:
        page.goto(url)
        page.get_by_test_id("workspace-link").click()
        page.get_by_test_id("workspace").wait_for()
        page.get_by_label("New task title", exact=True).fill("Ship release")
        page.get_by_role("button", name="Add", exact=True).click()
        row = page.locator('[data-task-id^="local:"]')
        row.wait_for()
        row.get_by_role("combobox").select_option("doing")
        page.wait_for_function("() => document.querySelector('[data-task-id^=\"local:\"] select')?.value === 'doing'")
        page.reload()
        assert row.get_by_role("combobox").input_value() == "doing"
        assert row.get_by_label("Title", exact=True).input_value() == "Ship release"
        page.get_by_label("New task title", exact=True).fill("Unsent draft")
        write(root, "app.py", "# TODO: Imported after refresh\n")
        page.get_by_text("Imported after refresh", exact=True).wait_for(timeout=15000)
        assert page.get_by_label("New task title", exact=True).input_value() == "Unsent draft"
        page.route("**/api/tasks", lambda route: route.fulfill(status=422, json={"error": "task-save-failed", "detail": "storage denied"}))
        page.get_by_role("button", name="Add", exact=True).click()
        page.get_by_role("alert").filter(has_text="storage denied").wait_for()
        assert page.get_by_label("New task title", exact=True).input_value() == "Unsent draft"
        page.unroute("**/api/tasks")
        page.get_by_role("button", name="JA", exact=True).click()
        assert page.get_by_label("新しいタスクの題名").input_value() == "Unsent draft"
        other = init_repo(tmp_path / "other")
        monkeypatch.setenv("EABK_STUDIO_PICK_PATH", str(other))
        page.locator("#repoBtn").click()
        page.wait_for_function("(repo) => document.querySelector('#repoBtn')?.title === repo", arg=str(other))
        assert page.locator('[data-task-id^="local:"]').count() == 0
        assert page.get_by_label("新しいタスクの題名").input_value() == ""
        monkeypatch.setenv("EABK_STUDIO_PICK_PATH", str(root))
        page.locator("#repoBtn").click()
        row.wait_for()
        assert row.get_by_label("題名", exact=True).input_value() == "Ship release"
        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
        assert not errors
    finally:
        context.close()


# FR-1088 AC-480: initialized submodule files are analysed; uninitialized ones are listed with a reason.
def test_submodules_are_inventoried_and_analysed(tmp_path):
    git = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", "-c", "protocol.file.allow=always"]
    lib = init_repo(tmp_path / "lib")
    write(lib, "core.py", "# TODO: Inside submodule\n")
    subprocess.run([*git, "add", "."], cwd=lib, check=True)
    subprocess.run([*git, "commit", "-qm", "init"], cwd=lib, check=True)
    root = init_repo(tmp_path / "main")
    for name in ("lib", "gone"):
        subprocess.run([*git, "submodule", "add", "-q", str(lib), name], cwd=root, check=True, capture_output=True)
    subprocess.run([*git, "commit", "-qm", "subs"], cwd=root, check=True)
    subprocess.run([*git, "submodule", "deinit", "-q", "-f", "gone"], cwd=root, check=True)
    model = m.build_model(root)
    subs = {s["path"]: s["state"] for s in model["repository"]["submodules"]}
    assert subs == {"lib": "initialized", "gone": "not-initialized"}
    assert [(t["file"], t["title"]) for t in model["tasks"]] == [("lib/core.py", "Inside submodule")]
    diags = {d["path"]: d["reason"] for d in model["repository"]["diagnostics"]}
    assert "not initialized" in diags["gone"]
    fingerprint = m.fingerprint(root)
    (root / "lib" / "core.py").write_text("# TODO: Changed\n", encoding="utf-8")
    assert m.fingerprint(root) != fingerprint


# FR-1088 AC-480: a fully ignored directory is one inventory entry and its contents are never read.
def test_ignored_directory_is_listed_once_without_reading(tmp_path):
    root = init_repo(tmp_path / "ign")
    write(root, ".gitignore", "node_modules/\n")
    for i in range(50):
        write(root, f"node_modules/p{i}/index.js", "// TODO: never")
    model = m.build_model(root)
    assert [f["path"] for f in model["repository"]["files"] if f["kind"] == "ignored"] == ["node_modules/"]
    assert not model["tasks"]


def _gh(responses, calls):
    def run(cmd, **kwargs):
        calls.append(cmd)
        out, code, err = responses[cmd[1]]
        return subprocess.CompletedProcess(cmd, code, json.dumps(out).encode(), err.encode())
    return run


ISSUES = [{"number": 7, "title": "Bug", "state": "OPEN", "url": "https://github.com/o/r/issues/7",
           "labels": [{"name": "bug"}], "assignees": [{"login": "dev"}], "milestone": None, "author": {"login": "pm"}},
          {"number": 8, "title": "Done", "state": "CLOSED", "url": "https://github.com/o/r/issues/8", "labels": [], "assignees": []}]


# FR-1088 AC-484: issues, pull requests and runs of every state are fetched read-only through gh; failures are explicit.
def test_github_fetch_normalizes_and_reports_failures(tmp_path, monkeypatch):
    root = init_repo(tmp_path / "remote")
    assert remote_github.fetch(root, run=lambda *a, **k: pytest.fail("gh must not run"))["reason"].startswith("no GitHub remote")
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:o/r.git"], cwd=root, check=True)
    calls, seen = [], []
    monkeypatch.setenv("HVE_STUDIO_REMOTE_LIMIT", "2")
    result = remote_github.fetch(root, run=_gh({"issue": (ISSUES, 0, ""), "pr": ([{"number": 9, "author": {"login": "a"}}], 0, ""),
                                                "run": (None, 1, "HTTP 403: rate limit")}, calls), progress=seen.append)
    assert result["status"] == "partial" and result["repo"] == "github.com/o/r"
    assert result["issues"][0]["labels"] == ["bug"] and result["issues"][0]["assignees"] == ["dev"]
    assert result["pulls"] == [{"number": 9, "author": "a"}]
    assert result["truncated"] == ["issues"] and "rate limit" in result["errors"]["runs"]
    # Sections are fetched in parallel and published one by one while the rest are still pending.
    assert sorted(c[1] for c in calls) == ["issue", "pr", "run"]
    assert all(p["status"] == "loading" for p in seen) and [len(p["pending"]) for p in seen] == [2, 1, 0]
    issue_call = next(c for c in calls if c[1] == "issue")
    pr_call = next(c for c in calls if c[1] == "pr")
    assert "--state" in issue_call and "all" in issue_call and "--state" in pr_call and "all" in pr_call
    assert [c[c.index("-R") + 1] for c in calls] == ["github.com/o/r"] * 3
    tasks = remote_github.issue_tasks(result)
    assert [(t["id"], t["status"]) for t in tasks] == [("github:issue:7", "todo"), ("github:issue:8", "done")]
    unauth = remote_github.fetch(root, run=_gh({s: (None, 4, "To get started with GitHub CLI, please run:  gh auth login")
                                                for s in ("issue", "pr", "run")}, []))
    assert unauth["status"] == "unavailable" and "gh auth login" in unauth["reason"]
    def missing(*a, **k):
        raise FileNotFoundError("gh")
    assert "not installed" in remote_github.fetch(root, run=missing)["reason"]
    def slow(cmd, **kwargs):
        if cmd[1] == "run":
            raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])
        return subprocess.CompletedProcess(cmd, 0, b"[]", b"")
    monkeypatch.setenv("HVE_STUDIO_REMOTE_TIMEOUT", "7")
    timed_out = remote_github.fetch(root, run=slow)
    assert timed_out["status"] == "partial" and "7 s" in timed_out["errors"]["runs"]
    monkeypatch.delenv("HVE_STUDIO_REMOTE_TIMEOUT")
    subprocess.run(["git", "remote", "set-url", "origin", "https://gitlab.com/o/r.git"], cwd=root, check=True)
    assert remote_github.github_repo(root) is None
    subprocess.run(["git", "remote", "set-url", "origin", "https://github.example.com/o/r"], cwd=root, check=True)
    assert remote_github.github_repo(root) == "github.example.com/o/r"
    malformed = remote_github.fetch(root, run=_gh({s: ({}, 0, "") for s in ("issue", "pr", "run")}, []))
    assert malformed["status"] == "error" and len(malformed["errors"]) == 3
    for value in ("invalid", "0", "-1"):
        monkeypatch.setenv("HVE_STUDIO_REMOTE_LIMIT", value)
        invalid = remote_github.fetch(root, run=lambda *a, **k: pytest.fail("invalid config must not fetch"))
        assert invalid["status"] == "error" and "positive integer" in invalid["reason"]


# FR-1088 AC-484: fetched issues become tasks with durable status overrides; only overrides reach the disk.
def test_state_merges_github_issues_without_persisting_remote_data(tmp_path, monkeypatch):
    root = init_repo(tmp_path / "repo")
    write(root, "README.md", "- [ ] Local\n")
    fetched = threading.Event()
    hold, release = threading.Event(), threading.Event()
    def fake(path, progress=None):
        if fetched.is_set():  # the refresh: issues arrive first, runs are still pending
            progress({"status": "loading", "repo": "github.com/o/r", "issues": ISSUES, "pulls": [], "runs": [],
                      "errors": {}, "truncated": [], "pending": ["runs"]})
            hold.set()
            release.wait(5)
        fetched.set()
        return {"status": "ok", "repo": "github.com/o/r", "issues": ISSUES, "pulls": [], "runs": [{"databaseId": 1}],
                "errors": {}, "truncated": [], "fetchedAt": "2026-01-01T00:00:00+00:00"}
    monkeypatch.setattr(studio.remote_github, "fetch", fake)
    state = studio.State(root, tmp_path / "state", remote=True)
    first = state.fingerprint()
    assert fetched.wait(5)
    for _ in range(100):
        if state.fingerprint() != first:
            break
        threading.Event().wait(0.05)
    model = json.loads(state.model_bytes())
    assert model["remote"]["status"] == "ok" and not model["remote"]["loading"]
    assert [t["id"] for t in model["tasks"]][-2:] == ["github:issue:7", "github:issue:8"]
    state.update_task({"repo": str(root), "action": "update", "id": "github:issue:7", "status": "doing"})
    assert next(t for t in json.loads(state.model_bytes())["tasks"] if t["id"] == "github:issue:7")["status"] == "doing"
    with pytest.raises(ValueError):
        state.update_task({"repo": str(root), "action": "delete", "id": "github:issue:7"})
    state.update_task({"repo": str(root), "action": "reset", "id": "github:issue:7"})
    assert next(t for t in json.loads(state.model_bytes())["tasks"] if t["id"] == "github:issue:7")["status"] == "todo"
    previous = state.fingerprint()
    state.refresh_remote()
    assert hold.wait(5)
    partial = json.loads(state.model_bytes())["remote"]
    assert partial["status"] == "loading" and partial["loading"] and partial["runs"] == [{"databaseId": 1}]
    release.set()
    for _ in range(100):
        with state.lock:
            loading = bool(state.remote_loading)
        if not loading:
            break
        threading.Event().wait(0.05)
    assert not loading and state.fingerprint() != previous
    assert sorted(p.name for p in (tmp_path / "state").iterdir()) == ["tasks.sqlite3"]
    monkeypatch.setattr(studio.remote_github, "fetch", lambda path, **k: pytest.fail("--no-remote must not fetch"))
    assert json.loads(studio.State(root, tmp_path / "other", remote=False).model_bytes())["remote"]["status"] == "disabled"


# FR-1088 AC-484: the workspace shows GitHub status, issues with links, and issue tasks in a real browser.
def test_workspace_browser_shows_github_data(api, shared_browser, monkeypatch):
    url, root = api
    monkeypatch.setattr(studio.remote_github, "fetch", lambda path, **k: {
        "status": "partial", "repo": "github.com/o/r", "issues": [{**ISSUES[0], "labels": ["bug"], "assignees": ["dev"]}],
        "pulls": [], "runs": [], "errors": {"runs": "HTTP 403"}, "truncated": [], "limit": 10000, "fetchedAt": "x"})
    studio.STATE.remote_enabled = True
    context = shared_browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    try:
        page.goto(url + "/#/workspace")
        page.get_by_test_id("workspace").wait_for()
        status = page.get_by_test_id("remote-status")
        status.filter(has_text="partially fetched").wait_for(timeout=15000)
        assert "github.com/o/r" in status.inner_text() and "HTTP 403" in status.inner_text()
        task = page.locator('[data-task-id="github:issue:7"]')
        assert task.get_by_role("link", name="GitHub").get_attribute("href") == ISSUES[0]["url"]
        page.get_by_role("button", name="GitHub issues", exact=True).click()
        row = page.get_by_test_id("workspace-inventory").get_by_role("row").filter(has_text="Bug")
        assert "bug" in row.inner_text() and "dev" in row.inner_text()
        page.get_by_role("button", name="Refetch from GitHub").click()
        assert not errors
    finally:
        context.close()
