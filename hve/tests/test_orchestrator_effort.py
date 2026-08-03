"""test_orchestrator_effort.py — `_apply_reasoning_effort` の挙動検証。

ユーザー指定 reasoning_effort のみを session_opts に伝播し、未指定時は
何もセットしないことを検証する（Auto モデル時もサーバ側に委譲）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from hve.orchestrator import _apply_reasoning_effort
from hve.config import MODEL_AUTO_VALUE


@dataclass
class _FakeCfg:
    model: str = MODEL_AUTO_VALUE
    reasoning_effort: Optional[str] = None
    review_reasoning_effort: Optional[str] = None
    qa_reasoning_effort: Optional[str] = None


class TestApplyReasoningEffortMain:
    def test_user_specified_value_is_applied(self):
        """ユーザー指定値が session_opts に伝播する（Auto モデルでも明示モデルでも）。"""
        cfg = _FakeCfg(model=MODEL_AUTO_VALUE, reasoning_effort="low")
        opts: dict = {}
        _apply_reasoning_effort(opts, cfg, kind="main")
        assert opts["reasoning_effort"] == "low"

    def test_user_specified_with_explicit_model(self):
        cfg = _FakeCfg(model="claude-opus-4.7", reasoning_effort="high")
        opts: dict = {}
        _apply_reasoning_effort(opts, cfg, kind="main")
        assert opts["reasoning_effort"] == "high"

    def test_no_user_value_auto_model_leaves_unset(self):
        """ユーザー未指定 + Auto モデル → 何もセットしない（サーバ側 Auto Model Selection に委譲）。"""
        cfg = _FakeCfg(model=MODEL_AUTO_VALUE, reasoning_effort=None)
        opts: dict = {}
        _apply_reasoning_effort(opts, cfg, kind="main")
        assert "reasoning_effort" not in opts

    def test_no_user_value_explicit_model_leaves_unset(self):
        """ユーザー未指定 + 明示モデル → 何もセットしない（SDK 既定動作）。"""
        cfg = _FakeCfg(model="claude-opus-4.7", reasoning_effort=None)
        opts: dict = {}
        _apply_reasoning_effort(opts, cfg, kind="main")
        assert "reasoning_effort" not in opts


class TestApplyReasoningEffortReview:
    def test_review_uses_review_field(self):
        cfg = _FakeCfg(
            model=MODEL_AUTO_VALUE,
            reasoning_effort="low",  # main 用は無視されるはず
            review_reasoning_effort="high",
        )
        opts: dict = {}
        _apply_reasoning_effort(opts, cfg, kind="review", model_value=MODEL_AUTO_VALUE)
        assert opts["reasoning_effort"] == "high"

    def test_review_explicit_model_no_value(self):
        cfg = _FakeCfg(model=MODEL_AUTO_VALUE, review_reasoning_effort=None)
        opts: dict = {}
        # review 用に明示モデルが渡されたケース
        _apply_reasoning_effort(opts, cfg, kind="review", model_value="custom-model")
        assert "reasoning_effort" not in opts

    def test_review_auto_model_leaves_unset(self):
        """review_reasoning_effort 未指定 + Auto モデル → 何もセットしない。"""
        cfg = _FakeCfg(model=MODEL_AUTO_VALUE, review_reasoning_effort=None)
        opts: dict = {}
        _apply_reasoning_effort(opts, cfg, kind="review", model_value=MODEL_AUTO_VALUE)
        assert "reasoning_effort" not in opts


class TestApplyReasoningEffortQa:
    def test_qa_uses_qa_field(self):
        cfg = _FakeCfg(
            model=MODEL_AUTO_VALUE,
            qa_reasoning_effort="medium",
        )
        opts: dict = {}
        _apply_reasoning_effort(opts, cfg, kind="qa")
        assert opts["reasoning_effort"] == "medium"
