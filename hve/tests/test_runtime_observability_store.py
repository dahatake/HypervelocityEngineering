"""FR-RTO-03 / FR-RTO-04 / FR-RTO-06 / NFR-RTO-03: run-scoped JSONL 記録と保存 allowlist。

RED 先行。`RuntimeEventRecorder` / `sanitize_event` は本テスト作成時点で未実装。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from hve import runtime_observability as rto


def _recorder(tmp_path: Path, **kwargs):
    return rto.RuntimeEventRecorder(tmp_path, repo_root=tmp_path, **kwargs)


class TestOutputLocation:
    """FR-RTO-03: 出力先とファイル名。"""

    def test_writes_pid_scoped_file_under_observability(self, tmp_path: Path) -> None:
        rec = _recorder(tmp_path)
        rec.record({"kind": "step_status", "step": "1", "status": "running"})
        rec.close()

        expected = tmp_path / "observability" / f"events-{rec.pid}.jsonl"
        assert expected.is_file()
        assert rec.path == expected

    def test_disabled_when_work_root_is_none(self) -> None:
        rec = rto.RuntimeEventRecorder(None)
        assert rec.enabled is False
        assert rec.record({"kind": "step_status", "step": "1", "status": "running"}) is False
        assert rec.path is None
        rec.close()

    def test_disabled_for_dry_run(self, tmp_path: Path) -> None:
        rec = _recorder(tmp_path, dry_run=True)
        assert rec.enabled is False
        assert rec.record({"kind": "step_status", "step": "1"}) is False
        assert not (tmp_path / "observability").exists()
        rec.close()


class TestFileFormat:
    """FR-RTO-03: UTF-8 / LF / BOM なしの 1 行 1 JSON。"""

    def test_lf_only_and_no_bom(self, tmp_path: Path) -> None:
        rec = _recorder(tmp_path)
        rec.record({"kind": "step_status", "step": "1", "status": "running"})
        rec.record({"kind": "step_status", "step": "1", "status": "done"})
        rec.close()

        raw = rec.path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert b"\r\n" not in raw
        assert raw.count(b"\n") == 2

    def test_each_line_is_one_json_object(self, tmp_path: Path) -> None:
        rec = _recorder(tmp_path)
        rec.record({"kind": "skill_invoked", "step": "1", "name": "コードクエリ"})
        rec.close()

        line = rec.path.read_text(encoding="utf-8").splitlines()[0]
        assert json.loads(line)["name"] == "コードクエリ"

    def test_read_events_skips_broken_lines(self, tmp_path: Path) -> None:
        rec = _recorder(tmp_path)
        rec.record({"kind": "step_status", "step": "1", "status": "running"})
        rec.close()
        with rec.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write("{broken\n")

        events = rto.read_events(tmp_path)
        assert [e["kind"] for e in events] == ["step_status"]


class TestConcurrency:
    """FR-RTO-03: 同一プロセス内の追記を直列化する。"""

    def test_parallel_appends_do_not_corrupt_lines(self, tmp_path: Path) -> None:
        rec = _recorder(tmp_path)

        def worker(step: int) -> None:
            for _ in range(50):
                rec.record({"kind": "tool_invoked", "step": str(step), "tool_name": "view"})

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        rec.close()

        lines = rec.path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 200
        assert all(json.loads(line)["kind"] == "tool_invoked" for line in lines)


class TestSizeCap:
    """FR-RTO-03: 上限到達で追記を停止し 1 回だけ警告する。"""

    def test_stops_and_warns_once(self, tmp_path: Path) -> None:
        warnings: list = []
        rec = _recorder(tmp_path, max_bytes=200, warn=warnings.append)
        for _ in range(50):
            rec.record({"kind": "tool_invoked", "step": "1", "tool_name": "view"})
        rec.close()

        size = rec.path.stat().st_size
        assert size <= 400
        assert len(warnings) == 1


class TestSanitization:
    """FR-RTO-04: 保存は allowlist、秘密情報は保存しない。"""

    def test_forbidden_keys_are_dropped(self, tmp_path: Path) -> None:
        payload = {
            "kind": "tool_invoked",
            "step": "1",
            "tool_name": "bash",
            "arguments": {"command": "echo secret"},
            "prompt": "system prompt body",
            "content": "assistant response body",
            "env": {"GH_TOKEN": "ghp_xxx"},
            "payload_json": "{...raw sdk...}",
        }
        clean = rto.sanitize_event(payload, repo_root=tmp_path)
        assert clean is not None
        assert clean["tool_name"] == "bash"
        for forbidden in ("arguments", "prompt", "content", "env", "payload_json"):
            assert forbidden not in clean

    def test_diagnostic_kinds_are_not_persisted(self, tmp_path: Path) -> None:
        for kind in ("assistant_usage_raw", "debug_env", "assistant_usage_raw_err"):
            assert rto.sanitize_event({"kind": kind, "step": "1"}, repo_root=tmp_path) is None

    def test_paths_are_stored_repo_relative(self, tmp_path: Path) -> None:
        target = tmp_path / "src" / "app.py"
        clean = rto.sanitize_event(
            {"kind": "file_io", "step": "1", "mode": "write", "path": str(target)},
            repo_root=tmp_path,
        )
        assert clean is not None
        assert clean["path"] == "src/app.py"

    def test_paths_outside_repo_root_are_dropped(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "other" / "secret.txt"
        clean = rto.sanitize_event(
            {"kind": "file_io", "step": "1", "mode": "write", "path": str(outside)},
            repo_root=tmp_path,
        )
        assert clean is not None
        assert "path" not in clean

    def test_relative_path_traversal_is_dropped(self, tmp_path: Path) -> None:
        clean = rto.sanitize_event(
            {"kind": "file_io", "step": "1", "mode": "write", "path": "src/../../etc/passwd"},
            repo_root=tmp_path,
        )
        assert clean is not None
        assert "path" not in clean

    def test_relative_path_is_normalized(self, tmp_path: Path) -> None:
        clean = rto.sanitize_event(
            {"kind": "file_io", "step": "1", "mode": "write", "path": "src/./sub/../app.py"},
            repo_root=tmp_path,
        )
        assert clean is not None
        assert clean["path"] == "src/app.py"

    @pytest.mark.parametrize(
        "value",
        [
            "$p",
            "$p))",
            "`$p))",
            "docs/architectural-requirements-app-006.md')",
        ],
    )
    def test_shell_expression_tokens_are_dropped(self, tmp_path: Path, value: str) -> None:
        """FR-RTO-04: シェルの変数・式・末尾コード断片はパスとして保存しない。"""
        clean = rto.sanitize_event(
            {"kind": "file_io", "step": "2/APP-006", "mode": "read", "path": value},
            repo_root=tmp_path,
        )
        assert clean is not None
        assert "path" not in clean

    def test_recorder_persists_only_sanitized_payload(self, tmp_path: Path) -> None:
        rec = _recorder(tmp_path)
        rec.record({"kind": "tool_invoked", "step": "1", "tool_name": "bash", "arguments": {"c": "x"}})
        rec.close()

        stored = json.loads(rec.path.read_text(encoding="utf-8").splitlines()[0])
        assert "arguments" not in stored
        assert stored["tool_name"] == "bash"


class TestFailureIsolation:
    """NFR-RTO-03: 記録の失敗が実行を落とさない。"""

    def test_write_error_is_swallowed_and_disables_recorder(self, tmp_path: Path) -> None:
        rec = _recorder(tmp_path)
        rec.record({"kind": "step_status", "step": "1", "status": "running"})
        rec._handle.close()  # 外部要因でハンドルが閉じた状況を模す

        assert rec.record({"kind": "step_status", "step": "1", "status": "done"}) is False
        rec.close()

    def test_close_is_idempotent(self, tmp_path: Path) -> None:
        rec = _recorder(tmp_path)
        rec.record({"kind": "step_status", "step": "1", "status": "running"})
        rec.close()
        rec.close()
        assert rec.record({"kind": "step_status", "step": "1"}) is False

    def test_context_manager_closes_handle(self, tmp_path: Path) -> None:
        with _recorder(tmp_path) as rec:
            rec.record({"kind": "step_status", "step": "1", "status": "running"})
            path = rec.path
        assert path.is_file()
        # FR-RTO-06: クローズ後はハンドルを保持しない（GUI の purge / archive と競合させない）。
        assert rec._handle is None
