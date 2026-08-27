"""ADFDV Deploy prompt の AC verification 契約テスト。"""

from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS = _REPO_ROOT / ".github" / "prompts"
_DATA_DEPLOY = _PROMPTS / "Dev-Dataflow-DataDeploy.prompt.md"
_FUNCTIONS_DEPLOY = _PROMPTS / "Dev-Dataflow-FunctionsDeploy.prompt.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_data_deploy_requires_gate_visible_ac_verification() -> None:
    """DataDeploy は gate が読む `{WORK}ac-verification.md` を必須成果物にする。"""
    text = _read(_DATA_DEPLOY)

    assert "{WORK}ac-verification.md" in text
    assert "artifacts/" in text
    assert "置かない" in text or "配下に置かない" in text


def test_data_deploy_requires_ac3_green() -> None:
    """DataDeploy の実在系 AC-3 は ✅ のみ許容する。"""
    text = _read(_DATA_DEPLOY)

    assert "AC-3" in text
    assert "✅" in text
    assert "NEEDS-VERIFICATION" in text
    assert "success" in text or "成功" in text


def test_functions_deploy_requires_gate_visible_ac_verification() -> None:
    """FunctionsDeploy も gate が読む `{WORK}ac-verification.md` を必須成果物にする。"""
    text = _read(_FUNCTIONS_DEPLOY)

    assert "{WORK}ac-verification.md" in text
    assert "artifacts/" in text
    assert "置かない" in text or "配下に置かない" in text


def test_functions_deploy_requires_ac2_ac3_green() -> None:
    """FunctionsDeploy の実在系 AC-2/AC-3 は ✅ のみ許容する。"""
    text = _read(_FUNCTIONS_DEPLOY)

    assert "AC-2" in text
    assert "AC-3" in text
    assert "✅" in text
    assert "NEEDS-VERIFICATION" in text
    assert "success" in text or "成功" in text


# ---------------------------------------------------------------------------
# 実装言語の契約（FR-WF-ADFDV-03）
# ---------------------------------------------------------------------------

_SERVICE_CODING = _PROMPTS / "Dev-Dataflow-ServiceCoding.prompt.md"
_TEST_CODING = _PROMPTS / "Dev-Dataflow-TestCoding.prompt.md"
_TEMPLATES = _REPO_ROOT / ".github" / "prompts" / "steps" / "adfdv"

# 言語契約を持つファイル。Prompt・body テンプレートに加え、Cloud reusable workflow の
# inline Issue body も対象にする（どこかに .NET 記述が残ると Agent へ矛盾した指示が渡るため）。
_LANGUAGE_CONTRACT_FILES = [
    _SERVICE_CODING,
    _TEST_CODING,
    _FUNCTIONS_DEPLOY,
    _TEMPLATES / "step-2.1.prompt.md",
    _TEMPLATES / "step-2.2.prompt.md",
    _REPO_ROOT / ".github" / "workflows" / "auto-dataflow-dev-reusable.yml",
]

# .NET 固有トークン。1 つでも残っていれば Python 化が不完全。
_DOTNET_TOKENS = ("dotnet ", "xUnit", ".csproj", "C#", "NuGet")


def test_dataflow_default_language_is_python() -> None:
    text = _read(_SERVICE_CODING)

    assert "Python" in text
    assert "pytest" in text


def test_dataflow_test_coding_uses_pytest() -> None:
    text = _read(_TEST_CODING)

    assert "pytest" in text
    assert "requirements" in text or "pyproject" in text


def test_dataflow_language_rationale_names_target_platforms() -> None:
    """Python を選ぶ根拠（実行プラットフォームの選択肢）を Prompt に明示する。"""
    text = _read(_SERVICE_CODING)

    for platform in ("Spark", "Microsoft Fabric", "Databricks"):
        assert platform in text, f"実行プラットフォーム {platform} の記載がない"


def test_no_dotnet_tokens_remain_in_dataflow_contracts() -> None:
    remaining: list[str] = []
    for path in _LANGUAGE_CONTRACT_FILES:
        text = _read(path)
        for token in _DOTNET_TOKENS:
            if token in text:
                remaining.append(f"{path.name}: {token!r}")
    assert remaining == [], f".NET 固有の記述が残っています: {remaining}"
