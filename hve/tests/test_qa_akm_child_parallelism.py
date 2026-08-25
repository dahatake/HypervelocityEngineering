"""test_qa_akm_child_parallelism.py — FR-QA-03 / FR-DAG-03 の契約テスト。

QA 起点 AKM の子実行は、AKM が `WorkflowDef.max_parallel` で宣言する並列度
（D01〜D21 の fan-out 21 件）で走る。宣言値は FR-DAG-03 の解決順序が適用するため、
子 argv 側で `--max-parallel` を固定してはならない（同一ルールの二重実装を禁じる
FR-MAINT-07）。

解決順序そのものは hve/tests/test_workflow_max_parallel_resolution.py が担保する。
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig
from workflow_registry import get_workflow


def _make_fake_process(returncode: int = 0):
    """即完了する fake Popen（real sleep 不使用）。"""
    finish = threading.Event()
    finish.set()

    class _FakeProcess:
        pid = 9001

        def wait(self, timeout=None):
            finish.wait(timeout=timeout)
            return returncode

        @property
        def returncode(self):
            return returncode

        def terminate(self):
            finish.set()

        def kill(self):
            finish.set()

    return _FakeProcess()


def _make_repo_with_qa() -> Path:
    repo = Path(tempfile.mkdtemp())
    path = repo / "qa" / "Issue-1-questionnaire-answered-abc12345.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# 回答済み QA\n", encoding="utf-8")
    return repo


def _make_config(**overrides) -> SDKConfig:
    defaults = dict(
        dry_run=True,
        quiet=True,
        model="gpt-5.4",
        reasoning_effort="high",
        context_tier="long_context",
        timeout_seconds=7200.0,
        step_timeout_seconds=3600.0,
    )
    defaults.update(overrides)
    return SDKConfig(**defaults)


def _capture_argv(config: SDKConfig) -> list:
    """QaAkmCoordinator が子プロセスへ渡す argv を取得する。"""
    from qa_akm_dispatch import QaAkmCoordinator

    captured: list = []

    def popen_factory(*args, **kwargs):
        captured.append(args[0] if args else kwargs.get("args"))
        return _make_fake_process()

    repo = _make_repo_with_qa()
    coordinator = QaAkmCoordinator(
        config, repo_root=repo, popen_factory=popen_factory,
    )
    coordinator.submit(Path("qa/Issue-1-questionnaire-answered-abc12345.md"))
    coordinator.drain()
    coordinator.cancel()
    return [str(a) for a in captured[0]]


class TestChildFanoutParallelism(unittest.TestCase):
    """FR-QA-03 / FR-DAG-03: 子 AKM 実行の fan-out 並列度。"""

    def test_akm_declares_max_parallel(self):
        """前提: AKM は Workflow 定義で並列上限を宣言している。"""
        self.assertIsNotNone(get_workflow("akm").max_parallel)

    def test_child_argv_does_not_pin_max_parallel(self):
        """固定すると FR-DAG-03 の宣言優先と二重管理になる。"""
        for parent_value in (1, 8, 15, 40):
            with self.subTest(parent=parent_value):
                argv = _capture_argv(_make_config(max_parallel=parent_value))
                self.assertNotIn("--max-parallel", argv)

    def test_declaration_governs_the_child_run(self):
        """子は `--workflow akm` なので FR-DAG-03 が AKM の宣言値を適用する。"""
        from orchestrator import _resolve_max_parallel

        argv = _capture_argv(_make_config())
        self.assertEqual(argv[argv.index("--workflow") + 1], "akm")
        value, source = _resolve_max_parallel(
            workflow=get_workflow("akm"),
            config_max_parallel=SDKConfig().max_parallel,
            ard_force_serial=False,
        )
        self.assertEqual(value, get_workflow("akm").max_parallel)
        self.assertEqual(source, "workflow")


if __name__ == "__main__":
    unittest.main()
