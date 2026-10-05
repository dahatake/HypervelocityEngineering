"""FR-CLI-104: 自己改善（Self-Improve）機能が全版から削除されていること。"""

from __future__ import annotations

import dataclasses
import importlib
import importlib.util
from pathlib import Path

import pytest

from hve.__main__ import _build_parser
from hve.config import SDKConfig

_HVE_DIR = Path(__file__).resolve().parent.parent
_OLD_FLAGS = (
    ["--self-improve"],
    ["--no-self-improve"],
    ["--self-improve-max-iterations", "3"],
    ["--self-improve-target-scope", "src/"],
    ["--self-improve-goal", "x"],
)


def test_self_improve_module_is_deleted() -> None:
    assert not (_HVE_DIR / "self_improve.py").exists()
    assert importlib.util.find_spec("hve.self_improve") is None


@pytest.mark.parametrize("flag", _OLD_FLAGS)
def test_orchestrate_rejects_removed_flags(flag: list[str], capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        _build_parser().parse_args(["orchestrate", "-w", "aas", *flag])
    assert raised.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_sdk_config_has_no_self_improve_fields() -> None:
    names = {field.name for field in dataclasses.fields(SDKConfig)}
    assert not [name for name in names if "self_improve" in name]


def test_environment_variables_are_ignored(monkeypatch) -> None:
    monkeypatch.setenv("HVE_AUTO_SELF_IMPROVE", "true")
    monkeypatch.setenv("HVE_SELF_IMPROVE_SCOPE", "step")
    monkeypatch.setenv("HVE_APPLY_SELF_IMPROVE_TO_MAIN", "false")
    cfg = SDKConfig.from_env()
    assert not hasattr(cfg, "auto_self_improve")
    assert not hasattr(cfg, "self_improve_scope")
    assert not hasattr(cfg, "apply_self_improve_to_main")


@pytest.mark.parametrize("module_name", ["hve.runner", "hve.orchestrator", "hve.prompts"])
def test_runtime_modules_have_no_self_improve_references(module_name: str) -> None:
    source = Path(importlib.import_module(module_name).__file__).read_text(encoding="utf-8")
    assert "self_improve" not in source
    assert "SELF_IMPROVE" not in source
    assert "Self-Improve" not in source


def test_prompt_directory_has_no_self_improve_prompts() -> None:
    root = _HVE_DIR.parent / ".github" / "prompts"
    assert not (root / "runtime" / "self-improve").exists()
    assert (root / "runtime" / "review" / "main-artifact-apply.prompt.md").is_file()
