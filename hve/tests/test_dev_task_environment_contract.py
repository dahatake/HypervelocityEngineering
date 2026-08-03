"""Repository test dependency and VS Code task environment contract."""
from __future__ import annotations

import json
from pathlib import Path
import re
import tomllib


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_TASKS = _REPO_ROOT / ".vscode" / "tasks.json"
_WORKSPACE_SETTINGS = _REPO_ROOT / ".vscode" / "settings.json"
_COPILOT_INSTRUCTIONS = _REPO_ROOT / ".github" / "copilot-instructions.md"
_SETUP_CMD = _REPO_ROOT / "hve" / "setup-hve.cmd"
_SETUP_PS1 = _REPO_ROOT / "hve" / "setup-hve.ps1"
_SETUP_SH = _REPO_ROOT / "hve" / "setup-hve.sh"
_WORKSPACE_PYTHON = "${workspaceFolder}\\.venv\\Scripts\\python.exe"
_PERMANENT_TASK_LABELS = {
    "Sub-17 Orchestrator RED contracts",
    "T09 Regenerate Step 1.2 verifier",
    "T09 Verify Bash and ShellCheck",
    "T09 Verify artifact contract",
    "T09 Verify LF and BOM",
    "T09 Run verifier contract tests",
    "T09 RED contract tests",
    "T09 Regenerate Step 1.2 verifier v2",
}


def test_pyproject_declares_pytest_test_extra() -> None:
    project = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]
    extras = project["optional-dependencies"]

    assert "test" in extras
    assert any(requirement.startswith("pytest>=") for requirement in extras["test"])


def test_normal_setup_installs_test_extra_but_minimal_remains_base_only() -> None:
    powershell = _SETUP_PS1.read_text(encoding="utf-8")
    shell = _SETUP_SH.read_text(encoding="utf-8")

    ps_extras_match = re.search(r"\$extras\s*=\s*@\((?P<values>[^)]*)\)", powershell)
    assert ps_extras_match is not None
    ps_extras = set(re.findall(r"'([^']+)'", ps_extras_match.group("values")))
    assert {"test", "mdq-watch", "mdq-ja", "semantic"}.issubset(ps_extras)
    sh_extras_match = re.search(r'^\s*extras="(?P<values>[^"]+)"$', shell, re.MULTILINE)
    assert sh_extras_match is not None
    sh_extras = set(sh_extras_match.group("values").split(","))
    assert {"test", "mdq-watch", "mdq-ja", "semantic"}.issubset(sh_extras)
    assert re.search(
        r'\$target\s*=\s*"\.\["\s*\+\s*\(\$extras\s+-join\s+[\'\"]?,[\'\"]?\)'
        r'\s*\+\s*"\]"',
        powershell,
    )
    assert re.search(
        r"Invoke-Checked\s+-Exe\s+\$venvPy\s+-ArgList\s+@\(\s*"
        r"'-m'\s*,\s*'pip'\s*,\s*'install'\s*,\s*'-e'\s*,\s*\$target\s*\)",
        powershell,
    )
    assert "Installing HVE (base only, no extras)" in powershell
    assert "Installing HVE (base only, no extras)" in shell


def test_windows_automation_uses_pwsh_without_legacy_fallback() -> None:
    settings = json.loads(_WORKSPACE_SETTINGS.read_text(encoding="utf-8"))
    setup_cmd = _SETUP_CMD.read_text(encoding="utf-8")
    setup_ps1 = _SETUP_PS1.read_text(encoding="utf-8")
    instructions = _COPILOT_INSTRUCTIONS.read_text(encoding="utf-8")

    assert settings["terminal.integrated.defaultProfile.windows"] == "PowerShell (Latest)"
    assert settings["terminal.integrated.profiles.windows"]["Windows PowerShell"] is None
    assert settings["terminal.integrated.profiles.windows"]["PowerShell (Latest)"]["path"] == "pwsh.exe"
    assert settings["terminal.integrated.automationProfile.windows"]["path"] == "pwsh.exe"
    assert "pwsh.exe -NoLogo -NoProfile" in setup_cmd
    executable_lines = [
        line.strip()
        for line in setup_cmd.splitlines()
        if line.strip() and not line.lstrip().upper().startswith("REM ")
    ]
    assert not any(
        re.search(
            r"(?i)(?:^\s*|[`(&|;]\s*)powershell(?:\.exe)?\s+-",
            line,
        )
        for line in executable_lines
    )
    assert "$PSVersionTable.PSEdition -ne 'Core'" in setup_ps1
    assert "Windows PowerShell 5.1 の直接実行・フォールバックは禁止" in instructions


def test_vscode_python_tasks_use_workspace_venv_without_absolute_repo_path() -> None:
    data = json.loads(_TASKS.read_text(encoding="utf-8"))
    tasks = data["tasks"]
    python_tasks = [
        task
        for task in tasks
        if str(task.get("command", "")).lower().endswith("python.exe")
    ]

    assert python_tasks
    assert all(task["command"] == _WORKSPACE_PYTHON for task in python_tasks)
    assert not any(
        str(task.get("command", "")).startswith("C:\\GitHub\\")
        for task in tasks
    )
    pytest_labels = {
        task["label"]
        for task in python_tasks
        if "pytest" in task.get("args", [])
    }
    assert {
        "Sub-17 Orchestrator RED contracts",
        "T09 Run verifier contract tests",
        "T09 RED contract tests",
    }.issubset(pytest_labels)
    all_labels = [task["label"] for task in tasks]
    assert len(all_labels) == len(set(all_labels))
    assert set(all_labels) == _PERMANENT_TASK_LABELS
    assert not any(
        label.strip().casefold().startswith("temp ")
        for label in all_labels
    ), "temporary validation tasks must be removed after use"
