"""要求定義 §13.5（ADFDV）の記述が実装と一致することを固定する。

§13.5 は ABD → ADFD、`batch` → `dataflow` のリネーム時に更新されず、
- 節名が旧称 ABDV（Batch Dev）のまま
- fan-out parser が実在しない `batch_job_catalog`
- 成果物パスが `src/batch/**` / `test/batch/**`
という実装と乖離した状態が残っていた。

要求定義は正規文書であり、実装と乖離したまま放置すると保守判断の根拠を失う。
ここでは §13.5 固有の宣言（見出し名・fan-out parser・Custom Agent・旧パス不在）を
`hve/workflow_registry.py` の実定義と突き合わせて固定する。

Step ID 集合の一致は全 Workflow 横断の単一実装（FR-MAINT-09 /
`hve/tests/test_requirement_section13_parity.py`）が担うため、本ファイルでは検査しない（FR-MAINT-07）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hve.catalog_parsers import get_parser_input_path  # noqa: E402
from hve.workflow_registry import get_workflow  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIREMENT_DEFINITION = _REPO_ROOT / "hve-dev" / "requirement-definition.md"


def _section_13_5() -> str:
    text = _REQUIREMENT_DEFINITION.read_text(encoding="utf-8")
    start = text.index("### 13.5 ")
    end = text.index("### 13.6 ", start)
    return text[start:end]


def test_section_13_5_uses_the_current_workflow_name() -> None:
    """旧称 ABDV / Batch Dev を見出しに残さない。"""
    section = _section_13_5()
    heading = section.splitlines()[0]

    assert "ADFDV" in heading, f"見出しが現行 workflow 名を指していない: {heading}"
    assert "Dataflow Dev" in heading, heading


def test_section_13_5_declares_the_actual_fanout_parser() -> None:
    """fan-out parser 名を実装と一致させる。"""
    section = _section_13_5()
    workflow = get_workflow("adfdv")
    assert workflow is not None
    parsers = {
        step.fanout_parser
        for step in workflow.steps
        if getattr(step, "fanout_parser", None)
    }

    assert parsers, "ADFDV に fan-out Step が無い（前提が変わっている）"
    for parser in parsers:
        assert f"`{parser}`" in section, f"§13.5 が fan-out parser `{parser}` を記載していない"
    assert "batch_job_catalog" not in section, "実在しない旧 parser 名が残っている"


def test_fr_wf_adfdv_01_declares_the_parser_catalog_sources() -> None:
    """fan-out のキー元を dataflow_catalog の実装契約へ合わせる。"""
    section = _section_13_5()
    block = section.split("- **FR-WF-ADFDV-01**:", 1)[1].split(
        "- **FR-WF-ADFDV-02**:", 1
    )[0]
    primary = "docs/catalog/app-arch-catalog.md"
    fallback = get_parser_input_path("dataflow_catalog")
    assert fallback == "docs/catalog/app-catalog.md"
    assert primary in block
    assert fallback in block
    assert "優先" in block and "フォールバック" in block
    assert "docs/dataflow/dataflow-app-catalog.md をキー元" not in block


def test_section_13_5_declares_the_actual_custom_agents() -> None:
    """Custom Agent 名を実装と一致させる。"""
    section = _section_13_5()
    workflow = get_workflow("adfdv")
    assert workflow is not None

    for step in workflow.steps:
        agent = getattr(step, "custom_agent", None)
        if not agent:
            continue
        assert agent in section, f"§13.5 が Step {step.id} の Custom Agent {agent} を記載していない"


def test_section_13_5_step_43_output_matches_registry() -> None:
    """Step 4.3 の成果物を registry の canonical path と一致させる。"""
    section = _section_13_5()
    workflow = get_workflow("adfdv")
    assert workflow is not None
    step = workflow.get_step("4.3")
    assert step is not None
    rows = [line for line in section.splitlines() if line.startswith("| 4.3 |")]
    assert len(rows) == 1, "§13.5 の ADFDV Step 4.3 行を一意に抽出できません"

    cells = [cell.strip() for cell in rows[0].strip("|").split("|")]
    declared_paths = re.findall(r"`([^`]+)`", cells[5])
    assert declared_paths == step.output_paths, (
        f"§13.5={declared_paths}, registry={step.output_paths}"
    )
    retired = "docs/azure/dataflow-requirements-conformance-report.md"
    assert retired not in rows[0], f"廃止済み Step 4.3 path が表行に残存: {retired}"


def test_section_13_5_does_not_reference_the_retired_batch_paths() -> None:
    """`src/batch/**` / `test/batch/**` はリネーム済みで実在しない。"""
    section = _section_13_5()

    for retired in ("src/batch/", "test/batch/", "src/infra/azure/batch/"):
        assert retired not in section, f"リネーム前のパスが残っている: {retired}"
