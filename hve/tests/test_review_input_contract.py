"""FR-CLI-93: Phase 3 の評価セッションへの入力を宣言 output_paths に絞る契約。"""

from __future__ import annotations

import inspect

from hve import runner
from hve.console import Console
from hve.prompts import REVIEW_PROMPT


def _build(output_paths: list[str], main_output: str) -> str:
    return runner._build_phase3_review_prompt(
        step_id="2.1",
        title="画面設計",
        output_paths=output_paths,
        main_output=main_output,
        max_chars=100,
        console=Console(verbose=False, quiet=True),
    )


def test_review_input_is_artifact_paths() -> None:
    main_output = "MAIN-OUTPUT-SENTINEL " * 50
    prompt = _build(["docs/screen/a.md", "docs/screen/b.md"], main_output)

    assert "2.1" in prompt and "画面設計" in prompt
    assert "docs/screen/a.md" in prompt and "docs/screen/b.md" in prompt
    assert "MAIN-OUTPUT-SENTINEL" not in prompt
    assert prompt.endswith(REVIEW_PROMPT)


def test_review_input_falls_back_to_main_output_without_declared_paths() -> None:
    prompt = _build([], "MAIN-OUTPUT-SENTINEL")

    assert "MAIN-OUTPUT-SENTINEL" in prompt
    assert prompt.endswith(REVIEW_PROMPT)


def test_run_step_resolves_review_paths_with_existing_resolver() -> None:
    source = inspect.getsource(runner.StepRunner.run_step)
    phase3 = source.split("# Phase 3: 敵対的レビュー", 1)[1].split("# Phase 4:", 1)[0]

    assert "_build_phase3_review_prompt(" in phase3
    assert "_resolve_step_output_paths(" in phase3
