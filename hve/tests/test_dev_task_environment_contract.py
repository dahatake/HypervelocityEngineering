"""Repository test dependency and VS Code task environment contract."""
from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import textwrap
import tomllib
from typing import NamedTuple, Optional


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_TASKS = _REPO_ROOT / ".vscode" / "tasks.json"
_WORKSPACE_SETTINGS = _REPO_ROOT / ".vscode" / "settings.json"
_COPILOT_INSTRUCTIONS = _REPO_ROOT / ".github" / "copilot-instructions.md"
_SETUP_CMD = _REPO_ROOT / "hve" / "setup-hve.cmd"
_SETUP_PS1 = _REPO_ROOT / "hve" / "setup-hve.ps1"
_SETUP_SH = _REPO_ROOT / "hve" / "setup-hve.sh"
_COPILOT_SDK_LOCK = _REPO_ROOT / "hve" / "copilot-sdk.lock"
_PYTHON_TEST_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "test-hve-python.yml"
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


# `code` と言語別 extras は同じ pin を二重に持つため、片方だけ更新すると drift する。
_LANGUAGE_CODE_EXTRAS = (
    "code-python", "code-csharp", "code-javascript", "code-typescript",
    "code-java", "code-go", "code-rust", "code-c", "code-cpp", "code-scala",
    "code-shell", "code-powershell", "code-batch", "code-sqlglot",
)


def test_code_extra_equals_the_union_of_the_language_extras() -> None:
    extras = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]["optional-dependencies"]

    union: set[str] = set()
    for name in _LANGUAGE_CODE_EXTRAS:
        assert name in extras, name
        union |= set(extras[name])

    assert union == set(extras["code"])


def test_cq_optional_dependencies_do_not_borrow_the_mdq_extras() -> None:
    """`cq watch` とトークン計測は cq 側の extras で完結しなければならない（FR-CQ-01）。"""
    extras = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]["optional-dependencies"]

    assert any(r.startswith("watchdog>=") for r in extras["code-watch"])
    assert any(r.startswith("tiktoken>=") for r in extras["code-tokenizer"])


def test_setup_scripts_offer_exactly_the_language_extras() -> None:
    """`-CodeLanguages` / `--code-languages` の受理名は言語別 extras と 1 対 1 で対応する。

    利用者が打つのは `sql` だが、sqlfluff 用の既存 `code-sql` と衝突するため
    extras 名だけ `code-sqlglot` へ写す。
    """
    block = re.search(
        r"\$CodeLanguageExtras = \[ordered\]@\{(.+?)^\}",
        _SETUP_PS1.read_text(encoding="utf-8"),
        re.DOTALL | re.MULTILINE,
    )
    assert block is not None, "setup-hve.ps1 に $CodeLanguageExtras が見つからない"
    ps1_map = dict(re.findall(r"(\w+)\s*=\s*'(code-[\w-]+)'", block.group(1)))

    sh_text = _SETUP_SH.read_text(encoding="utf-8")
    sh_names_match = re.search(r'CODE_LANGUAGE_NAMES="([^"]+)"', sh_text)
    assert sh_names_match is not None, "setup-hve.sh に CODE_LANGUAGE_NAMES が見つからない"
    sh_names = set(sh_names_match.group(1).split())

    expected = {name.removeprefix("code-") for name in _LANGUAGE_CODE_EXTRAS} - {"sqlglot"} | {"sql"}
    assert set(ps1_map) == expected
    assert sh_names == expected

    # `sql` の写像は両スクリプトで同じでなければ、片方だけ存在しない extras を叩く。
    assert ps1_map["sql"] == "code-sqlglot"
    assert "code-sqlglot" in sh_text


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


def test_setup_scripts_verify_copilot_runtime_pin_consistency() -> None:
    """setup が SDK の pin する Copilot ランタイムとの整合を検証する契約。

    github-copilot-sdk の生成イベントパーサはエンベロープ (id/timestamp/type) を
    assert で固めているため、pin と異なるランタイムを掴むと session.event が
    AssertionError となり当該イベントが黙って捨てられる。
    """
    for path in (_SETUP_PS1, _SETUP_SH):
        script = path.read_text(encoding="utf-8")
        assert "Verifying Copilot runtime consistency" in script, path.name
        assert "download-runtime" in script, path.name
        for bypass_var in (
            "COPILOT_CLI_PATH",
            "COPILOT_CLI_EXTRACT_DIR",
            "COPILOT_SKIP_CLI_DOWNLOAD",
        ):
            assert bypass_var in script, f"{path.name}: {bypass_var}"


def test_setup_scripts_read_copilot_version_only_with_no_auto_update() -> None:
    """`copilot --version` 単体はオンライン更新チェックの結果 (最新利用可能版) を返す。

    実測: `cli/1.0.69/copilot.exe --version` -> 1.0.78 /
    `--no-auto-update --version` -> 1.0.69。pin との突合には後者が必須。
    """
    powershell = _SETUP_PS1.read_text(encoding="utf-8")
    shell = _SETUP_SH.read_text(encoding="utf-8")

    assert "function Get-CopilotCliVersion" in powershell
    assert re.search(r"'--no-auto-update'\s*,?\s*'--version'", powershell)
    assert "cli_embedded_version()" in shell
    assert re.search(r"--no-auto-update\s+--version", shell)


def test_copilot_sdk_lock_pins_an_exact_version() -> None:
    """SDK 版は lock で固定する。setup 実行日でマシンごとに版が変わるのを防ぐため。"""
    text = _COPILOT_SDK_LOCK.read_text(encoding="utf-8")

    assert re.search(r"(?m)^github-copilot-sdk==\S+$", text)
    assert re.search(r"(?m)^# pinned Copilot CLI runtime: \S+$", text)
    assert not text.startswith("\ufeff")
    # `Path.read_text(newline=...)` は 3.13 以降にしか無いため、生バイトで判定する。
    assert b"\r\n" not in _COPILOT_SDK_LOCK.read_bytes()


def test_setup_pins_the_copilot_sdk_only_behind_an_explicit_flag() -> None:
    """FR-MODEL-07: 既定は最新追従。lock 版固定と lock 書き換えは明示フラグの内側だけ。"""
    powershell = _SETUP_PS1.read_text(encoding="utf-8")
    shell = _SETUP_SH.read_text(encoding="utf-8")

    assert "copilot-sdk.lock" in powershell
    assert "copilot-sdk.lock" in shell
    assert re.search(
        r"'install'\s*,\s*'--no-deps'\s*,\s*'-r'\s*,\s*\$lockFile", powershell
    )
    assert re.search(r"pip install --no-deps -r \"\$LOCK_FILE\"", shell)

    assert "[switch]$PinSdk" in powershell
    assert re.search(r"--pin-sdk\)\s+PIN_SDK=true", shell)
    assert "[switch]$UpgradeSdk" in powershell
    assert "--upgrade-sdk) UPGRADE_SDK=true" in shell
    # 版固定と lock 書き換えは必ずフラグの内側に置く（既定経路は最新へ追従する）。
    assert 'if ($PinSdk) {' in powershell
    assert 'if [[ "$PIN_SDK" == true ]]; then' in shell
    assert 'if ($UpgradeSdk) {' in powershell
    assert 'if [[ "$UPGRADE_SDK" == true ]]; then' in shell


_COPILOT_CLI_PACKAGE = "@github/copilot@latest"


def test_setup_scripts_install_the_latest_copilot_cli() -> None:
    """FR-MODEL-08: 3 OS 共通で外部 copilot CLI を最新版へ導入・更新する。

    npm グローバル管理下でない ``copilot`` へ npm 導入を重ねると PATH 解決が
    分岐するため、その場合は導入せず警告と手動更新手順だけを提示する。
    """
    powershell = _SETUP_PS1.read_text(encoding="utf-8")
    shell = _SETUP_SH.read_text(encoding="utf-8")

    powershell_packages = re.findall(
        r"'install'\s*,\s*'-g'\s*,\s*'(@github/copilot[^']*)'", powershell
    )
    shell_packages = re.findall(r"npm install -g (@github/copilot[\w@./-]*)", shell)
    assert powershell_packages
    assert shell_packages
    assert all(package == _COPILOT_CLI_PACKAGE for package in powershell_packages), (
        powershell_packages
    )
    assert all(package == _COPILOT_CLI_PACKAGE for package in shell_packages), (
        shell_packages
    )

    for name, script in ((_SETUP_PS1.name, powershell), (_SETUP_SH.name, shell)):
        assert "Installing the latest GitHub Copilot CLI" in script, name
        assert f"npm install -g {_COPILOT_CLI_PACKAGE}" in script, name
        assert "not managed by npm" in script, name


_CALL_SEPARATOR = "\x1f"
_PTY_PROBE_MARKER = "__HVE_TEST_PTY_PROBE__"
_PTY_AST_PROBE = (
    "import ast,os;"
    "tree=ast.parse(os.environ.get('HVE_TEST_CODE',''));"
    "raise SystemExit(0 if any("
    "isinstance(node,ast.Call) and ("
    "(isinstance(node.func,ast.Name) and node.func.id=='is_pty_available') or "
    "(isinstance(node.func,ast.Attribute) and node.func.attr=='is_pty_available')"
    ") for node in ast.walk(tree)) else 1)"
)
_SETUP_COMMON_SHELL_ARGS = (
    "--no-install-tools",
    "--no-global-cleanup",
    "--skip-nltk-download",
    "--yes",
)
_SETUP_COMMON_POWERSHELL_ARGS = (
    "-NoInstallTools",
    "-NoGlobalCleanup",
    "-SkipNltkDownload",
    "-Yes",
)


class _SetupRun(NamedTuple):
    returncode: int
    stdout: str
    stderr: str
    calls: tuple[tuple[str, ...], ...]
    gh_calls: tuple[str, ...]


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | 0o111)


def _read_call_records(path: Path) -> tuple[tuple[str, ...], ...]:
    if not path.exists():
        return ()
    return tuple(
        tuple(line.split(_CALL_SEPARATOR))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    )


def _read_lines(path: Path) -> tuple[str, ...]:
    if not path.exists():
        return ()
    return tuple(line for line in path.read_text(encoding="utf-8").splitlines() if line)


def _record_has(record: tuple[str, ...], *values: str) -> bool:
    return all(any(value in field for field in record[1:]) for value in values)


def _has_gui_pty_install(calls: tuple[tuple[str, ...], ...]) -> bool:
    return any(_record_has(record, "pip", "install", "gui-pty") for record in calls)


def _has_pip_install(calls: tuple[tuple[str, ...], ...]) -> bool:
    return any(_record_has(record, "pip", "install") for record in calls)


def _has_latest_sdk_upgrade(calls: tuple[tuple[str, ...], ...]) -> bool:
    return any(
        _record_has(record, "pip", "install", "--upgrade", "github-copilot-sdk")
        for record in calls
    )


def _touched_sdk_lock(calls: tuple[tuple[str, ...], ...]) -> bool:
    return any(
        any("copilot-sdk.lock" in field for field in record[1:]) for record in calls
    )


def _has_locked_sdk_install(calls: tuple[tuple[str, ...], ...]) -> bool:
    return any(
        _record_has(record, "pip", "install", "-r", "copilot-sdk.lock")
        for record in calls
    )


def _has_shared_pty_probe(calls: tuple[tuple[str, ...], ...]) -> bool:
    return any(_PTY_PROBE_MARKER in record for record in calls)


def _created_venv(calls: tuple[tuple[str, ...], ...]) -> bool:
    return any(
        any(
            record[index : index + 2] == ("-m", "venv")
            for index in range(1, len(record) - 1)
        )
        for record in calls
    )


def _run_summary(label: str, run: _SetupRun) -> str:
    stdout = "\n".join(run.stdout.splitlines()[-12:])
    stderr = "\n".join(run.stderr.splitlines()[-12:])
    return f"{label}: exit={run.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"


@lru_cache(maxsize=1)
def _bash_executable() -> str:
    candidates: list[str | None] = []
    if os.name == "nt":
        for root_name in ("ProgramFiles", "ProgramW6432", "LOCALAPPDATA"):
            root = os.environ.get(root_name)
            if root:
                candidates.append(str(Path(root) / "Git" / "bin" / "bash.exe"))
    candidates.extend((shutil.which("bash.exe"), shutil.which("bash")))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise AssertionError("bash is required to execute the isolated setup-hve.sh harness")


@lru_cache(maxsize=1)
def _pwsh7_executable() -> str | None:
    if os.name != "nt":
        return None
    candidates = (shutil.which("pwsh.exe"), shutil.which("pwsh"))
    for candidate in candidates:
        if not candidate:
            continue
        probe = subprocess.run(
            [
                candidate,
                "-NoLogo",
                "-NoProfile",
                "-Command",
                "$PSVersionTable.PSEdition + ':' + $PSVersionTable.PSVersion.Major",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if probe.returncode == 0 and probe.stdout.strip().startswith("Core:"):
            if int(probe.stdout.strip().split(":", 1)[1]) >= 7:
                return str(Path(candidate).resolve())
    return None


def _mirror_without(source: Path, sandbox: Path, hidden: tuple[str, ...]) -> Path:
    """Expose ``source`` minus ``hidden`` so ``command -v`` cannot reach the host tool.

    The PowerShell harness drops whole directories instead, which is not viable on
    POSIX because /usr/bin also carries the tools the script legitimately needs.
    """
    sandbox.mkdir(parents=True, exist_ok=True)
    for entry in sorted(source.iterdir()):
        link = sandbox / entry.name
        if entry.name in hidden or link.exists() or link.is_symlink():
            continue
        try:
            link.symlink_to(entry)
        except OSError as exc:  # 握り潰すと隠したい以外のツールが黙って消える。
            raise AssertionError(f"cannot mirror {entry} into {sandbox}: {exc}") from exc
    return sandbox


def _shell_test_path(
    fake_bin: Path,
    bash: str,
    *,
    sandbox: Optional[Path] = None,
    hidden: tuple[str, ...] = (),
) -> str:
    paths = [fake_bin, Path(bash).parent]
    if os.name == "nt":
        git_root = Path(bash).parent.parent
        paths.extend((git_root / "usr" / "bin", git_root / "mingw64" / "bin"))
    else:
        paths.extend((Path("/usr/bin"), Path("/bin")))

    resolved: list[Path] = []
    for path in dict.fromkeys(paths):
        if not path.is_dir():
            continue
        # GitHub-hosted runners ship `gh` in /usr/bin, so keeping the directory on PATH
        # would make the "missing prerequisite" branches unreachable. Windows keeps the
        # directories as-is because the Git-for-Windows bin dirs carry no such tool and
        # symlink creation there needs extra privileges.
        if (
            os.name == "nt"
            or sandbox is None
            or not hidden
            or path == fake_bin
            or not any((path / name).exists() for name in hidden)
        ):
            resolved.append(path)
            continue
        resolved.append(_mirror_without(path, sandbox, hidden))
    return os.pathsep.join(str(path) for path in dict.fromkeys(resolved))


def _powershell_test_path(fake_bin: Path) -> str:
    """Preserve the pwsh runtime PATH while hiding test-owned external tools."""
    paths = [fake_bin]
    for raw_path in os.environ.get("PATH", "").split(os.pathsep):
        if not raw_path:
            continue
        path = Path(raw_path)
        if any(
            (path / name).is_file()
            for name in (
                "gh.exe",
                "gh.cmd",
                "gh.bat",
                "copilot.exe",
                "copilot.cmd",
                "copilot.bat",
            )
        ):
            continue
        paths.append(path)
    if Path(sys.executable).parent not in paths:
        paths.insert(1, Path(sys.executable).parent)
    return os.pathsep.join(str(path) for path in dict.fromkeys(paths))


def _run_shell_setup(
    root: Path,
    *,
    args: tuple[str, ...] = (),
    gh_available: bool,
    pty_available: bool,
    gh_status_exit: int = 0,
) -> _SetupRun:
    repo = root / "repo"
    setup = repo / "hve" / "setup-hve.sh"
    fake_bin = root / "fake-bin"
    calls = root / "python-calls.log"
    gh_calls = root / "gh-calls.log"
    venv_python = repo / ".venv" / "bin" / "python"
    repo.joinpath("hve").mkdir(parents=True)
    shutil.copyfile(_SETUP_SH, setup)
    setup.chmod(setup.stat().st_mode | 0o111)
    if _COPILOT_SDK_LOCK.exists():
        shutil.copyfile(_COPILOT_SDK_LOCK, repo / "hve" / "copilot-sdk.lock")

    fake_python = textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        set -u
        code=''
        if [[ "${{1:-}}" == '-c' && $# -ge 2 ]]; then
          code="$2"
        elif [[ "${{1:-}}" == '-' ]]; then
          code="$(cat)"
        fi
        pty_probe=false
        if [[ "$code" == *is_pty_available* ]] &&
           HVE_TEST_CODE="$code" "$HVE_TEST_HOST_PY" -c "$HVE_TEST_AST_PROBE" >/dev/null 2>&1; then
          pty_probe=true
        fi
        {{
          printf '%s' "${{0##*/}}"
          for arg in "$@"; do
            safe="${{arg//$'\\r'/\\\\r}}"
            safe="${{safe//$'\\n'/\\\\n}}"
            printf '\037%s' "$safe"
          done
          if [[ "${{1:-}}" == '-' ]]; then
            safe="${{code//$'\\r'/\\\\r}}"
            safe="${{safe//$'\\n'/\\\\n}}"
            printf '\037stdin=%s' "$safe"
          fi
          if [[ "$pty_probe" == true ]]; then printf '\037%s' '{_PTY_PROBE_MARKER}'; fi
          printf '\n'
        }} >> "$HVE_TEST_CALL_LOG"
        if [[ "$pty_probe" == true ]]; then exit "${{HVE_TEST_PTY_EXIT:-0}}"; fi
        if [[ "${{1:-}}" == '--version' ]]; then printf 'Python 3.14.0\n'; fi
        if [[ "${{1:-}}" == '-m' && "${{2:-}}" == 'pip' &&
              "${{3:-}}" == 'show' && "${{4:-}}" == 'hve' ]]; then
          exit 1
        fi
        exit 0
        """
    )
    _write_executable(venv_python, fake_python)
    _write_executable(fake_bin / "python3.14", fake_python)
    _write_executable(
        fake_bin / "uname",
        "#!/usr/bin/env bash\nprintf 'Darwin\\n'\n",
    )
    if gh_available:
        _write_executable(
            fake_bin / "gh",
            """#!/usr/bin/env bash
set -u
printf '%s\\n' "$*" >> "$HVE_TEST_GH_LOG"
if [[ "${1:-}" == 'auth' && "${2:-}" == 'status' ]]; then
  exit "${HVE_TEST_GH_STATUS_EXIT:-0}"
fi
exit 0
""",
        )

    bash = _bash_executable()
    env = os.environ.copy()
    env.update(
        {
            "PATH": _shell_test_path(
                fake_bin,
                bash,
                sandbox=root / "sandbox-bin",
                hidden=() if gh_available else ("gh",),
            ),
            "HVE_TEST_AST_PROBE": _PTY_AST_PROBE,
            "HVE_TEST_CALL_LOG": calls.as_posix(),
            "HVE_TEST_GH_LOG": gh_calls.as_posix(),
            "HVE_TEST_GH_STATUS_EXIT": str(gh_status_exit),
            "HVE_TEST_HOST_PY": Path(sys.executable).as_posix(),
            "HVE_TEST_PTY_EXIT": "0" if pty_available else "1",
        }
    )
    completed = subprocess.run(
        [bash, setup.as_posix(), *_SETUP_COMMON_SHELL_ARGS, *args],
        cwd=repo,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return _SetupRun(
        completed.returncode,
        completed.stdout,
        completed.stderr,
        _read_call_records(calls),
        _read_lines(gh_calls),
    )


def _instrument_powershell_venv_python(source: str) -> str:
    assignment = re.compile(
        r"(?m)^\$venvPy\s*=\s*Join-Path\s+\$venvDir\s+"
        r"(['\"])Scripts\\python\.exe\1\s*$"
    )
    replacement = textwrap.dedent(
        f"""\
        function Invoke-HveTestVenvPython {{
            [CmdletBinding()]
            param([Parameter(ValueFromRemainingArguments = $true)][object[]]$FakeArgs)

            $code = ''
            if ($FakeArgs.Count -ge 2 -and [string]$FakeArgs[0] -eq '-c') {{
                $code = [string]$FakeArgs[1]
            }}
            $isPtyProbe = $false
            if ($code.Contains('is_pty_available')) {{
                $previousCode = [Environment]::GetEnvironmentVariable('HVE_TEST_CODE', 'Process')
                try {{
                    $env:HVE_TEST_CODE = $code
                    & $env:HVE_TEST_HOST_PY -c $env:HVE_TEST_AST_PROBE *> $null
                    $isPtyProbe = ($LASTEXITCODE -eq 0)
                }} finally {{
                    if ($null -eq $previousCode) {{
                        Remove-Item Env:HVE_TEST_CODE -ErrorAction SilentlyContinue
                    }} else {{
                        $env:HVE_TEST_CODE = $previousCode
                    }}
                }}
            }}

            $parts = [System.Collections.Generic.List[string]]::new()
            $parts.Add('venv-python')
            foreach ($arg in @($FakeArgs)) {{
                $text = ([string]$arg).Replace("`r", '\r').Replace("`n", '\n')
                $parts.Add($text)
            }}
            if ($isPtyProbe) {{ $parts.Add('{_PTY_PROBE_MARKER}') }}
            Add-Content -LiteralPath $env:HVE_TEST_CALL_LOG -Value ($parts -join [char]31)
            $global:LASTEXITCODE = if ($isPtyProbe) {{ [int]$env:HVE_TEST_PTY_EXIT }} else {{ 0 }}
        }}
        $venvPy = 'Invoke-HveTestVenvPython'
        """
    )
    instrumented, replacements = assignment.subn(lambda _: replacement, source)
    assert replacements == 1, (
        "PowerShell harness must instrument exactly one $venvPy assignment; "
        f"found {replacements}"
    )
    return instrumented


def _run_powershell_setup(
    root: Path,
    *,
    args: tuple[str, ...] = (),
    gh_available: bool,
    pty_available: bool,
    gh_status_exit: int = 0,
) -> _SetupRun | None:
    pwsh = _pwsh7_executable()
    if pwsh is None:
        return None

    repo = root / "repo"
    setup = repo / "hve" / "setup-hve.ps1"
    fake_bin = root / "fake-bin"
    calls = root / "python-calls.log"
    gh_calls = root / "gh-calls.log"
    repo.joinpath("hve").mkdir(parents=True)
    fake_bin.mkdir(parents=True)
    setup.write_text(
        _instrument_powershell_venv_python(_SETUP_PS1.read_text(encoding="utf-8")),
        encoding="utf-8",
        newline="\n",
    )
    if _COPILOT_SDK_LOCK.exists():
        shutil.copyfile(_COPILOT_SDK_LOCK, repo / "hve" / "copilot-sdk.lock")
    repo.joinpath(".venv", "Scripts").mkdir(parents=True)
    repo.joinpath("Invoke-HveTestVenvPython").write_text(
        "existing venv marker\n", encoding="utf-8"
    )

    if gh_available:
        (fake_bin / "gh.cmd").write_bytes(
            (
                "@echo off\r\n"
                ">>\"%HVE_TEST_GH_LOG%\" echo %*\r\n"
                "if /I \"%~1\"==\"auth\" if /I \"%~2\"==\"status\" "
                "exit /b %HVE_TEST_GH_STATUS_EXIT%\r\n"
                "exit /b 0\r\n"
            ).encode("ascii")
        )
    fake_global_python = (
        "@echo off\r\n"
        "if \"%~1\"==\"-3.14\" shift\r\n"
        "if \"%~1\"==\"--version\" (echo Python 3.14.0& exit /b 0)\r\n"
        "if \"%~1\"==\"-m\" if \"%~2\"==\"pip\" "
        "if \"%~3\"==\"show\" exit /b 1\r\n"
        "if \"%~1\"==\"-c\" echo {\"site\":[],\"scripts\":[]}\r\n"
        "exit /b 0\r\n"
    ).encode("ascii")
    (fake_bin / "py.cmd").write_bytes(fake_global_python)
    (fake_bin / "python.cmd").write_bytes(fake_global_python)
    (fake_bin / "python3.cmd").write_bytes(fake_global_python)
    (fake_bin / "copilot.cmd").write_bytes(
        b"@echo off\r\necho 1.0.0\r\nexit /b 0\r\n"
    )

    env = os.environ.copy()
    env.update(
        {
            "PATH": _powershell_test_path(fake_bin),
            "HVE_TEST_AST_PROBE": _PTY_AST_PROBE,
            "HVE_TEST_CALL_LOG": str(calls),
            "HVE_TEST_GH_LOG": str(gh_calls),
            "HVE_TEST_GH_STATUS_EXIT": str(gh_status_exit),
            "HVE_TEST_HOST_PY": sys.executable,
            "HVE_TEST_PTY_EXIT": "0" if pty_available else "1",
        }
    )
    completed = subprocess.run(
        [pwsh, "-NoLogo", "-NoProfile", "-File", str(setup),
         *_SETUP_COMMON_POWERSHELL_ARGS, *args],
        cwd=repo,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=45,
    )
    return _SetupRun(
        completed.returncode,
        completed.stdout,
        completed.stderr,
        _read_call_records(calls),
        _read_lines(gh_calls),
    )


def _cmd_executable_lines(script: str) -> list[str]:
    return [
        stripped
        for line in script.splitlines()
        if (stripped := line.strip())
        and not stripped.upper().startswith("REM ")
        and not stripped.startswith("::")
    ]


def _cmd_propagates_pwsh_exit(script: str) -> bool:
    """Check executable cmd statements without fixing whitespace or ``@pwsh`` form."""
    lines = _cmd_executable_lines(script)
    for invoke_index, line in enumerate(lines):
        if not re.search(r"(?i)(?:^|[\s@])pwsh(?:\.exe)?\b.*\s-File\b", line):
            continue
        for capture_index in range(invoke_index + 1, min(len(lines), invoke_index + 4)):
            direct = re.search(
                r"(?i)\bexit\s+/b\s+%ERRORLEVEL%(?:\s|$)", lines[capture_index]
            )
            if direct:
                return True
            captured = re.search(
                r"(?i)^set\s+\"?([A-Z_][A-Z0-9_]*)=%ERRORLEVEL%\"?$",
                lines[capture_index],
            )
            if not captured:
                continue
            variable = re.escape(captured.group(1))
            return any(
                re.search(rf"(?i)\bexit\s+/b\s+%{variable}%(?:\s|$)", later)
                for later in lines[capture_index + 1 :]
            )
    return False


def _run_cmd_exit_probe(root: Path, expected_exit: int) -> int | None:
    pwsh = _pwsh7_executable()
    cmd = shutil.which("cmd.exe") if os.name == "nt" else None
    if pwsh is None or cmd is None:
        return None
    root.mkdir(parents=True, exist_ok=True)
    wrapper = root / "setup-hve.cmd"
    script = root / "setup-hve.ps1"
    shutil.copyfile(_SETUP_CMD, wrapper)
    script.write_text(f"exit {expected_exit}\n", encoding="utf-8", newline="\n")
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join((str(Path(pwsh).parent), env.get("PATH", "")))
    completed = subprocess.run(
        [cmd, "/d", "/c", str(wrapper), "sentinel"],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return completed.returncode


def test_normal_gui_setup_installs_gh_and_platform_pty_backend(tmp_path: Path) -> None:
    """FR-GUI-09: normal setup provisions and verifies each platform backend."""
    project = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]
    gui_pty = [
        re.sub(r"\s+", "", requirement).casefold()
        for requirement in project["optional-dependencies"]["gui-pty"]
    ]
    setup_cmd = _SETUP_CMD.read_text(encoding="utf-8")

    assert any(
        requirement.startswith("pywinpty") and "sys_platform=='win32'" in requirement
        for requirement in gui_pty
    )
    assert any(
        requirement.startswith("ptyprocess") and "sys_platform!='win32'" in requirement
        for requirement in gui_pty
    )

    probe_env = os.environ.copy()
    for source, expected in (
        ("is_pty_available()", True),
        ("# is_pty_available()", False),
        ("payload = '''is_pty_available()'''", False),
    ):
        probe_env["HVE_TEST_CODE"] = source
        probe = subprocess.run(
            [sys.executable, "-c", _PTY_AST_PROBE],
            env=probe_env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert (probe.returncode == 0) is expected, source

    runs: list[tuple[str, _SetupRun]] = [
        (
            "setup-hve.sh normal GUI",
            _run_shell_setup(
                tmp_path / "shell-normal", gh_available=True, pty_available=True
            ),
        )
    ]
    powershell_run = _run_powershell_setup(
        tmp_path / "powershell-normal", gh_available=True, pty_available=True
    )
    if powershell_run is not None:
        runs.append(("setup-hve.ps1 normal GUI", powershell_run))

    gaps: list[str] = []
    for label, run in runs:
        if run.returncode != 0:
            gaps.append(_run_summary(label, run))
        if not _has_gui_pty_install(run.calls):
            gaps.append(f"{label}: gui-pty was not installed by the existing venv Python")
        if not _has_shared_pty_probe(run.calls):
            gaps.append(f"{label}: shared is_pty_available() was not executed")

    assert _cmd_propagates_pwsh_exit(setup_cmd)
    assert not _cmd_propagates_pwsh_exit(
        "REM pwsh -File setup.ps1\nREM set RC=%ERRORLEVEL%\nREM exit /b %RC%\n"
    )
    assert _cmd_propagates_pwsh_exit(
        "@pwsh -NoProfile -File setup.ps1\nset RESULT=%ERRORLEVEL%\n"
        "endlocal&exit /b %RESULT%\n"
    )
    cmd_exit = _run_cmd_exit_probe(tmp_path / "cmd-exit", expected_exit=37)
    if cmd_exit is not None and cmd_exit != 37:
        gaps.append(f"setup-hve.cmd returned {cmd_exit}, expected delegated pwsh exit 37")

    assert not gaps, "FR-GUI-09 normal setup gaps:\n- " + "\n- ".join(gaps)


def test_normal_gui_setup_fails_closed_when_gh_or_pty_is_missing(
    tmp_path: Path,
) -> None:
    """FR-GUI-09: missing normal-GUI prerequisites must terminate non-zero."""
    runs: list[tuple[str, _SetupRun]] = [
        (
            "setup-hve.sh missing gh",
            _run_shell_setup(
                tmp_path / "shell-gh-missing",
                gh_available=False,
                pty_available=True,
            ),
        ),
        (
            "setup-hve.sh unavailable PTY",
            _run_shell_setup(
                tmp_path / "shell-pty-missing",
                gh_available=True,
                pty_available=False,
            ),
        ),
    ]
    for label, root, gh_available, pty_available in (
        ("setup-hve.ps1 missing gh", "powershell-gh-missing", False, True),
        ("setup-hve.ps1 unavailable PTY", "powershell-pty-missing", True, False),
    ):
        run = _run_powershell_setup(
            tmp_path / root,
            gh_available=gh_available,
            pty_available=pty_available,
        )
        if run is not None:
            runs.append((label, run))

    failures = [_run_summary(label, run) for label, run in runs if run.returncode == 0]
    assert not failures, (
        "normal GUI setup accepted a missing prerequisite:\n- " + "\n- ".join(failures)
    )


def test_normal_gui_setup_repairs_existing_venv_without_force(tmp_path: Path) -> None:
    """FR-GUI-09: editable GUI extras install runs after reuse without Force."""
    runs: list[tuple[str, _SetupRun]] = [
        (
            "setup-hve.sh existing venv",
            _run_shell_setup(
                tmp_path / "shell-existing", gh_available=True, pty_available=True
            ),
        )
    ]
    powershell_run = _run_powershell_setup(
        tmp_path / "powershell-existing", gh_available=True, pty_available=True
    )
    if powershell_run is not None:
        runs.append(("setup-hve.ps1 existing venv", powershell_run))

    gaps: list[str] = []
    for label, run in runs:
        if run.returncode != 0:
            gaps.append(_run_summary(label, run))
        # Git for Windows の Bash は、NTFS 上に Python で作成したテスト用
        # shebang script を ``[[ -x ]]`` と認識しない。この場合だけ fake venv を
        # 新規作成したように見える。実際の POSIX 実行ビット契約は Linux CI の同一
        # harness で検証するため、Windows ではこの host 固有の誤検知を除外する。
        if os.name != "nt" and _created_venv(run.calls):
            gaps.append(f"{label}: recreated an already valid venv without Force")
        if not _has_gui_pty_install(run.calls):
            gaps.append(f"{label}: existing venv skipped the gui-pty install/repair")
        if not _has_shared_pty_probe(run.calls):
            gaps.append(f"{label}: existing venv skipped shared PTY verification")
    assert not gaps, "FR-GUI-09 existing venv gaps:\n- " + "\n- ".join(gaps)


def test_no_gui_and_minimal_remain_explicit_opt_outs(tmp_path: Path) -> None:
    """FR-GUI-09: NoGui/Minimal disable normal-GUI prerequisite enforcement."""
    runs: list[tuple[str, _SetupRun]] = []
    for label, shell_arg, powershell_arg in (
        ("NoGui", "--no-gui", "-NoGui"),
        ("Minimal", "--minimal", "-Minimal"),
    ):
        runs.append(
            (
                f"setup-hve.sh {label}",
                _run_shell_setup(
                    tmp_path / f"shell-{label.casefold()}",
                    args=(shell_arg,),
                    gh_available=False,
                    pty_available=False,
                ),
            )
        )
        powershell_run = _run_powershell_setup(
            tmp_path / f"powershell-{label.casefold()}",
            args=(powershell_arg,),
            gh_available=False,
            pty_available=False,
        )
        if powershell_run is not None:
            runs.append((f"setup-hve.ps1 {label}", powershell_run))

    gaps: list[str] = []
    for label, run in runs:
        if run.returncode != 0:
            gaps.append(_run_summary(label, run))
        if _has_gui_pty_install(run.calls):
            gaps.append(f"{label}: installed gui-pty despite explicit opt-out")
        if _has_shared_pty_probe(run.calls):
            gaps.append(f"{label}: ran shared PTY verification despite explicit opt-out")
    assert not gaps, "FR-GUI-09 opt-out gaps:\n- " + "\n- ".join(gaps)


def test_default_setup_upgrades_the_copilot_sdk_and_pin_sdk_uses_the_lock(
    tmp_path: Path,
) -> None:
    """FR-MODEL-07: 既定実行は最新版へ更新し、明示 pin のときだけ lock 版を導入する。"""
    gaps: list[str] = []

    default_runs: list[tuple[str, _SetupRun]] = [
        (
            "setup-hve.sh default",
            _run_shell_setup(
                tmp_path / "shell-sdk-default", gh_available=True, pty_available=True
            ),
        )
    ]
    powershell_default = _run_powershell_setup(
        tmp_path / "powershell-sdk-default", gh_available=True, pty_available=True
    )
    if powershell_default is not None:
        default_runs.append(("setup-hve.ps1 default", powershell_default))

    for label, run in default_runs:
        if run.returncode != 0:
            gaps.append(_run_summary(label, run))
        if not _has_latest_sdk_upgrade(run.calls):
            gaps.append(f"{label}: skipped the github-copilot-sdk upgrade to the latest release")
        if _touched_sdk_lock(run.calls):
            gaps.append(f"{label}: touched hve/copilot-sdk.lock on the default path")

    pinned_runs: list[tuple[str, _SetupRun]] = [
        (
            "setup-hve.sh --pin-sdk",
            _run_shell_setup(
                tmp_path / "shell-sdk-pinned",
                args=("--pin-sdk",),
                gh_available=True,
                pty_available=True,
            ),
        )
    ]
    powershell_pinned = _run_powershell_setup(
        tmp_path / "powershell-sdk-pinned",
        args=("-PinSdk",),
        gh_available=True,
        pty_available=True,
    )
    if powershell_pinned is not None:
        pinned_runs.append(("setup-hve.ps1 -PinSdk", powershell_pinned))

    for label, run in pinned_runs:
        if run.returncode != 0:
            gaps.append(_run_summary(label, run))
        if not _has_locked_sdk_install(run.calls):
            gaps.append(f"{label}: did not install github-copilot-sdk from the lock")
        if _has_latest_sdk_upgrade(run.calls):
            gaps.append(f"{label}: upgraded github-copilot-sdk despite the explicit pin")

    assert not gaps, "FR-MODEL-07 SDK install gaps:\n- " + "\n- ".join(gaps)


def test_check_only_audits_gui_prerequisites_without_changing_anything(
    tmp_path: Path,
) -> None:
    """FR-GUI-09: check-only stays diagnostic and warns instead of failing closed."""
    # (label, run, audits_pty)
    # Git for Windows の Bash は NTFS 上の fake venv python を ``[[ -x ]]`` と
    # 認識しないため、Windows ホストでは shell harness の PTY 監査は到達しない。
    runs: list[tuple[str, _SetupRun, bool]] = [
        (
            "setup-hve.sh check-only missing prerequisites",
            _run_shell_setup(
                tmp_path / "shell-check-missing",
                args=("--check-only",),
                gh_available=False,
                pty_available=False,
            ),
            os.name != "nt",
        )
    ]
    powershell_run = _run_powershell_setup(
        tmp_path / "powershell-check-missing",
        args=("-CheckOnly",),
        gh_available=False,
        pty_available=False,
    )
    if powershell_run is not None:
        runs.append(
            ("setup-hve.ps1 check-only missing prerequisites", powershell_run, True)
        )

    gaps: list[str] = []
    for label, run, audits_pty in runs:
        if run.returncode != 0:
            gaps.append(_run_summary(label, run))
        output = f"{run.stdout}\n{run.stderr}"
        if "GitHub CLI (gh) is unavailable" not in output:
            gaps.append(f"{label}: missing gh was not reported as a warning")
        if _has_pip_install(run.calls) or _created_venv(run.calls):
            gaps.append(f"{label}: check-only modified the environment")
        if not audits_pty:
            continue
        if not _has_shared_pty_probe(run.calls):
            gaps.append(f"{label}: shared is_pty_available() was not audited")
        if "PTY backend required by the GUI" not in output:
            gaps.append(f"{label}: unavailable PTY backend was not reported as a warning")

    satisfied = _run_powershell_setup(
        tmp_path / "powershell-check-satisfied",
        args=("-CheckOnly",),
        gh_available=True,
        pty_available=True,
    )
    if satisfied is not None:
        if satisfied.returncode != 0:
            gaps.append(_run_summary("setup-hve.ps1 check-only satisfied", satisfied))
        if "is unavailable" in f"{satisfied.stdout}\n{satisfied.stderr}":
            gaps.append(
                "setup-hve.ps1 check-only satisfied: warned despite available prerequisites"
            )

    assert not gaps, "FR-GUI-09 check-only audit gaps:\n- " + "\n- ".join(gaps)


def test_setup_does_not_run_gh_auth_login_or_reject_unauthenticated_status(
    tmp_path: Path,
) -> None:
    """FR-GUI-09: authentication remains an interactive GUI responsibility."""
    runs: list[tuple[str, _SetupRun]] = [
        (
            "setup-hve.sh unauthenticated gh",
            _run_shell_setup(
                tmp_path / "shell-auth",
                gh_available=True,
                pty_available=True,
                gh_status_exit=1,
            ),
        )
    ]
    powershell_run = _run_powershell_setup(
        tmp_path / "powershell-auth",
        gh_available=True,
        pty_available=True,
        gh_status_exit=1,
    )
    if powershell_run is not None:
        runs.append(("setup-hve.ps1 unauthenticated gh", powershell_run))

    gaps: list[str] = []
    for label, run in runs:
        if run.returncode != 0:
            gaps.append(_run_summary(label, run))
        normalized = [re.sub(r"\s+", " ", call.strip()).casefold() for call in run.gh_calls]
        if not any(call.startswith("auth status") for call in normalized):
            gaps.append(f"{label}: gh auth status was not observed through the fake gh")
        if any(re.search(r"(?:^|\s)auth\s+login(?:\s|$)", call) for call in normalized):
            gaps.append(f"{label}: setup invoked forbidden gh auth login: {run.gh_calls}")
    assert not gaps, "FR-GUI-09 gh auth responsibility gaps:\n- " + "\n- ".join(gaps)


def test_posix_setup_script_is_executable() -> None:
    """FR-GUI-09: the documented ``./hve/setup-hve.sh`` entry point is runnable."""
    result = subprocess.run(
        ["git", "ls-files", "--stage", "--", "hve/setup-hve.sh"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    entries = [line for line in result.stdout.splitlines() if line.strip()]

    assert len(entries) == 1
    assert entries[0].split(maxsplit=1)[0] == "100755"


def test_ci_verifies_the_pty_backend_on_every_supported_os() -> None:
    """FR-GUI-09: each OS installs gui-pty and runs the PTY suite without skips."""
    import yaml

    workflow = yaml.safe_load(_PYTHON_TEST_WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["gui-pty-tests"]
    steps = "\n".join(str(step.get("run", "")) for step in job["steps"])

    assert set(job["strategy"]["matrix"]["os"]) == {
        "windows-latest",
        "macos-latest",
        "ubuntu-latest",
    }
    assert job["strategy"]["fail-fast"] is False
    assert "gui-pty" in steps
    assert "is_pty_available" in steps
    assert "hve/tests/test_pty_backend.py" in steps
    assert "skipped == 0" in steps


def test_ci_smoke_tests_the_interactive_copilot_cli_on_every_supported_os() -> None:
    """FR-GUI-10: 3 OS で解決済み Copilot CLI の実 PTY smoke を skip 無しで実行する。"""
    import yaml

    workflow = yaml.safe_load(_PYTHON_TEST_WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["gui-pty-tests"]
    steps = "\n".join(str(step.get("run", "")) for step in job["steps"])

    # CLI が解決できないまま skip されると smoke が無言で消えるため fail-closed にする。
    assert "download-runtime" in steps
    assert "CopilotCliBridge.find_binary()" in steps
    assert "hve/tests/test_copilot_cli_pty_smoke.py" in steps
    assert "skipped == 0" in steps


def test_ci_checks_the_sdk_lock_contract_on_every_supported_os() -> None:
    """FR-MODEL-07: lock の UTF-8/LF/BOM 契約を Windows/macOS/Linux の全 OS で検証する。"""
    import yaml

    workflow = yaml.safe_load(_PYTHON_TEST_WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["gui-pty-tests"]
    steps = "\n".join(str(step.get("run", "")) for step in job["steps"])

    assert (
        "hve/tests/test_dev_task_environment_contract.py::"
        "test_copilot_sdk_lock_pins_an_exact_version" in steps
    )
