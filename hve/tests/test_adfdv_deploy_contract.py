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
