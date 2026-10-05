"""FR-CLI-92: Phase 3 の評価を review_model に依らず新しいセッションで行う契約。"""

from __future__ import annotations

import ast
import inspect
import textwrap

from hve.config import SDKConfig
from hve.console import Console
from hve.runner import StepRunner


def _phase3_block() -> ast.If:
    tree = ast.parse(textwrap.dedent(inspect.getsource(StepRunner.run_step)))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Attribute)
            and node.test.attr == "auto_contents_review"
            and any(
                isinstance(sub, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "review_response" for t in sub.targets)
                for sub in ast.walk(node)
            )
        ):
            return node
    raise AssertionError("Phase 3 block not found in run_step")


def test_review_always_uses_sub_session() -> None:
    block = _phase3_block()
    source = ast.unparse(block)

    # review_model の一致・不一致でセッションを切り替えない
    assert "_should_use_review_sub_session" not in source
    assert "_log_main_session_reuse" not in source
    # メインセッションを評価セッションとして代入しない
    for node in ast.walk(block):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_effective_review_session" for t in node.targets
        ):
            assert not (isinstance(node.value, ast.Name) and node.value.id == "session")
    # 評価用サブセッションは Phase 3 の中で必ず作成される
    assert "_create_session_with_auto_reasoning_fallback" in source
    assert 'suffix="review"' in source or "suffix='review'" in source


def test_review_sub_session_reason_is_logged_for_same_model() -> None:
    cfg = SDKConfig(dry_run=True, model="claude-opus-4.7")
    runner = StepRunner(config=cfg, console=Console(verbose=False, quiet=True))
    events: list[str] = []
    runner.console.event = events.append  # type: ignore[method-assign]

    runner._log_sub_session_reason("1.1", "Review", qa_model=cfg.get_review_model())

    assert events
    assert "内部エラー" not in events[0]
    assert "評価分離" in events[0]
