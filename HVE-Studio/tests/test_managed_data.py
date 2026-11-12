"""FR-1090 AC-488..492: generated display data is disposable, not authoritative."""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from test_studio import m, studio
from test_repository_workspace import init_repo, write
import managed_data


@pytest.fixture
def data_repo(tmp_path):
    root = init_repo(tmp_path / "source repo")
    write(root, "docs/PRD.md", "#### FR-ING-01 Import video\n- 受入基準 AC-909: The video is imported\n  - 検証レベル: integration\n")
    write(root, "src/app.py", "# FR-ING-01\n# TODO: Validate video\n")
    write(root, "tests/test_app.py", "# FR-ING-01\n")
    return root


def original_files(root):
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file() and not {".git", ".hve-studio"} & set(p.relative_to(root).parts)}


# FR-1090 AC-488: examples cannot become requirements or hide the real definition after a code fence.
def test_requirement_examples_are_not_definitions():
    text = ("<!--\n#### FR-012 Commented example\n-->\n"
            "```markdown\n<!-- example marker\n#### FR-013 Code example\n```\n"
            "#### FR-ING-01 Real requirement\n")
    document = m.parse_text(text, "docs/PRD.md")
    assert document["headings"] == [(8, 4, "FR-ING-01 Real requirement")]


# FR-1090 AC-488 AC-489 AC-491 AC-492: real inputs, links, progress, staleness and cleanup.
def test_sync_refresh_and_delete_preserve_originals(data_repo, tmp_path):
    root = data_repo
    before = original_files(root)
    fp = m.fingerprint(root)
    events = []
    assert managed_data.sync(root, events.append)["state"] == "current"
    assert m.fingerprint(root) == fp  # generated data cannot invalidate itself
    status, saved = managed_data.inspect(root)
    assert status["exists"] and saved["reqs"][0]["id"] == "FR-ING-01"
    assert saved["reqs"][0]["acs"][0]["id"] == "AC-909"
    feature = saved["catalog"]["features"][0]
    assert feature["impl"] == ["src/app.py"] and feature["tests"] == ["tests/test_app.py"]
    assert not saved["cases"] and not saved["reqs"][0]["status"]
    assert original_files(root) == before
    assert {"inventory", "files", "relationships", "model", "write", "done"} <= {e["phase"] for e in events}
    assert all(0 <= e["completed"] <= e["total"] for e in events)
    assert next(e for e in reversed(events) if e["phase"] == "files")["completed"] == 3
    assert next(e for e in reversed(events) if e["phase"] == "model")["completed"] == 1

    state = studio.State(root, tmp_path / "state")
    assert json.loads(state.model_bytes())["meta"]["generatedData"]["state"] == "current"
    write(root, "docs/PRD.md", "#### FR-ING-01 Updated requirement\n")
    assert managed_data.inspect(root)[0]["state"] == "stale"
    assert managed_data.inspect(root)[1] is None
    assert json.loads(state.model_bytes())["reqs"][0]["title"] == "Updated requirement"
    managed_data.sync(root)
    assert managed_data.inspect(root)[1]["reqs"][0]["title"] == "Updated requirement"
    before_delete = original_files(root)
    assert managed_data.delete(root)["state"] == "missing"
    assert not (root / managed_data.DIRECTORY).exists()
    assert original_files(root) == before_delete
    assert json.loads(state.model_bytes())["reqs"][0]["id"] == "FR-ING-01"
    assert managed_data.delete(root)["state"] == "missing"


# FR-1090 AC-491 AC-492: no overwrite or deletion of foreign/edited files, even in the reserved directory.
@pytest.mark.parametrize("foreign", [True, False])
def test_modified_or_foreign_data_is_retained(data_repo, foreign):
    path = data_repo / managed_data.RELATIVE_PATH
    if foreign:
        path.parent.mkdir()
        path.write_text('{"mine":true}', encoding="utf-8")
    else:
        managed_data.sync(data_repo)
        path.write_bytes(path.read_bytes().replace(b"Import video", b"Edited title"))
    content = path.read_bytes()
    assert managed_data.inspect(data_repo)[0]["state"] == "conflict"
    for action in (managed_data.sync, managed_data.delete):
        with pytest.raises(managed_data.DataError):
            action(data_repo)
        assert path.read_bytes() == content
    assert not (path.parent / ".operation-lock").exists()


# FR-1090 AC-491: only the owned file is removed; a user's neighboring file remains.
def test_delete_preserves_neighboring_files(data_repo):
    managed_data.sync(data_repo)
    other = write(data_repo, ".hve-studio/mine.txt", "keep")
    managed_data.delete(data_repo)
    assert other.read_text(encoding="utf-8") == "keep"


# FR-1090 AC-492: a failed write or a changing source retains the previous good file.
@pytest.mark.parametrize("failure", ["write", "source"])
def test_failed_sync_keeps_previous_data(data_repo, monkeypatch, failure):
    managed_data.sync(data_repo)
    path = data_repo / managed_data.RELATIVE_PATH
    before = path.read_bytes()
    build = m.build_model

    def failing_replace(*args):
        raise OSError("disk write failure")

    def changing_build(root, **kwargs):
        model = build(root, **kwargs)
        write(root, "src/new.py", "# source changed\n")
        return model

    if failure == "write":
        monkeypatch.setattr(managed_data.os, "replace", failing_replace)
    else:
        monkeypatch.setattr(m, "build_model", changing_build)
    with pytest.raises((OSError, managed_data.DataError), match="failure|changed"):
        managed_data.sync(data_repo)
    assert path.read_bytes() == before
    assert sorted(p.name for p in path.parent.iterdir()) == [managed_data.FILENAME]


# FR-1090 AC-492: reject path indirection.
def test_linked_path_is_rejected(data_repo, tmp_path):
    directory = data_repo / managed_data.DIRECTORY
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        directory.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink permission unavailable")
    try:
        for action in (managed_data.sync, managed_data.delete):
            with pytest.raises(managed_data.DataError, match="linked"):
                action(data_repo)
        assert not list(outside.iterdir())
    finally:
        directory.unlink()


# FR-1090 AC-492: lock coverage must not depend on Windows symlink permission.
def test_operation_lock_is_rejected(data_repo):
    lock = write(data_repo, ".hve-studio/.operation-lock", "another operation")
    for action in (managed_data.sync, managed_data.delete):
        with pytest.raises(managed_data.DataError, match="another data operation"):
            action(data_repo)
    assert lock.read_text(encoding="utf-8") == "another operation"


# FR-1090 AC-492: hardlinked snapshots cannot be replaced or deleted.
def test_hardlinked_data_is_rejected(data_repo, tmp_path):
    managed_data.sync(data_repo)
    path = data_repo / managed_data.RELATIVE_PATH
    other = tmp_path / "linked.json"
    os.link(path, other)
    before = other.read_bytes()
    for action in (managed_data.sync, managed_data.delete):
        with pytest.raises(managed_data.DataError, match="single regular file"):
            action(data_repo)
        assert path.read_bytes() == other.read_bytes() == before


# FR-1090 AC-489 AC-491: CLI has actionable state and real progress without starting a server.
def test_cli_sync_status_and_delete(data_repo, capsys):
    for operation in ("--sync-data", "--data-status", "--delete-data"):
        assert studio.main(["--repo", str(data_repo), operation]) == 0
        out = capsys.readouterr().out
        if operation != "--data-status":
            assert "[####################] done 1/1" in out
        assert json.loads(out.splitlines()[-1])["exists"] is (operation != "--delete-data")


@pytest.fixture
def data_server(data_repo, tmp_path, monkeypatch):
    state = studio.State(data_repo, tmp_path / "task-storage", remote=False)
    monkeypatch.setattr(studio, "STATE", state, raising=False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def request(url, endpoint, payload=None, header=True):
    headers = {"Content-Type": "application/json"}
    if header:
        headers["X-EABK-Studio"] = "1"
    req = urllib.request.Request(url + endpoint, data=None if payload is None else json.dumps(payload).encode(),
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def wait_job(state):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = state.data_status()
        if result["operation"].get("status") != "running":
            return result
        time.sleep(0.01)
    pytest.fail("data operation did not finish")


# FR-1090 AC-489 AC-490 AC-491 AC-492: same operations through HTTP with repo/confirmation guards.
def test_http_sync_delete_and_error_reporting(data_server, data_repo):
    state, url = data_server
    payload = {"repo": str(data_repo)}
    for endpoint, body, header in (("/api/data/sync", payload, False),
                                    ("/api/data/sync", {"repo": "wrong"}, True),
                                    ("/api/data/delete", payload, True)):
        with pytest.raises(urllib.error.HTTPError) as error:
            request(url, endpoint, body, header)
        assert error.value.code in (403, 409)
    assert request(url, "/api/data")["data"]["state"] == "missing"
    request(url, "/api/data/sync", payload)
    assert wait_job(state)["data"]["state"] == "current"
    assert request(url, "/api/model")["meta"]["generatedData"]["exists"]
    request(url, "/api/data/delete", {**payload, "confirm": True})
    assert wait_job(state)["data"]["state"] == "missing"
    managed_data.sync(data_repo)
    (data_repo / managed_data.RELATIVE_PATH).write_text("edited", encoding="utf-8")
    request(url, "/api/data/delete", {**payload, "confirm": True})
    result = wait_job(state)
    assert result["operation"]["status"] == "error" and result["operation"]["error"]
    assert result["data"]["exists"]


# FR-1090 AC-489 AC-492: progress remains readable and jobs stay pinned when the viewed repo changes.
def test_running_job_is_pinned_and_rejects_duplicate(data_server, data_repo, tmp_path, monkeypatch):
    state, url = data_server
    entered, release = threading.Event(), threading.Event()
    sync = managed_data.sync

    def blocked(root, progress):
        progress({"phase": "files", "completed": 1, "total": 3})
        entered.set()
        assert release.wait(10)
        return sync(root, progress)

    monkeypatch.setattr(managed_data, "sync", blocked)
    try:
        request(url, "/api/data/sync", {"repo": str(data_repo)})
        assert entered.wait(5)
        assert request(url, "/api/data")["operation"]["progress"]["completed"] == 1
        with pytest.raises(urllib.error.HTTPError) as error:
            request(url, "/api/data/sync", {"repo": str(data_repo)})
        assert error.value.code == 409
        other = init_repo(tmp_path / "other")
        state.set_root(other)
        assert request(url, "/api/data")["operation"] == {}
    finally:
        release.set()
        state.set_root(data_repo)
        assert wait_job(state)["operation"]["status"] == "done"
    assert (data_repo / managed_data.RELATIVE_PATH).exists()
    assert not (other / managed_data.DIRECTORY).exists()
