"""TDD RED/GREEN test report contract tests.

These tests pin the minimal reporting contract for HVE TDD RED/GREEN steps.
They intentionally avoid parsing natural language and look for stable path/schema
markers in skills, prompts, and templates.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_DIR = _REPO_ROOT / ".github" / "skills"
_PROMPTS_DIR = _REPO_ROOT / ".github" / "prompts"
_TEMPLATES_DIR = _REPO_ROOT / ".github" / "prompts" / "steps"

_REPORT_PATH = "tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md"
_ASDW_DATA_DEPLOY_REPORT_PATH = (
    "tests/run/<run-id>/asdw-web/step-1-3/<target-app-id>/GREEN/"
    "tdd-test-report.md"
)
# Step.1.3 は generic runtime path を具体化した、より厳密な canonical path を使う。
# override 対象はこの Prompt/Template だけとし、他のTDD生成元は generic契約を維持する。
_PROMPT_REPORT_PATH_OVERRIDES = {
    "Dev-Microservice-Azure-DataDeploy.prompt.md": _ASDW_DATA_DEPLOY_REPORT_PATH,
}
_TEMPLATE_REPORT_PATH_OVERRIDES = {
    _TEMPLATES_DIR / "asdw-web" / "step-1.3.prompt.md": _ASDW_DATA_DEPLOY_REPORT_PATH,
}
_REQUIRED_SCHEMA_TOKENS = [
    "Schema-Version",
    "Evidence-Status",
    "TDD-Judgement",
    "Secret-Redaction",
    "Test-Files-Changed",
]
_FIXED_TDD_REPORT_SCHEMA_TOKENS = [
    "<!-- validation-confirmed -->",
    "- Schema-Version: 1",
    "- Workflow:",
    "- Step:",
    "- Agent:",
    "- Target-Key:",
    "- Phase:",
    "- Test-Code-Path:",
    "- Timestamp-UTC:",
    "- Evidence-Status:",
    "- TDD-Judgement:",
    "- Secret-Redaction: confirmed",
    "- Test-Files-Changed:",
    "## Command",
    "## Expected Outcome",
    "## Actual Result",
    "## Evidence",
    "## Failure Analysis",
    "## Test Protection",
]

_TDD_REPORT_PROMPTS = [
    "Dev-Microservice-Azure-DataTestCoding.prompt.md",
    "Dev-Microservice-Azure-DataDeploy.prompt.md",
    "Dev-Microservice-Azure-AddServiceTestCoding.prompt.md",
    "Dev-Microservice-Azure-AddServiceTesting.prompt.md",
    "Dev-Microservice-Azure-ServiceTestCoding.prompt.md",
    "Dev-Microservice-Azure-ServiceCoding-AzureFunctions.prompt.md",
    "Dev-Microservice-Azure-UITestCoding.prompt.md",
    "Dev-Microservice-Azure-UICoding.prompt.md",
    "Dev-Microservice-Azure-AgentTestCoding.prompt.md",
    "Dev-Microservice-Azure-AgentCoding.prompt.md",
    "Dev-Dataflow-TestCoding.prompt.md",
    "Dev-Dataflow-ServiceCoding.prompt.md",
]

_TDD_REPORT_TEMPLATES = [
    _TEMPLATES_DIR / "asdw-web" / "step-1.2.prompt.md",
    _TEMPLATES_DIR / "asdw-web" / "step-1.3.prompt.md",
    _TEMPLATES_DIR / "asdw-web" / "step-2.3.prompt.md",
    _TEMPLATES_DIR / "asdw-web" / "step-2.4.prompt.md",
    _TEMPLATES_DIR / "asdw-web" / "step-3.2.prompt.md",
    _TEMPLATES_DIR / "asdw-web" / "step-3.3.prompt.md",
    _TEMPLATES_DIR / "asdw-web" / "step-4.1.prompt.md",
    _TEMPLATES_DIR / "asdw-web" / "step-4.2.prompt.md",
    _TEMPLATES_DIR / "adfdv" / "step-2.1.prompt.md",
    _TEMPLATES_DIR / "adfdv" / "step-2.2.prompt.md",
    _TEMPLATES_DIR / "aagd" / "step-2.2.prompt.md",
    _TEMPLATES_DIR / "aagd" / "step-2.3.prompt.md",
]

# 固定 TDD レポートスキーマの正本は Prompt（さらに上流は Skill `tdd-red-green-reality`）。
# Prompt と template は同一 Agent プロンプトへ連結されて注入されるため、両方に逐語で
# 固定スキーマを持たせると 33 行が重複する。ここに列挙した template だけは
# 「固定スキーマは委譲先 Prompt で検証し、template は Step 固有値のみ持つ」契約とする。
# 委譲は「同一の固定スキーマを持つ Prompt が存在する template」に限定し、
# 委譲先 Prompt には固定スキーマ全トークンを必ず要求する（検証の消滅を防ぐ）。
_SCHEMA_DELEGATED_TEMPLATES = {
    _TEMPLATES_DIR / "asdw-web" / "step-1.2.prompt.md": (
        "Dev-Microservice-Azure-DataTestCoding.prompt.md"
    ),
}

# 委譲対象 template が Prompt へ畳み込めない Step 固有値。
# generic な `<workflow-id>` / `<step-id>` / `<phase>` プレースホルダでは表現できず、
# Step 1.2 でのみ確定する値・パス・状態を固定する。
_STEP_SCOPED_TEMPLATE_TOKENS = {
    _TEMPLATES_DIR / "asdw-web" / "step-1.2.prompt.md": (
        "- Workflow: asdw-web",
        "- Step: 1.2",
        "- Phase: RED",
        # live Azure verifier を実行しない Step 1.2 固有の帰結
        "- Live-RED-Status: NOT_RUN",
        "tests/run/<run-id>/asdw-web/step-1-2/<target-app-id>/RED/tdd-test-report.md",
        "tests/run/<run-id>/asdw-web/step-1-2/<target-app-id>/RED/static-verification.log",
        "Raw-Log-Path",
        "src/infra/azure/verify-data-resources.sh",
    ),
}


def _assert_fixed_tdd_report_schema(text: str, source: str) -> None:
    missing = [token for token in _FIXED_TDD_REPORT_SCHEMA_TOKENS if token not in text]
    assert not missing, f"{source} missing fixed TDD report schema tokens: {missing!r}"


def test_tdd_reality_skill_defines_test_report_path_and_schema() -> None:
    text = (_SKILLS_DIR / "testing" / "tdd-red-green-reality" / "SKILL.md").read_text(encoding="utf-8")
    assert _REPORT_PATH in text
    for token in _REQUIRED_SCHEMA_TOKENS:
        assert token in text, f"tdd-red-green-reality skill missing {token!r}"


def test_tdd_reality_skill_defines_fixed_markdown_report_template() -> None:
    text = (_SKILLS_DIR / "testing" / "tdd-red-green-reality" / "SKILL.md").read_text(encoding="utf-8")
    _assert_fixed_tdd_report_schema(text, "tdd-red-green-reality skill")


def test_tdd_green_retry_skill_records_retry_to_tdd_report() -> None:
    text = (_SKILLS_DIR / "testing" / "tdd-green-retry-strategy" / "SKILL.md").read_text(encoding="utf-8")
    assert _REPORT_PATH in text
    assert "異なるアプローチ" in text
    assert "Root-Cause" in text or "root cause" in text or "根本原因" in text


def test_harness_verification_loop_distinguishes_tdd_report_from_verification_report() -> None:
    text = (
        _SKILLS_DIR
        / "harness"
        / "harness-verification-loop"
        / "references"
        / "verification-commands.md"
    ).read_text(encoding="utf-8")
    assert "verification-report.md" in text
    assert "tdd-test-report.md" in text
    assert _REPORT_PATH in text


def test_tdd_prompts_require_standard_test_report() -> None:
    for name in _TDD_REPORT_PROMPTS:
        text = (_PROMPTS_DIR / name).read_text(encoding="utf-8")
        expected_path = _PROMPT_REPORT_PATH_OVERRIDES.get(name, _REPORT_PATH)
        assert expected_path in text, f"{name} does not require its TDD report path"
        assert "TDD-Judgement" in text, f"{name} does not require TDD-Judgement"
        assert "Secret-Redaction" in text, f"{name} does not require secret redaction evidence"


def test_tdd_prompts_require_fixed_tdd_report_schema() -> None:
    for name in _TDD_REPORT_PROMPTS:
        path = _PROMPTS_DIR / name
        _assert_fixed_tdd_report_schema(path.read_text(encoding="utf-8"), path.name)


def test_tdd_templates_require_standard_test_report() -> None:
    for path in _TDD_REPORT_TEMPLATES:
        text = path.read_text(encoding="utf-8")
        expected_path = _TEMPLATE_REPORT_PATH_OVERRIDES.get(path, _REPORT_PATH)
        assert expected_path in text, f"{path.relative_to(_REPO_ROOT)} missing TDD report path"
        assert "TDD-Judgement" in text, f"{path.relative_to(_REPO_ROOT)} missing TDD judgement marker"


def test_asdw_data_deploy_report_path_override_is_exact_and_limited() -> None:
    assert _PROMPT_REPORT_PATH_OVERRIDES == {
        "Dev-Microservice-Azure-DataDeploy.prompt.md": _ASDW_DATA_DEPLOY_REPORT_PATH,
    }
    data_deploy_template = _TEMPLATES_DIR / "asdw-web" / "step-1.3.prompt.md"
    assert _TEMPLATE_REPORT_PATH_OVERRIDES == {
        data_deploy_template: _ASDW_DATA_DEPLOY_REPORT_PATH,
    }
    for path in (
        _PROMPTS_DIR / "Dev-Microservice-Azure-DataDeploy.prompt.md",
        data_deploy_template,
    ):
        text = path.read_text(encoding="utf-8")
        marker = f"- 出力先: `{_ASDW_DATA_DEPLOY_REPORT_PATH}`"
        assert text.count(_ASDW_DATA_DEPLOY_REPORT_PATH) == 1, path
        assert marker in text, path


def test_tdd_templates_require_fixed_tdd_report_schema() -> None:
    for path in _TDD_REPORT_TEMPLATES:
        rel = str(path.relative_to(_REPO_ROOT))
        text = path.read_text(encoding="utf-8")
        delegated_prompt = _SCHEMA_DELEGATED_TEMPLATES.get(path)
        if delegated_prompt is None:
            _assert_fixed_tdd_report_schema(text, rel)
            continue
        # 委譲した場合でも固定スキーマの検証は消滅させない: 委譲先 Prompt に全トークンを要求する。
        prompt_path = _PROMPTS_DIR / delegated_prompt
        _assert_fixed_tdd_report_schema(prompt_path.read_text(encoding="utf-8"), prompt_path.name)
        # template は委譲先を明示し、Step 固有値だけを保持する。
        assert delegated_prompt in text, f"{rel} does not reference its schema owner prompt"
        missing = [token for token in _STEP_SCOPED_TEMPLATE_TOKENS[path] if token not in text]
        assert not missing, f"{rel} missing step-scoped TDD report tokens: {missing!r}"


def test_fixed_schema_delegation_is_limited_and_backed_by_prompt_contract() -> None:
    """固定スキーマの Prompt 委譲は限定的で、Prompt 側検証で必ず担保される。"""
    assert _SCHEMA_DELEGATED_TEMPLATES == {
        _TEMPLATES_DIR / "asdw-web" / "step-1.2.prompt.md": (
            "Dev-Microservice-Azure-DataTestCoding.prompt.md"
        ),
    }
    assert set(_SCHEMA_DELEGATED_TEMPLATES) <= set(_TDD_REPORT_TEMPLATES)
    assert set(_SCHEMA_DELEGATED_TEMPLATES) == set(_STEP_SCOPED_TEMPLATE_TOKENS)
    for path, prompt_name in _SCHEMA_DELEGATED_TEMPLATES.items():
        # 委譲先 Prompt は test_tdd_prompts_require_fixed_tdd_report_schema の対象であること。
        assert prompt_name in _TDD_REPORT_PROMPTS, (path, prompt_name)
        # 委譲した template は固定スキーマを逐語で持たない（重複の再発を防ぐ）。
        text = path.read_text(encoding="utf-8")
        assert "- Schema-Version: 1" not in text, path
        assert "## Test Protection" not in text, path
