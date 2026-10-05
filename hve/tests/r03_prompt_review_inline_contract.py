"""R03-R11 RED: Prompt 固有レビュー観点を通常時の単回セルフチェックへ移行する契約。

ファイル名を ``test_`` で始めないことで、R02 完了時点の通常 CI からは除外する。
R03-R11 では pytest に本ファイルのパスを明示して RED/GREEN を検証する。
"""
from __future__ import annotations

from pathlib import Path
import re

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS = _REPO_ROOT / ".github" / "prompts"
_INLINE_REVIEW_CONTRACT = (
    "以下のドメイン固有観点は成果物の受入条件であり、"
    "出力前に行う別の検証ステップでも、敵対的レビューの発動条件でもない。"
)
_OPTIONAL_REVIEW_CONTRACT = "敵対的レビューはユーザーが明示した場合のみ実施する。"
_OPTIONAL_REVIEW_PROMPTS = frozenset({"KnowledgeManager.prompt.md"})
_REVIEW_CANDIDATE_HEADING_RE = re.compile(
    r"^#{1,6}\s+.*(?:受入観点|品質レビュー|敵対的レビュー).*$",
    re.MULTILINE,
)
_REVIEW_SECTION_HEADING_RE = re.compile(
    r"^#{1,6}\s+.*受入観点（完了条件の補足）.*$",
    re.MULTILINE,
)
# FR-CLI-101: 出力前に行う独立した検証節の見出し
_STANDALONE_VERIFICATION_HEADING_RE = re.compile(
    r"^#{1,6}\s+.*(?:セルフチェック|セルフレビュー|最終品質レビュー|最終チェック).*$",
    re.MULTILINE,
)
_COMPLETION_HEADING_RE = re.compile(r"^#{1,6}\s+(?:\d+\)\s+)?完了条件\s*$", re.MULTILINE)
_MERGED_SELF_CHECK_PROMPTS = (
    "Arch-ARD-BusinessAnalysis-Targeted.prompt.md",
    "Arch-ARD-BusinessAnalysis-Untargeted.prompt.md",
    "Arch-ARD-UseCaseCatalog.prompt.md",
    "Arch-ApplicationAnalytics.prompt.md",
    "Doc-APISpec.prompt.md",
    "Doc-ArchOverview.prompt.md",
    "Doc-CICDSummary.prompt.md",
    "Doc-ComponentDesign.prompt.md",
    "Doc-ComponentIndex.prompt.md",
    "Doc-ConfigSummary.prompt.md",
    "Doc-DataModel.prompt.md",
    "Doc-DependencyMap.prompt.md",
    "Doc-FileInventory.prompt.md",
    "Doc-FileSummary.prompt.md",
    "Doc-InfraDeps.prompt.md",
    "Doc-LargeFileSummary.prompt.md",
    "Doc-Migration.prompt.md",
    "Doc-NFRAnalysis.prompt.md",
    "Doc-Onboarding.prompt.md",
    "Doc-Refactoring.prompt.md",
    "Doc-TechDebt.prompt.md",
    "Doc-TestSpecSummary.prompt.md",
    "Doc-TestSummary.prompt.md",
)
_FORBIDDEN_REPEAT_PATTERNS = (
    re.compile(r"(?:異なる観点で)?\s*3\s*度のレビュー"),
    re.compile(r"\*\*[123]\s*回目[：:]"),
)

_PROMPT_GROUPS: dict[str, tuple[str, ...]] = {
    "aas-domain": (
        "Arch-ArchitectureCandidateAnalyzer.prompt.md",
        "Arch-Microservice-DomainAnalytics.prompt.md",
        "Arch-Microservice-ServiceIdentify.prompt.md",
        "Arch-DataModeling.prompt.md",
        "Arch-DataCatalog.prompt.md",
    ),
    "aas-artifacts": (
        "Arch-Microservice-ServiceCatalog.prompt.md",
        "Arch-TDD-TestStrategy.prompt.md",
        "Arch-UI-PersonaScreenList.prompt.md",
        "Arch-PersonaCatalog.prompt.md",
        "Arch-UI-List.prompt.md",
    ),
    "aad-aag-detail": (
        "Arch-UI-Detail.prompt.md",
        "Arch-Microservice-ServiceDetail.prompt.md",
        "Arch-TDD-TestSpec.prompt.md",
        "Arch-AIAgentDesign-Step3.prompt.md",
        "Arch-AgenticRetrieval-Detail.prompt.md",
    ),
    "adfd-design": (
        "Arch-Dataflow-AppSpec.prompt.md",
        "Arch-Dataflow-MonitoringDesign.prompt.md",
        "Arch-Dataflow-TDD-TestSpec.prompt.md",
        "Arch-Dataflow-AppCatalog.prompt.md",
        "Arch-Dataflow-DataModel.prompt.md",
        "Arch-Dataflow-ServiceCatalog.prompt.md",
        "Arch-Dataflow-TestStrategy.prompt.md",
    ),
    "asdw-data-compute": (
        "Dev-Microservice-Azure-DataDesign.prompt.md",
        "Dev-Microservice-Azure-DataTestCoding.prompt.md",
        "Dev-Microservice-Azure-DataDeploy.prompt.md",
        "Dev-Microservice-Azure-ComputeDesign.prompt.md",
        "Dev-Microservice-Azure-ComputeDeploy-AzureFunctions.prompt.md",
        "Dev-Microservice-Azure-ComputePostDeployTest.prompt.md",
    ),
    "asdw-additional": (
        "Dev-Microservice-Azure-AddServiceDesign.prompt.md",
        "Dev-Microservice-Azure-AddServiceDeploy.prompt.md",
        "Dev-Microservice-Azure-AddServiceTestCoding.prompt.md",
        "Dev-Microservice-Azure-AddServiceTesting.prompt.md",
    ),
    "asdw-service-ui": (
        "Dev-Microservice-Azure-ServiceTestCoding.prompt.md",
        "Dev-Microservice-Azure-ServiceCoding-AzureFunctions.prompt.md",
        "Dev-Microservice-Azure-UITestCoding.prompt.md",
        "Dev-Microservice-Azure-UICoding.prompt.md",
        "Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.prompt.md",
    ),
    "aagd-agent": (
        "Dev-Microservice-Azure-AgentTestCoding.prompt.md",
        "Dev-Microservice-Azure-AgentCoding.prompt.md",
        "Dev-Microservice-Azure-AgentDeploy.prompt.md",
        "Dev-Microservice-Azure-AgenticRetrievalDesign.prompt.md",
    ),
    "dataflow-qa-akm": (
        "Dev-Dataflow-TestCoding.prompt.md",
        "Dev-Dataflow-ServiceCoding.prompt.md",
        "Dev-Dataflow-FunctionsDeploy.prompt.md",
        "QA-AzureArchitectureReview.prompt.md",
        "QA-AzureDependencyReview.prompt.md",
        "KnowledgeManager.prompt.md",
    ),
}

_EXPECTED_PROMPTS = frozenset(
    name for names in _PROMPT_GROUPS.values() for name in names
)


def _review_prompts_on_disk() -> set[str]:
    terms = ("adversarial-review", "受入観点（完了条件の補足）", "敵対的レビュー")
    result: set[str] = set()
    for path in _PROMPTS.glob("*.prompt.md"):
        text = path.read_text(encoding="utf-8")
        if (
            any(term in text for term in terms)
            or _REVIEW_CANDIDATE_HEADING_RE.search(text)
            or any(pattern.search(text) for pattern in _FORBIDDEN_REPEAT_PATTERNS)
        ):
            result.add(path.name)
    return result


def test_review_prompt_inventory_is_complete_and_non_overlapping() -> None:
    """現行レビュー Prompt を重複なしで全て契約対象にする。"""
    flattened = [name for names in _PROMPT_GROUPS.values() for name in names]
    assert len(flattened) == len(set(flattened))
    assert _EXPECTED_PROMPTS == _review_prompts_on_disk()
    assert all((_PROMPTS / name).is_file() for name in _EXPECTED_PROMPTS)
    assert _OPTIONAL_REVIEW_PROMPTS < _EXPECTED_PROMPTS


@pytest.mark.parametrize("prompt_name", sorted(_EXPECTED_PROMPTS))
def test_prompt_review_section_is_single_inline_check_not_activation(
    prompt_name: str,
) -> None:
    """レビュー観点だけで敵対的レビューや反復 Sub-agent を発動させない。"""
    text = (_PROMPTS / prompt_name).read_text(encoding="utf-8")
    violations: list[str] = []

    if "adversarial-review" in text:
        violations.append("Prompt が共有 Skill を直接発動している")

    if prompt_name in _OPTIONAL_REVIEW_PROMPTS:
        if _OPTIONAL_REVIEW_CONTRACT not in text:
            violations.append("ユーザー明示時のみの任意レビュー契約がない")
    elif _INLINE_REVIEW_CONTRACT not in text:
        violations.append("受入観点の正規文がない")
    else:
        contract_at = text.index(_INLINE_REVIEW_CONTRACT)
        nearby_prefix = text[max(0, contract_at - 500) : contract_at]
        if not _REVIEW_SECTION_HEADING_RE.search(nearby_prefix):
            violations.append("正規文がレビュー節内に配置されていない")

    for pattern in _FORBIDDEN_REPEAT_PATTERNS:
        if pattern.search(text):
            violations.append(f"反復レビュー指示が残っている: {pattern.pattern}")

    assert not violations, f"{prompt_name}: " + " / ".join(violations)


def test_prompts_have_no_standalone_verification_step() -> None:
    """FR-CLI-101: 出力前に行う独立した検証節を持たない。"""
    offenders: list[str] = []
    for path in sorted(_PROMPTS.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for match in _STANDALONE_VERIFICATION_HEADING_RE.finditer(text):
            offenders.append(f"{path.relative_to(_PROMPTS).as_posix()}: {match.group(0)}")
    assert offenders == []


@pytest.mark.parametrize("prompt_name", _MERGED_SELF_CHECK_PROMPTS)
def test_self_check_items_are_merged_into_completion_criteria(prompt_name: str) -> None:
    """FR-CLI-101: 旧セルフチェック節の項目を完了条件の 1 か所へ統合する。"""
    text = (_PROMPTS / prompt_name).read_text(encoding="utf-8")
    assert len(_COMPLETION_HEADING_RE.findall(text)) == 1
    assert "出力前に必ず確認" not in text


# FR-CLI-101（N4-2）: 存在しない「最終品質レビュー」節への参照や、出力前の自己検証の指示を残さない。
_SELF_REVIEW_TOKENS = ("最終品質レビュー", "セルフチェック", "セルフレビュー", "自己レビュー", "内部思考")
# v3.26（N4-7）で HVE が実行時に付与する指示文も対象にした。
_SELF_REVIEW_EXEMPT: frozenset[str] = frozenset()


def test_prompts_do_not_instruct_a_separate_self_review() -> None:
    offenders: list[str] = []
    for path in sorted(_PROMPTS.rglob("*.md")):
        relative = path.relative_to(_PROMPTS).as_posix()
        if relative in _SELF_REVIEW_EXEMPT:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for token in _SELF_REVIEW_TOKENS:
                if token in line:
                    offenders.append(f"{relative}:{number}: {token}")
    assert offenders == []
