"""TDD GREEN リトライ戦略 Skill の契約テスト。

`tdd-green-retry-strategy` Skill の新設と、TDD GREEN フェーズを持つ各 Agent prompt への
結線が消えないことをキーフレーズ部分一致で固定する（脆性低減のため文言完全一致は避ける）。

背景（捏造なし・実証済み）: ASDW-WEB Step.1.3 で、GREEN 化リトライが「同一アプローチの
単純反復」だったため 3 回とも同じ弱点に当たり続け GREEN 未達になった（run
20260702T181844-1a8e06）。これを受け、GREEN 化ループを持つ全 Step で「多層・異アプローチ・
失敗の都度に公式技術情報 MCP で根本原因調査」を共通規律として一元化した。
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILL = (
    _REPO_ROOT
    / ".github"
    / "skills"
    / "testing"
    / "tdd-green-retry-strategy"
    / "SKILL.md"
)
_ROUTING = _REPO_ROOT / ".github" / "skills" / "_routing" / "README.md"
_PROMPTS_DIR = _REPO_ROOT / ".github" / "prompts"
_TEMPLATES_DIR = _REPO_ROOT / ".github" / "prompts" / "steps"
_TDD_REPORT_PATH = "tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md"

# tdd-green-retry-strategy を結線した「TDD GREEN フェーズを持つ」Agent prompt。
# post-deploy (ComputePostDeployTest) は「反復よりフィードバック重視」の明示的設計のため対象外。
_WIRED_GREEN_PROMPTS = [
    "Dev-Microservice-Azure-DataDeploy.prompt.md",
    "Dev-Microservice-Azure-AddServiceTesting.prompt.md",
    "Dev-Microservice-Azure-ServiceCoding-AzureFunctions.prompt.md",
    "Dev-Microservice-Azure-UICoding.prompt.md",
    "E2ETesting-Playwright.prompt.md",
    "Dev-Dataflow-ServiceCoding.prompt.md",
    "Dev-Microservice-Azure-AgentCoding.prompt.md",
]


def test_skill_file_exists() -> None:
    """tdd-green-retry-strategy Skill が存在する。"""
    assert _SKILL.is_file(), f"Skill 未検出: {_SKILL}"


def test_skill_declares_name_in_frontmatter() -> None:
    """Skill の frontmatter に name が宣言され、resolver が自動検出できる。"""
    text = _SKILL.read_text(encoding="utf-8")
    assert "name: tdd-green-retry-strategy" in text


def test_skill_has_multi_layer_principle() -> None:
    """多層リトライ（内側から外側へ）の原則が含まれる。"""
    text = _SKILL.read_text(encoding="utf-8")
    assert "多層リトライ" in text
    assert "Layer 1" in text
    assert "Layer 2" in text
    assert "最大 5 回" in text


def test_skill_prohibits_same_approach_repeat() -> None:
    """同一アプローチの単純反復を禁止し、異なるアプローチを要求する。"""
    text = _SKILL.read_text(encoding="utf-8")
    assert "異なるアプローチ" in text
    assert "単純反復" in text or "単純に繰り返さない" in text


def test_skill_requires_official_mcp_per_failure() -> None:
    """失敗の都度に根本原因特定＋公式技術情報 MCP で解決策取得を要求する。"""
    text = _SKILL.read_text(encoding="utf-8")
    assert "根本原因" in text
    assert "Microsoft Learn MCP" in text
    # Python / その他言語のカバレッジ（JS/TS 含む）
    assert "Python 技術情報 MCP" in text
    assert "JavaScript" in text or "TypeScript" in text
    # Web は最後の手段
    assert "Web 検索" in text


def test_skill_records_green_retry_to_tdd_report() -> None:
    """GREEN retry の試行結果が TDD report に記録される契約を持つ。"""
    text = _SKILL.read_text(encoding="utf-8")
    assert _TDD_REPORT_PATH in text
    assert "Root-Cause" in text


def test_routing_table_lists_skill() -> None:
    """ルーティング表に新 Skill が登録されている。"""
    text = _ROUTING.read_text(encoding="utf-8")
    assert "tdd-green-retry-strategy" in text


def test_all_green_prompts_reference_skill() -> None:
    """TDD GREEN フェーズを持つ全 prompt が共通 Skill を参照する。"""
    for name in _WIRED_GREEN_PROMPTS:
        path = _PROMPTS_DIR / name
        assert path.is_file(), f"prompt 未検出: {path}"
        text = path.read_text(encoding="utf-8")
        assert "tdd-green-retry-strategy" in text, f"{name} に Skill 参照が無い"


def test_all_green_prompts_require_official_mcp_lookup() -> None:
    """各 GREEN prompt が失敗時の公式技術情報 MCP 参照を要求する。

    Azure/C# 系（DataDeploy / AddServiceTesting / ServiceCoding-AzureFunctions /
    Dev-Dataflow-ServiceCoding / AgentCoding）は Microsoft Learn MCP を明示する。
    UI/E2E 系（UICoding / E2ETesting-Playwright）は JS/TS/Playwright の公式ドキュメント
    MCP を参照する（`当該技術（...）の公式ドキュメント・API を提供する MCP` 表現）。
    """
    microsoft_learn = {
        "Dev-Microservice-Azure-DataDeploy.prompt.md",
        "Dev-Microservice-Azure-AddServiceTesting.prompt.md",
        "Dev-Microservice-Azure-ServiceCoding-AzureFunctions.prompt.md",
        "Dev-Dataflow-ServiceCoding.prompt.md",
        "Dev-Microservice-Azure-AgentCoding.prompt.md",
    }
    tech_docs_mcp = {
        "Dev-Microservice-Azure-UICoding.prompt.md",
        "E2ETesting-Playwright.prompt.md",
    }
    for name in microsoft_learn:
        text = (_PROMPTS_DIR / name).read_text(encoding="utf-8")
        assert "Microsoft Learn MCP" in text, f"{name} に Microsoft Learn MCP 参照が無い"
    for name in tech_docs_mcp:
        text = (_PROMPTS_DIR / name).read_text(encoding="utf-8")
        assert "公式ドキュメント・API を提供する MCP" in text, (
            f"{name} に当該技術の公式ドキュメント MCP 参照が無い"
        )


def test_all_green_prompts_require_different_approach() -> None:
    """各 GREEN prompt が異なるアプローチでのリトライを要求する。"""
    for name in _WIRED_GREEN_PROMPTS:
        text = (_PROMPTS_DIR / name).read_text(encoding="utf-8")
        assert "異なるアプローチ" in text, f"{name} に異アプローチ要求が無い"


def test_fixed_count_steps_unified_to_five() -> None:
    """固定 3 回だった Step.1.3 / Step.4.4 のテンプレートが最大 5 回に統一されている。"""
    step_1_3 = (_TEMPLATES_DIR / "asdw-web" / "step-1.3.prompt.md").read_text(encoding="utf-8")
    step_4_4 = (_TEMPLATES_DIR / "asdw-web" / "step-4.4.prompt.md").read_text(encoding="utf-8")
    assert "初回を含め最大5回" in step_1_3
    assert "実際に対象stage processを開始した後" in step_1_3
    assert "process開始前の拒否" in step_1_3
    assert "最大3回反復" not in step_1_3
    assert "最大 5 回リトライ" in step_4_4
    assert "最大 3 回リトライ" not in step_4_4


# tdd_max_retries（既定 5）を使う GREEN テンプレート。回数変更は不要だが、
# GREEN loop 記述に Skill 参照（異アプローチ＋失敗都度の公式技術情報 MCP 調査）を持つ。
_WIRED_GREEN_TEMPLATES = [
    _TEMPLATES_DIR / "asdw-web" / "step-3.3.prompt.md",
    _TEMPLATES_DIR / "asdw-web" / "step-4.2.prompt.md",
    _TEMPLATES_DIR / "aagd" / "step-2.3.prompt.md",
    _TEMPLATES_DIR / "adfdv" / "step-2.2.prompt.md",
]


def test_tdd_max_retries_green_templates_reference_skill() -> None:
    """tdd_max_retries を使う GREEN テンプレートが共通 Skill を参照する。"""
    for path in _WIRED_GREEN_TEMPLATES:
        assert path.is_file(), f"テンプレート未検出: {path}"
        text = path.read_text(encoding="utf-8")
        assert "tdd-green-retry-strategy" in text, f"{path.name} に Skill 参照が無い"
        assert "異なるアプローチ" in text, f"{path.name} に異アプローチ要求が無い"
        assert "MCP" in text, f"{path.name} に公式技術情報 MCP 参照が無い"


def test_count_change_green_templates_reference_skill() -> None:
    """固定回数を 5 へ統一した step-1.3 / step-4.4 も Skill を参照する。"""
    for rel in (("asdw-web", "step-1.3.prompt.md"), ("asdw-web", "step-4.4.prompt.md")):
        path = _TEMPLATES_DIR / rel[0] / rel[1]
        text = path.read_text(encoding="utf-8")
        assert "tdd-green-retry-strategy" in text, f"{path.name} に Skill 参照が無い"
