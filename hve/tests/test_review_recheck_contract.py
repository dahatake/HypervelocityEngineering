"""FR-CLI-94 / FR-CLI-95: 再レビュー Prompt は修正を指示せず、未修正 Critical の FAIL を維持する。"""

from __future__ import annotations

import ast
import inspect
import textwrap

from hve.prompts import ADVERSARIAL_RECHECK_PROMPT
from hve.runner import StepRunner


def test_recheck_prompt_has_no_fix_directive() -> None:
    assert "すべて修正し" not in ADVERSARIAL_RECHECK_PROMPT
    assert "成果物を修正しない" in ADVERSARIAL_RECHECK_PROMPT


def test_recheck_keeps_fail_for_unfixed_critical() -> None:
    assert "未修正の Critical" in ADVERSARIAL_RECHECK_PROMPT
    assert "反論の有無に依らず FAIL を維持" in ADVERSARIAL_RECHECK_PROMPT
    assert "新しい根拠を示さずに重大度を下げてはならない" in ADVERSARIAL_RECHECK_PROMPT
    # 合否基準は変更しない
    assert "Critical が 0 件になれば PASS" in ADVERSARIAL_RECHECK_PROMPT


def test_recheck_is_skipped_when_improvements_are_not_applied() -> None:
    # 評価者は修正しないため、反映しない設定では再レビューの前にループを抜ける
    source = textwrap.dedent(inspect.getsource(StepRunner.run_step))
    loop = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Name)
        and node.target.id == "cycle"
    )
    first = loop.body[0]
    assert isinstance(first, ast.If)
    assert ast.unparse(first.test) == "not self.config.apply_review_improvements_to_main"
    assert isinstance(first.body[0], ast.Break)
