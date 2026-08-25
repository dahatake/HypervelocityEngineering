"""test_qa_akm_child_logging.py — FR-QA-07 の RED テスト。

QA 起点 AKM 子実行の標準出力・標準エラーを子 run ディレクトリ配下へ保存し、
結果へ保存先パスを含め、親実行の失敗報告へ `returncode` と保存先を出すことを検証する。

実装前は `stdout` / `stderr` が `subprocess.DEVNULL` へ捨てられ、結果 dict に
`log_path` が無いため RED となる。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig


class _RecordingProcessFactory:
    """Popen を置換し、stdout / stderr へ渡された値を記録する。"""

    def __init__(self, *, returncodes: List[int] | None = None) -> None:
        self.stdout_args: List[Any] = []
        self.stderr_args: List[Any] = []
        self.argvs: List[List[str]] = []
        self._returncodes = list(returncodes or [])
        self._lock = threading.Lock()
        self.blocked = threading.Event()
        self.blocked.set()
        self.started = [threading.Event() for _ in range(8)]

    def __call__(self, *args, **kwargs):
        with self._lock:
            index = len(self.argvs)
            self.argvs.append([str(a) for a in (args[0] if args else kwargs.get("args"))])
            self.stdout_args.append(kwargs.get("stdout"))
            self.stderr_args.append(kwargs.get("stderr"))
        returncode = self._returncodes[index] if index < len(self._returncodes) else 0
        gate = self.blocked
        if index < len(self.started):
            self.started[index].set()

        class _FakeProcess:
            pid = 6000 + index

            def wait(self, timeout=None):
                gate.wait(timeout=timeout)
                return returncode

            @property
            def returncode(self):
                return returncode if gate.is_set() else None

            def terminate(self):
                gate.set()

            def kill(self):
                gate.set()

        return _FakeProcess()


def _make_repo(*relative_paths: str) -> Path:
    repo = Path(tempfile.mkdtemp())
    for relative in relative_paths:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# 回答済み QA\n", encoding="utf-8")
    return repo


def _make_config() -> SDKConfig:
    return SDKConfig(dry_run=True, quiet=True, model="gpt-5.4")


def _run_once(
    factory: _RecordingProcessFactory,
    *,
    files: List[str],
) -> tuple[Path, List[Dict[str, Any]]]:
    from qa_akm_dispatch import QaAkmCoordinator

    repo = _make_repo(*files)
    coordinator = QaAkmCoordinator(
        _make_config(), repo_root=repo, popen_factory=factory,
    )
    for relative in files:
        coordinator.submit(Path(relative))
    results = coordinator.drain()
    coordinator.cancel()
    return repo, results


class TestQaAkmChildStdioLog(unittest.TestCase):
    """FR-QA-07: 子の stdout / stderr を保存し、結果へ保存先を含める。"""

    def test_child_stdout_is_redirected_to_file(self) -> None:
        factory = _RecordingProcessFactory()
        _run_once(factory, files=["qa/a.md"])
        stdout_arg = factory.stdout_args[0]
        self.assertIsNot(stdout_arg, subprocess.DEVNULL)
        self.assertTrue(hasattr(stdout_arg, "fileno"))
        self.assertEqual(str(getattr(stdout_arg, "encoding", "")).lower(), "utf-8")
        self.assertEqual(getattr(stdout_arg, "errors", None), "replace")
        self.assertIs(factory.stderr_args[0], subprocess.STDOUT)

    def test_log_file_is_created_under_child_run_dir(self) -> None:
        factory = _RecordingProcessFactory()
        repo, _ = _run_once(factory, files=["qa/a.md"])
        logs = sorted((repo / "work" / "run").glob("qa-akm-*/child-stdio.log"))
        self.assertEqual(len(logs), 1)

    def test_result_contains_repo_relative_log_path(self) -> None:
        factory = _RecordingProcessFactory()
        repo, results = _run_once(factory, files=["qa/a.md"])
        self.assertEqual(len(results), 1)
        log_path = str(results[0].get("log_path", ""))
        self.assertTrue(log_path, "結果へ log_path が含まれていない")
        self.assertFalse(Path(log_path).is_absolute())
        self.assertTrue((repo / log_path).is_file())

    def test_batch_results_share_one_log_path(self) -> None:
        from qa_akm_dispatch import QaAkmCoordinator

        factory = _RecordingProcessFactory()
        factory.blocked = threading.Event()  # 1 件目を保持して滞留を作る
        repo = _make_repo("qa/a.md", "qa/b.md", "qa/c.md")
        coordinator = QaAkmCoordinator(
            _make_config(), repo_root=repo, popen_factory=factory,
        )
        coordinator.submit(Path("qa/a.md"))
        self.assertTrue(factory.started[0].wait(timeout=5.0), "1 件目の子が起動しない")
        coordinator.submit(Path("qa/b.md"))
        coordinator.submit(Path("qa/c.md"))
        factory.blocked.set()
        results = coordinator.drain()
        coordinator.cancel()

        self.assertEqual(len(results), 3)
        self.assertEqual(len(factory.argvs), 2, "滞留した 2 件は 1 回の子実行へまとまる")
        by_file = {str(item["file"]): str(item["log_path"]) for item in results}
        self.assertEqual(
            by_file[str(Path("qa/b.md"))], by_file[str(Path("qa/c.md"))],
        )
        self.assertNotEqual(
            by_file[str(Path("qa/a.md"))], by_file[str(Path("qa/b.md"))],
        )

    def test_non_utf8_child_output_does_not_raise(self) -> None:
        factory = _RecordingProcessFactory()
        repo, results = _run_once(factory, files=["qa/a.md"])
        log_path = repo / str(results[0]["log_path"])
        # 子は raw byte を fd へ書く。親は decode しないため例外にならない。
        with open(log_path, "ab") as raw:
            raw.write(b"\x81\x40 cp932 fragment\n")
        text = log_path.read_text(encoding="utf-8", errors="replace")
        self.assertIn("cp932 fragment", text)


class TestDrainQaAkmFailureReport(unittest.TestCase):
    """FR-QA-07: 失敗報告へ returncode / log_path / blocked 導線を含める。"""

    @staticmethod
    def _format(failed: List[Dict[str, Any]], reason: str = "DAG 完了後") -> str:
        import orchestrator

        return orchestrator._format_qa_akm_failure_warning(failed, reason)

    def test_warning_includes_returncode_and_log_path(self) -> None:
        message = self._format([
            {"file": "qa/a.md", "returncode": 1, "log_path": "work/run/qa-akm-x/child-stdio.log"},
        ])
        self.assertIn("returncode=1", message)
        self.assertIn("work/run/qa-akm-x/child-stdio.log", message)

    def test_warning_groups_batch_failures_by_log_path(self) -> None:
        failed = [
            {"file": f"qa/{name}.md", "returncode": 2, "log_path": "work/run/qa-akm-y/child-stdio.log"}
            for name in ("a", "b", "c")
        ]
        message = self._format(failed)
        self.assertEqual(message.count("work/run/qa-akm-y/child-stdio.log"), 1)
        self.assertIn("3", message)

    def test_warning_includes_dirty_source_hint(self) -> None:
        message = self._format([
            {"file": "qa/a.md", "returncode": 1, "log_path": "work/run/qa-akm-x/child-stdio.log"},
        ])
        self.assertIn("未コミット", message)

    def test_warning_does_not_inline_child_log_body(self) -> None:
        message = self._format([
            {
                "file": "qa/a.md",
                "returncode": 1,
                "log_path": "work/run/qa-akm-x/child-stdio.log",
                "stdout": "秘匿すべき子ログ本文",
            },
        ])
        self.assertNotIn("秘匿すべき子ログ本文", message)

    def test_warning_without_log_path_is_still_reported(self) -> None:
        message = self._format([{"file": "qa/a.md", "returncode": -1}])
        self.assertIn("returncode=-1", message)
        self.assertIn("1 件", message)


class TestQaAkmSubmitDirtySourcePrecheck(unittest.TestCase):
    """FR-QA-07: 登録時点で HVE ソースが dirty なら子を起動せず即時警告する。"""

    def _coordinator(self, factory, *, dirty, warnings):
        from qa_akm_dispatch import QaAkmCoordinator

        repo = _make_repo("qa/a.md")
        coordinator = QaAkmCoordinator(
            _make_config(),
            repo_root=repo,
            popen_factory=factory,
            warn=warnings.append,
            dirty_source_probe=lambda: list(dirty),
        )
        return repo, coordinator

    def test_dirty_submit_does_not_start_child(self) -> None:
        factory = _RecordingProcessFactory()
        warnings: List[str] = []
        _, coordinator = self._coordinator(
            factory, dirty=["hve/runner.py", "hve/workiq.py"], warnings=warnings,
        )
        coordinator.submit(Path("qa/a.md"))
        results = coordinator.drain()
        coordinator.cancel()
        self.assertEqual(factory.argvs, [])
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].get("skipped"))
        self.assertEqual(results[0].get("reason"), "hve-source-dirty")

    def test_dirty_submit_warns_immediately(self) -> None:
        factory = _RecordingProcessFactory()
        warnings: List[str] = []
        _, coordinator = self._coordinator(
            factory, dirty=["hve/runner.py"], warnings=warnings,
        )
        coordinator.submit(Path("qa/a.md"))
        coordinator.cancel()
        self.assertEqual(len(warnings), 1)
        self.assertIn("qa/a.md", warnings[0].replace("\\", "/"))
        self.assertIn("未コミット", warnings[0])

    def test_clean_submit_starts_child(self) -> None:
        factory = _RecordingProcessFactory()
        warnings: List[str] = []
        _, coordinator = self._coordinator(factory, dirty=[], warnings=warnings)
        coordinator.submit(Path("qa/a.md"))
        results = coordinator.drain()
        coordinator.cancel()
        self.assertEqual(len(factory.argvs), 1)
        self.assertEqual(warnings, [])
        self.assertFalse(results[0].get("skipped", False))

    def test_skipped_results_are_reported_apart_from_failures(self) -> None:
        import orchestrator

        message = orchestrator._format_qa_akm_skip_warning(
            [{"file": "qa/a.md", "returncode": -1, "skipped": True,
              "reason": "hve-source-dirty"}],
            "DAG 完了後",
        )
        self.assertIn("スキップ", message)
        self.assertIn("未コミット", message)
        self.assertNotIn("失敗しました", message)

    def test_default_probe_is_the_shared_dirty_source_resolver(self) -> None:
        import qa_akm_dispatch

        source = Path(qa_akm_dispatch.__file__).read_text(encoding="utf-8")
        self.assertIn("_git_dirty_hve_source_paths", source)


if __name__ == "__main__":
    unittest.main()
