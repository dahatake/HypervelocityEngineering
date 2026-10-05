"""FR-CLI-103 — prompts must not stop only to ask users."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

ASK_STOP_PATTERN = re.compile(
    r"質問して(?:停止|確定)"
    r"|利用者へ質問して停止"
    r"|ユーザーへ質問して停止"
    r"|質問は最大"
    r"|最大[0-9]+問"
    r"|回答を待って"
    r"|推測でテストを作らず停止"
    r"|確認してから(?:進|着手)"
    r"|全回答が揃うまで作業を進めない"
    r"|ユーザーに回答を求める"
)

ALLOWLIST: dict[str, str] = {
    ".github/prompts/cloud/copilot-auto-feedback-auto-qa.prompt.md": (
        "FR-CLI-103 exception: Cloud QA flow may create questions."
    ),
    ".github/prompts/runtime/qa/pre-execution.prompt.md": (
        "FR-CLI-103 exception: pre-execution QA flow may create questions."
    ),
    ".github/prompts/runtime/qa/post-execution.prompt.md": (
        "FR-CLI-103 exception: pre-execution QA flow may classify questions."
    ),
    ".github/skills/hve-prompt-edition/SKILL.md": (
        "FR-CLI-103 exception: Prompt Edition request pre-flight gate."
    ),
    ".github/skills/task-questionnaire/SKILL.md": (
        "FR-CLI-103 exception: explicit questionnaire or Cloud QA path."
    ),
    ".github/skills/task-questionnaire/references/pr-protocol.md": (
        "FR-CLI-103 exception: explicit questionnaire or Cloud QA path."
    ),
    ".github/skills/task-questionnaire/references/standalone-protocol.md": (
        "FR-CLI-103 exception: explicit questionnaire or Cloud QA path."
    ),
}


def _repo_relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _markdown_files() -> list[Path]:
    targets = list((ROOT / ".github" / "prompts").rglob("*.md"))
    targets.extend((ROOT / ".github" / "skills").rglob("*.md"))
    return sorted(targets)


def test_prompts_and_skills_do_not_stop_for_user_answers() -> None:
    offenders: list[str] = []
    for path in _markdown_files():
        rel = _repo_relative(path)
        if rel in ALLOWLIST:
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if ASK_STOP_PATTERN.search(line):
                offenders.append(f"{rel}:{line_no}: {line.strip()}")

    assert offenders == []


def test_required_prompt_rewrites_are_present() -> None:
    doc_consistency = (
        ROOT / ".github" / "prompts" / "QA-DocConsistency.prompt.md"
    ).read_text(encoding="utf-8")
    assert "既定値を選び、理由と影響を記録して続行する" in doc_consistency
    assert "質問票を作成するモードでは、この限りではない" in doc_consistency

    compute_design = (
        ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-ComputeDesign.prompt.md"
    ).read_text(encoding="utf-8")
    assert "採用した既定値・理由・影響を記録する" in compute_design

    agent_test = (
        ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-AgentTestCoding.prompt.md"
    ).read_text(encoding="utf-8")
    assert (
        "設計が`TBD`の能力は、テストを保留として理由とともに記録し、"
        "ほかの能力の作業を続けてください。"
    ) in agent_test

    step_inputs = (
        ROOT / ".github" / "prompts" / "cloud" / "step-inputs.prompt.md"
    ).read_text(encoding="utf-8")
    assert (
        "添付の URL を推測せず、その資料なしで進められる作業を続け、"
        "欠けた入力を報告に記録してください。"
    ) in step_inputs

    questionnaire = (
        ROOT / ".github" / "skills" / "task-questionnaire" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert (
        "不明点は既定値を選び、理由と影響を記録して進めてください。"
    ) in questionnaire
    assert (
        "質問票は、利用者が求めたときか、Cloud の QA 経路でだけ作ります。"
    ) in questionnaire
