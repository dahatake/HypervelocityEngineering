"""test_qa_akm_batching.py — FR-QA-03（v2.31 改訂）の RED テスト。

実行開始時点でキューに滞留している複数の登録を 1 回の AKM 子実行へまとめ、
`target_files` へ当該バッチの全ファイルを与え、実行結果を登録件数分
（ファイル単位）で報告することを検証する。あわせて、まとめても同時に
2 つ以上の AKM 子プロセスを起動しないことを固定する。

実装前は 1 登録 = 1 子実行のため、バッチ化を要求するケースが RED となる。
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Dict, List, Sequence

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig


class _FakeProcessFactory:
    """Popen を置換し、起動 argv・同時実行数・完了タイミングを制御する。

    `block_indices` に含まれる呼び出しは `release()` されるまで `wait()` が返らない。
    Event は事前に確保するため、テスト側はポーリングせず決定論的に待てる。
    """

    CAPACITY = 8

    def __init__(
        self,
        *,
        block_indices: Sequence[int] = (),
        returncodes: Sequence[int] = (),
    ) -> None:
        self.argvs: List[List[str]] = []
        self.max_concurrent = 0
        self._blocked = set(block_indices)
        self._returncodes = list(returncodes)
        self._lock = threading.Lock()
        self._concurrent = 0
        self._started = [threading.Event() for _ in range(self.CAPACITY)]
        self._gates = [threading.Event() for _ in range(self.CAPACITY)]
        for index in range(self.CAPACITY):
            if index not in self._blocked:
                self._gates[index].set()

    def __call__(self, *args, **kwargs):
        argv = [str(a) for a in (args[0] if args else kwargs.get("args"))]
        with self._lock:
            index = len(self.argvs)
            self.argvs.append(argv)
            self._concurrent += 1
            self.max_concurrent = max(self.max_concurrent, self._concurrent)
        gate = self._gates[index]
        returncode = (
            self._returncodes[index] if index < len(self._returncodes) else 0
        )
        self._started[index].set()
        outer = self

        class _FakeProcess:
            pid = 5000 + index

            def wait(self, timeout=None):
                gate.wait(timeout=timeout)
                with outer._lock:
                    outer._concurrent -= 1
                return returncode

            @property
            def returncode(self):
                return returncode if gate.is_set() else None

            def terminate(self):
                gate.set()

            def kill(self):
                gate.set()

        return _FakeProcess()

    def wait_started(self, index: int, timeout: float = 5.0) -> bool:
        return self._started[index].wait(timeout=timeout)

    def release(self, index: int) -> None:
        self._gates[index].set()

    def target_files(self, index: int) -> List[str]:
        argv = self.argvs[index]
        start = argv.index("--target-files") + 1
        collected: List[str] = []
        for token in argv[start:]:
            if token.startswith("--"):
                break
            collected.append(token)
        return collected


def _make_repo(*relative_paths: str) -> Path:
    repo = Path(tempfile.mkdtemp())
    for relative in relative_paths:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# 回答済み QA\n", encoding="utf-8")
    return repo


def _make_config() -> SDKConfig:
    return SDKConfig(
        dry_run=True,
        quiet=True,
        model="gpt-5.4",
        reasoning_effort="high",
        context_tier="long_context",
        timeout_seconds=7200.0,
        step_timeout_seconds=3600.0,
    )


def _by_file(results: List[Dict[str, object]]) -> Dict[str, int]:
    return {str(item["file"]): int(item["returncode"]) for item in results}


class TestQaAkmBatching(unittest.TestCase):
    """FR-QA-03: 滞留した登録を 1 回の子実行へまとめる。"""

    def _run_batch_scenario(self, factory: _FakeProcessFactory):
        """1 件目の子を保持したまま 2 件を追加投入し、滞留を作る。"""
        from qa_akm_dispatch import QaAkmCoordinator

        repo = _make_repo("qa/a.md", "qa/b.md", "qa/c.md")
        coordinator = QaAkmCoordinator(
            _make_config(), repo_root=repo, popen_factory=factory,
        )
        coordinator.submit(Path("qa/a.md"))
        self.assertTrue(factory.wait_started(0), "1 件目の子が起動しない")
        coordinator.submit(Path("qa/b.md"))
        coordinator.submit(Path("qa/c.md"))
        factory.release(0)
        results = coordinator.drain()
        coordinator.cancel()
        return results

    def test_pending_submits_are_batched_into_single_child(self):
        factory = _FakeProcessFactory(block_indices=(0,))
        self._run_batch_scenario(factory)
        self.assertEqual(
            len(factory.argvs), 2,
            "滞留した 2 件は 1 回の子実行へまとまる必要がある",
        )

    def test_batch_argv_lists_all_target_files_in_fifo_order(self):
        factory = _FakeProcessFactory(block_indices=(0,))
        self._run_batch_scenario(factory)
        self.assertEqual(
            factory.target_files(1),
            [str(Path("qa/b.md")), str(Path("qa/c.md"))],
        )

    def test_drain_returns_one_result_per_registration(self):
        factory = _FakeProcessFactory(block_indices=(0,))
        results = self._run_batch_scenario(factory)
        self.assertEqual(
            sorted(_by_file(results)),
            sorted(str(Path(p)) for p in ("qa/a.md", "qa/b.md", "qa/c.md")),
        )

    def test_no_concurrent_child_processes(self):
        factory = _FakeProcessFactory(block_indices=(0,))
        self._run_batch_scenario(factory)
        self.assertLessEqual(
            factory.max_concurrent, 1,
            "バッチ化しても子プロセスの同時起動は 1 を超えてはならない",
        )

    def test_batch_failure_is_reported_for_every_file(self):
        factory = _FakeProcessFactory(block_indices=(0,), returncodes=(0, 3))
        results = self._run_batch_scenario(factory)
        mapping = _by_file(results)
        self.assertEqual(mapping[str(Path("qa/a.md"))], 0)
        self.assertEqual(mapping[str(Path("qa/b.md"))], 3)
        self.assertEqual(mapping[str(Path("qa/c.md"))], 3)

    def test_single_submit_is_not_batched(self):
        from qa_akm_dispatch import QaAkmCoordinator

        factory = _FakeProcessFactory()
        repo = _make_repo("qa/only.md")
        coordinator = QaAkmCoordinator(
            _make_config(), repo_root=repo, popen_factory=factory,
        )
        coordinator.submit(Path("qa/only.md"))
        results = coordinator.drain()
        coordinator.cancel()

        self.assertEqual(len(factory.argvs), 1)
        self.assertEqual(factory.target_files(0), [str(Path("qa/only.md"))])
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
