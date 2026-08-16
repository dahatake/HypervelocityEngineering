"""test_qa_akm_model_selection.py — FR-QA-04 の RED テスト。

QA 起点 AKM（FR-QA-03）の子実行が使うモデル / reasoning effort / context tier を、
メインタスクの実行品質設定から独立に選択できることを検証する。

実装前は `SDKConfig.akm_model` 等が存在しないため全件 RED となる。
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import MODEL_AUTO_VALUE, SDKConfig


def _make_fake_process(finish_event=None, returncode=0, pid=9999):
    """threading.Event ベースの fake Popen（real sleep 不使用）。"""
    if finish_event is None:
        finish_event = threading.Event()
        finish_event.set()

    class _FakeProcess:
        def __init__(self):
            self.pid = pid
            self._finish = finish_event
            self._returncode = returncode

        def wait(self, timeout=None):
            self._finish.wait(timeout=timeout)
            return self._returncode

        @property
        def returncode(self):
            return self._returncode if self._finish.is_set() else None

        def terminate(self):
            self._finish.set()

        def kill(self):
            self._finish.set()

    return _FakeProcess()


def _make_repo_with_qa() -> Path:
    repo = Path(tempfile.mkdtemp())
    path = repo / "qa" / "Issue-1-questionnaire-answered-abc12345.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# 回答済み QA\n", encoding="utf-8")
    return repo


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
    return [str(a) for a in captured[0]]


def _value_after(argv: list, flag: str):
    return argv[argv.index(flag) + 1] if flag in argv else None


class TestAkmExecutionQualityConfigDefaults(unittest.TestCase):
    """FR-QA-04: SDKConfig の AKM 専用フィールドと継承規則。"""

    def test_akm_fields_default_to_none(self):
        cfg = SDKConfig()
        self.assertIsNone(cfg.akm_model)
        self.assertIsNone(cfg.akm_reasoning_effort)
        self.assertIsNone(cfg.akm_context_tier)

    def test_get_akm_model_inherits_main_model(self):
        cfg = SDKConfig(model="gpt-5.4")
        self.assertEqual(cfg.get_akm_model(), "gpt-5.4")

    def test_get_akm_model_returns_explicit_value(self):
        cfg = SDKConfig(model="gpt-5.4", akm_model="claude-opus-4.6")
        self.assertEqual(cfg.get_akm_model(), "claude-opus-4.6")

    def test_akm_model_accepts_auto_sentinel(self):
        cfg = SDKConfig(model="gpt-5.4", akm_model=MODEL_AUTO_VALUE)
        self.assertEqual(cfg.get_akm_model(), MODEL_AUTO_VALUE)

    def test_unsupported_akm_model_falls_back_to_auto_with_warning(self):
        """`_normalize_model_with_warning` と同一規則で検証される。"""
        with self.assertWarns(UserWarning):
            cfg = SDKConfig(model="gpt-5.4", akm_model="claude-sonnet-4.6")
        self.assertEqual(cfg.akm_model, MODEL_AUTO_VALUE)

    def test_from_env_does_not_introduce_akm_env_vars(self):
        """`reasoning_effort` / `context_tier` に環境変数経路が無いため新設しない。"""
        saved = os.environ.copy()
        try:
            os.environ["AKM_MODEL"] = "claude-opus-4.6"
            os.environ["AKM_REASONING_EFFORT"] = "high"
            os.environ["AKM_CONTEXT_TIER"] = "long_context"
            cfg = SDKConfig.from_env()
            self.assertIsNone(cfg.akm_model)
            self.assertIsNone(cfg.akm_reasoning_effort)
            self.assertIsNone(cfg.akm_context_tier)
        finally:
            os.environ.clear()
            os.environ.update(saved)


class TestBuildArgvAkmOverrides(unittest.TestCase):
    """FR-QA-04: `_build_argv` が AKM 専用値を優先し、未指定はメインを継承する。"""

    def _base_config(self, **overrides) -> SDKConfig:
        defaults = dict(
            model="gpt-5.4",
            reasoning_effort="high",
            context_tier="long_context",
            timeout_seconds=7200.0,
        )
        defaults.update(overrides)
        return SDKConfig(dry_run=True, quiet=True, **defaults)

    def test_all_akm_values_override_main(self):
        argv = _capture_argv(self._base_config(
            akm_model="claude-opus-4.6",
            akm_reasoning_effort="medium",
            akm_context_tier="default",
        ))
        self.assertEqual(_value_after(argv, "--model"), "claude-opus-4.6")
        self.assertEqual(_value_after(argv, "--reasoning-effort"), "medium")
        self.assertEqual(_value_after(argv, "--context-tier"), "default")

    def test_only_akm_model_set_leaves_other_flags_inherited(self):
        argv = _capture_argv(self._base_config(akm_model="claude-opus-4.6"))
        self.assertEqual(_value_after(argv, "--model"), "claude-opus-4.6")
        self.assertEqual(_value_after(argv, "--reasoning-effort"), "high")
        self.assertEqual(_value_after(argv, "--context-tier"), "long_context")

    def test_only_akm_reasoning_effort_set_leaves_model_inherited(self):
        argv = _capture_argv(self._base_config(akm_reasoning_effort="low"))
        self.assertEqual(_value_after(argv, "--model"), "gpt-5.4")
        self.assertEqual(_value_after(argv, "--reasoning-effort"), "low")

    def test_only_akm_context_tier_set_leaves_model_inherited(self):
        argv = _capture_argv(self._base_config(akm_context_tier="default"))
        self.assertEqual(_value_after(argv, "--model"), "gpt-5.4")
        self.assertEqual(_value_after(argv, "--context-tier"), "default")

    def test_no_akm_values_produces_identical_argv(self):
        """後方互換: 3 項目未指定ならメイン値がそのまま引き継がれ、`--akm-*` は漏れない。"""
        argv = _capture_argv(self._base_config())
        self.assertEqual(_value_after(argv, "--model"), "gpt-5.4")
        self.assertEqual(_value_after(argv, "--reasoning-effort"), "high")
        self.assertEqual(_value_after(argv, "--context-tier"), "long_context")
        leaked = [a for a in argv if a.startswith("--akm-")]
        self.assertEqual(leaked, [], f"AKM 専用フラグが子へ漏れています: {leaked}")

    def test_akm_flags_are_never_forwarded_to_the_child(self):
        """AKM 専用値を指定しても、子はメイン用フラグだけを受け取る。"""
        argv = _capture_argv(self._base_config(
            akm_model="claude-opus-4.6",
            akm_reasoning_effort="medium",
            akm_context_tier="default",
        ))
        leaked = [a for a in argv if a.startswith("--akm-")]
        self.assertEqual(leaked, [], f"AKM 専用フラグが子へ漏れています: {leaked}")
        # 子は `-w akm` の明示実行であり、そこへ再び AKM 専用設定を渡すと
        # 孫 AKM へ伝播する余地が生まれるため、フラグ名ごと存在しないことを固定する。
        self.assertEqual(argv.count("--model"), 1)
        self.assertEqual(argv.count("--reasoning-effort"), 1)
        self.assertEqual(argv.count("--context-tier"), 1)

    def test_akm_model_auto_is_forwarded_verbatim(self):
        """CLI の `--model` は "Auto" 文字列を受理するため、そのまま渡す。"""
        argv = _capture_argv(self._base_config(akm_model=MODEL_AUTO_VALUE))
        self.assertEqual(_value_after(argv, "--model"), MODEL_AUTO_VALUE)


class TestAkmSettingsDoNotLeakToMainSessions(unittest.TestCase):
    """FR-QA-04: AKM 専用値がメイン / review / QA のセッション生成へ漏れない。"""

    def _apply(self, kind: str, cfg: SDKConfig) -> dict:
        from orchestrator import _apply_reasoning_effort

        session_opts: dict = {}
        _apply_reasoning_effort(session_opts, cfg, kind=kind)
        return session_opts

    def test_akm_reasoning_effort_is_ignored_by_main_review_qa(self):
        cfg = SDKConfig(
            model="gpt-5.4",
            reasoning_effort=None,
            review_reasoning_effort=None,
            qa_reasoning_effort=None,
            akm_reasoning_effort="medium",
        )
        for kind in ("main", "review", "qa"):
            with self.subTest(kind=kind):
                self.assertNotIn("reasoning_effort", self._apply(kind, cfg))

    def test_akm_model_does_not_change_review_and_qa_model_resolution(self):
        cfg = SDKConfig(model="gpt-5.4", akm_model="claude-opus-4.6")
        self.assertEqual(cfg.get_review_model(), "gpt-5.4")
        self.assertEqual(cfg.get_qa_model(), "gpt-5.4")

    def test_akm_context_tier_does_not_change_main_context_tier(self):
        cfg = SDKConfig(context_tier="long_context", akm_context_tier="default")
        self.assertEqual(cfg.context_tier, "long_context")


if __name__ == "__main__":
    unittest.main()
