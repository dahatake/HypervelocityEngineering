"""FR-LOCAL-SURFACE-03: ローカル起動時の HVE バージョン整合性。"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import hve.startup_version as sv  # pyright: ignore[reportMissingTypeStubs]


class _Stdin(io.StringIO):
    def __init__(self, answers: list[str], *, tty: bool = True) -> None:
        super().__init__("".join(f"{answer}\n" for answer in answers))
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


@pytest.fixture(autouse=True)
def _clean_startup_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(sv._CHECKED_ENV, raising=False)
    monkeypatch.delenv("HVE_NO_VENV_REEXEC", raising=False)


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    source: str | None = "1.2.0",
    installed: str | None = "1.1.0",
    answers: list[str] | None = None,
    tty: bool = True,
) -> io.StringIO:
    stderr = io.StringIO()
    monkeypatch.setattr(sv, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        sv,
        "_venv_python",
        lambda _root: tmp_path / ".venv" / "expected-python",
    )
    monkeypatch.setattr(sv, "_read_source_version", lambda _root: source)
    monkeypatch.setattr(sv, "_read_installed_version", lambda: installed)
    monkeypatch.setattr(sv.sys, "stdin", _Stdin(answers or [], tty=tty))
    if sys.platform.startswith("win"):
        monkeypatch.setattr(sv, "_windows_stdin_is_console", lambda: True)
    monkeypatch.setattr(sv.sys, "stderr", stderr)
    return stderr


def _forbid_process(*_args, **_kwargs):
    raise AssertionError("subprocess.run must not be called")


def test_parse_version_uses_numeric_semver_order() -> None:
    newer = sv._parse_version("1.10.0")
    older = sv._parse_version("1.9.9")

    assert newer == (1, 10, 0)
    assert older == (1, 9, 9)
    assert sv._parse_version("1.2") is None
    assert sv._parse_version("v1.2.3") is None


def test_parse_version_rejects_component_beyond_runtime_integer_limit() -> None:
    limit = sys.get_int_max_str_digits()
    if limit == 0:
        pytest.skip("runtime integer-string conversion limit is disabled")

    assert sv._parse_version(f"{'9' * (limit + 1)}.0.0") is None


@pytest.mark.parametrize("value", ["01.2.3", "1.02.3", "1.2.03"])
def test_parse_version_rejects_leading_zero_components(value: str) -> None:
    assert sv._parse_version(value) is None


def test_parse_version_rejects_non_ascii_digits() -> None:
    assert sv._parse_version("١.٢.٣") is None


def test_read_source_version_uses_pyproject_project_version(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "hve"\nversion = "2.3.4"\n',
        encoding="utf-8",
    )

    assert sv._read_source_version(tmp_path) == "2.3.4"


def test_read_source_version_returns_none_when_pyproject_is_missing(
    tmp_path: Path,
) -> None:
    assert sv._read_source_version(tmp_path) is None


def test_read_source_version_returns_none_for_invalid_utf8(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_bytes(
        b'[project]\nname = "hve"\nversion = "2.3.4\xff"\n'
    )

    assert sv._read_source_version(tmp_path) is None


def test_read_source_version_returns_none_for_invalid_toml(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project\nversion = "2.3.4"\n',
        encoding="utf-8",
    )

    assert sv._read_source_version(tmp_path) is None


@pytest.mark.parametrize(
    "body",
    [
        'name = "hve"\n',
        '[project]\nname = "hve"\n',
        '[project]\nversion = 123\n',
        '[project]\nversion = "   "\n',
    ],
)
def test_read_source_version_returns_none_without_string_project_version(
    tmp_path: Path,
    body: str,
) -> None:
    (tmp_path / "pyproject.toml").write_text(body, encoding="utf-8")

    assert sv._read_source_version(tmp_path) is None


def test_read_installed_version_returns_none_when_distribution_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(_name: str) -> str:
        raise sv.metadata.PackageNotFoundError("hve")

    monkeypatch.setattr(sv.metadata, "version", missing)

    assert sv._read_installed_version() is None


@pytest.mark.parametrize("value", [None, b"1.2.3", "   "])
def test_read_installed_version_returns_none_for_unusable_version_value(
    monkeypatch: pytest.MonkeyPatch,
    value: object,
) -> None:
    monkeypatch.setattr(sv.metadata, "version", lambda _name: value)

    assert sv._read_installed_version() is None


@pytest.mark.parametrize(
    "error",
    [
        OSError("metadata unavailable"),
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid metadata"),
    ],
)
def test_read_installed_version_returns_none_for_metadata_read_failure(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    def fail(_name: str) -> str:
        raise error

    monkeypatch.setattr(sv.metadata, "version", fail)

    assert sv._read_installed_version() is None


def test_read_installed_version_prefers_non_placeholder_distribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_version(_name: str) -> str:
        return "0.0.0"

    def fake_distributions():
        return [
            type("_Dist", (), {"metadata": {"Name": "hve"}, "version": "0.0.0"})(),
            type("_Dist", (), {"metadata": {"Name": "hve"}, "version": "0.8.121"})(),
        ]

    monkeypatch.setattr(sv.metadata, "version", fake_version)
    monkeypatch.setattr(sv.metadata, "distributions", fake_distributions)

    assert sv._read_installed_version() == "0.8.121"


def test_same_version_is_silent_noop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stderr = _configure(monkeypatch, tmp_path, source="1.2.0", installed="1.2.0")
    monkeypatch.setattr(sv.subprocess, "run", _forbid_process)

    assert sv.check_startup_version(["gui"]) is None
    assert stderr.getvalue() == ""


@pytest.mark.parametrize("answer", ["n", "no", ""])
def test_declining_old_version_continues_without_setup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, answer: str
) -> None:
    stderr = _configure(monkeypatch, tmp_path, answers=[answer])
    monkeypatch.setattr(sv.subprocess, "run", _forbid_process)

    assert sv.check_startup_version(["gui"]) is None
    output = stderr.getvalue()
    assert "現在インストールされているバージョンは`1.1.0`です" in output
    assert "最新の`1.2.0`のバージョンにアップグレードしますか? [y/N]:" in output


def test_invalid_answer_reprompts_then_yes_runs_setup_and_original_argv_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stderr = _configure(monkeypatch, tmp_path, answers=["later", "YES"])
    versions = iter(["1.1.0", "1.2.0"])
    monkeypatch.setattr(sv, "_read_installed_version", lambda: next(versions))
    monkeypatch.setattr(sv, "_build_setup_argv", lambda _root: ["setup-command"])
    calls: list[tuple[list[str], dict]] = []

    def run(argv, **kwargs):
        calls.append((list(argv), dict(kwargs)))
        return SimpleNamespace(returncode=0 if len(calls) == 1 else 7)

    monkeypatch.setattr(sv.subprocess, "run", run)

    assert sv.check_startup_version(["orchestrate", "--workflow", "ard"]) == 7
    assert stderr.getvalue().count("アップグレードしますか? [y/N]:") == 2
    assert calls[0] == (
        ["setup-command"],
        {"cwd": str(tmp_path), "check": False, "shell": False},
    )
    restart_argv, restart_kwargs = calls[1]
    assert restart_argv == [
        str(tmp_path / ".venv" / "expected-python"),
        "-m",
        "hve",
        "orchestrate",
        "--workflow",
        "ard",
    ]
    assert restart_kwargs["check"] is False
    assert restart_kwargs["shell"] is False
    assert "cwd" not in restart_kwargs
    assert restart_kwargs["env"][sv._CHECKED_ENV] == "1"


def test_old_version_non_tty_warns_with_both_versions_and_continues(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stderr = _configure(monkeypatch, tmp_path, tty=False)
    monkeypatch.setattr(sv.subprocess, "run", _forbid_process)

    assert sv.check_startup_version(["gui"]) is None
    output = stderr.getvalue()
    assert "1.1.0" in output
    assert "1.2.0" in output
    assert "TTY" in output


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows NUL contract")
def test_windows_nul_is_treated_as_non_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    with open(os.devnull, encoding="utf-8") as null_input:
        assert null_input.isatty() is True
        monkeypatch.setattr(sv.sys, "stdin", null_input)

        assert sv._is_interactive() is False


@pytest.mark.parametrize("is_console", [False, True])
def test_windows_interactivity_requires_a_real_console_handle(
    monkeypatch: pytest.MonkeyPatch, is_console: bool
) -> None:
    monkeypatch.setattr(sv.sys, "platform", "win32")
    monkeypatch.setattr(sv.sys, "stdin", _Stdin([], tty=True))
    monkeypatch.setattr(sv, "_windows_stdin_is_console", lambda: is_console)

    assert sv._is_interactive() is is_console


def test_posix_interactivity_does_not_consult_the_windows_console_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden() -> bool:
        raise AssertionError("POSIX must not consult the Windows console check")

    monkeypatch.setattr(sv.sys, "platform", "linux")
    monkeypatch.setattr(sv.sys, "stdin", _Stdin([], tty=True))
    monkeypatch.setattr(sv, "_windows_stdin_is_console", forbidden)

    assert sv._is_interactive() is True


def test_closed_stdin_is_treated_as_non_tty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stderr = _configure(monkeypatch, tmp_path)
    closed_stdin = io.StringIO()
    closed_stdin.close()
    monkeypatch.setattr(sv.sys, "stdin", closed_stdin)
    monkeypatch.setattr(sv.subprocess, "run", _forbid_process)

    assert sv.check_startup_version(["gui"]) is None
    assert "TTY" in stderr.getvalue()


def test_tty_read_failure_declines_update_without_crashing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FailingReadStdin:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            raise OSError("stdin unavailable")

    stderr = _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(sv.sys, "stdin", FailingReadStdin())
    monkeypatch.setattr(sv.subprocess, "run", _forbid_process)

    assert sv.check_startup_version(["gui"]) is None
    assert "アップグレードしますか? [y/N]:" in stderr.getvalue()


def test_newer_installed_version_is_not_downgraded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stderr = _configure(monkeypatch, tmp_path, installed="1.3.0", answers=["yes"])
    monkeypatch.setattr(sv.subprocess, "run", _forbid_process)

    assert sv.check_startup_version(["gui"]) is None
    output = stderr.getvalue()
    assert "1.3.0" in output
    assert "1.2.0" in output
    assert "downgrade" in output.lower()


def test_invalid_source_version_warns_without_inventing_a_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stderr = _configure(monkeypatch, tmp_path, source="development", answers=["yes"])
    monkeypatch.setattr(sv.subprocess, "run", _forbid_process)

    assert sv.check_startup_version(["gui"]) is None
    output = stderr.getvalue()
    assert "source" in output.lower()
    assert "development" not in output


@pytest.mark.parametrize("answer", ["n", "no", ""])
def test_missing_metadata_decline_continues_without_setup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, answer: str
) -> None:
    stderr = _configure(monkeypatch, tmp_path, installed=None, answers=[answer])
    monkeypatch.setattr(sv.subprocess, "run", _forbid_process)

    assert sv.check_startup_version(["gui"]) is None
    output = stderr.getvalue()
    assert "インストール済みバージョンを確認できません" in output
    assert "最新の`1.2.0`のバージョンをセットアップしますか? [y/N]:" in output


def test_missing_metadata_invalid_answer_reprompts_then_updates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stderr = _configure(monkeypatch, tmp_path, installed=None, answers=["later", "y"])
    versions = iter([None, "1.2.0"])
    monkeypatch.setattr(sv, "_read_installed_version", lambda: next(versions))
    monkeypatch.setattr(sv, "_build_setup_argv", lambda _root: ["setup-command"])
    calls: list[tuple[list[str], dict]] = []

    def run(argv, **kwargs):
        calls.append((list(argv), dict(kwargs)))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(sv.subprocess, "run", run)

    assert sv.check_startup_version(["--help"]) == 0
    assert stderr.getvalue().count("セットアップしますか? [y/N]:") == 2
    assert calls[0] == (
        ["setup-command"],
        {"cwd": str(tmp_path), "check": False, "shell": False},
    )
    restart_argv, restart_kwargs = calls[1]
    assert restart_argv == [
        str(tmp_path / ".venv" / "expected-python"),
        "-m",
        "hve",
        "--help",
    ]
    assert restart_kwargs["check"] is False
    assert restart_kwargs["shell"] is False
    assert "cwd" not in restart_kwargs
    assert restart_kwargs["env"][sv._CHECKED_ENV] == "1"


def test_missing_metadata_post_setup_read_failure_does_not_restart(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stderr = _configure(monkeypatch, tmp_path, installed=None, answers=["yes"])
    versions = iter([None, None])
    monkeypatch.setattr(sv, "_read_installed_version", lambda: next(versions))
    monkeypatch.setattr(sv, "_build_setup_argv", lambda _root: ["setup-command"])
    calls: list[list[str]] = []

    def run(argv, **_kwargs):
        calls.append(list(argv))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(sv.subprocess, "run", run)

    assert sv.check_startup_version(["gui"]) == 1
    assert calls == [["setup-command"]]
    assert "一致しません" in stderr.getvalue()


def test_missing_metadata_non_tty_warns_and_continues(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stderr = _configure(monkeypatch, tmp_path, installed=None, tty=False)
    monkeypatch.setattr(sv.subprocess, "run", _forbid_process)

    assert sv.check_startup_version(["gui"]) is None
    output = stderr.getvalue()
    assert "インストール済みバージョンを確認できません" in output
    assert "1.2.0" in output


def test_setup_failure_does_not_restart_original_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stderr = _configure(monkeypatch, tmp_path, answers=["yes"])
    monkeypatch.setattr(sv, "_build_setup_argv", lambda _root: ["setup-command"])
    calls: list[list[str]] = []

    def run(argv, **_kwargs):
        calls.append(list(argv))
        return SimpleNamespace(returncode=9)

    monkeypatch.setattr(sv.subprocess, "run", run)

    assert sv.check_startup_version(["gui"]) == 9
    assert calls == [["setup-command"]]
    assert "exit=9" in stderr.getvalue()


@pytest.mark.parametrize("after", [None, "1.1.0", "1.3.0"])
def test_post_setup_version_must_exactly_match_source_before_restart(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, after: str | None
) -> None:
    stderr = _configure(monkeypatch, tmp_path, answers=["yes"])
    versions = iter(["1.1.0", after])
    monkeypatch.setattr(sv, "_read_installed_version", lambda: next(versions))
    monkeypatch.setattr(sv, "_build_setup_argv", lambda _root: ["setup-command"])
    calls: list[list[str]] = []

    def run(argv, **_kwargs):
        calls.append(list(argv))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(sv.subprocess, "run", run)

    assert sv.check_startup_version(["gui"]) == 1
    assert calls == [["setup-command"]]
    assert "一致しません" in stderr.getvalue()


def test_setup_launch_error_is_nonzero_and_does_not_restart(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stderr = _configure(monkeypatch, tmp_path, answers=["yes"])
    monkeypatch.setattr(sv, "_build_setup_argv", lambda _root: ["setup-command"])

    def fail(*_args, **_kwargs):
        raise OSError("cannot launch")

    monkeypatch.setattr(sv.subprocess, "run", fail)

    assert sv.check_startup_version(["gui"]) == 1
    assert "起動できません" in stderr.getvalue()


def test_restart_launch_error_is_nonzero_after_successful_setup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stderr = _configure(monkeypatch, tmp_path, answers=["yes"])
    versions = iter(["1.1.0", "1.2.0"])
    monkeypatch.setattr(sv, "_read_installed_version", lambda: next(versions))
    monkeypatch.setattr(sv, "_build_setup_argv", lambda _root: ["setup-command"])
    calls: list[list[str]] = []

    def run(argv, **_kwargs):
        calls.append(list(argv))
        if len(calls) == 1:
            return SimpleNamespace(returncode=0)
        raise OSError("cannot restart")

    monkeypatch.setattr(sv.subprocess, "run", run)

    assert sv.check_startup_version(["gui"]) == 1
    assert len(calls) == 2
    assert "更新後の HVE を起動できません" in stderr.getvalue()


def test_marker_skips_version_read_prompt_setup_and_restart(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(sv._CHECKED_ENV, "1")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("version check work must be skipped in a child process")

    monkeypatch.setattr(sv, "_repo_root", forbidden)
    monkeypatch.setattr(sv, "_read_source_version", forbidden)
    monkeypatch.setattr(sv, "_read_installed_version", forbidden)
    monkeypatch.setattr(sv.subprocess, "run", forbidden)

    assert sv.check_startup_version(["orchestrate"]) is None


def test_venv_reexec_marker_does_not_suppress_version_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HVE_NO_VENV_REEXEC", "1")
    calls: list[str] = []
    monkeypatch.setattr(sv, "_repo_root", lambda: tmp_path)

    def read_source(_root: Path) -> str:
        calls.append("source")
        return "1.2.0"

    monkeypatch.setattr(sv, "_read_source_version", read_source)
    monkeypatch.setattr(sv, "_read_installed_version", lambda: "1.2.0")
    monkeypatch.setattr(sv.subprocess, "run", _forbid_process)

    assert sv.check_startup_version(["gui"]) is None
    assert calls == ["source"]


def test_windows_setup_argv_uses_pwsh_and_existing_ps1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = tmp_path / "hve" / "setup-hve.ps1"
    script.parent.mkdir()
    script.write_text("# setup\n", encoding="utf-8")
    pwsh = str(tmp_path / "pwsh.exe")
    monkeypatch.setattr(sv.sys, "platform", "win32")
    monkeypatch.setattr(sv.shutil, "which", lambda name: pwsh if name == "pwsh.exe" else None)

    argv = sv._build_setup_argv(tmp_path)

    assert argv == [
        pwsh,
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
    ]
    assert "-Yes" not in argv


def test_windows_setup_argv_fails_closed_without_pwsh(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = tmp_path / "hve" / "setup-hve.ps1"
    script.parent.mkdir()
    script.write_text("# setup\n", encoding="utf-8")
    monkeypatch.setattr(sv.sys, "platform", "win32")
    monkeypatch.setattr(sv.shutil, "which", lambda _name: None)

    assert sv._build_setup_argv(tmp_path) is None


def test_windows_missing_pwsh_stops_before_setup_and_original_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stderr = _configure(monkeypatch, tmp_path, answers=["yes"])
    script = tmp_path / "hve" / "setup-hve.ps1"
    script.parent.mkdir()
    script.write_text("# setup\n", encoding="utf-8")
    monkeypatch.setattr(sv.sys, "platform", "win32")
    monkeypatch.setattr(sv, "_windows_stdin_is_console", lambda: True)
    monkeypatch.setattr(sv.shutil, "which", lambda _name: None)
    monkeypatch.setattr(sv.subprocess, "run", _forbid_process)

    assert sv.check_startup_version(["gui"]) == 1
    output = stderr.getvalue()
    assert "pwsh" in output
    assert "setup-hve.cmd" in output


def test_windows_missing_setup_script_takes_precedence_over_missing_pwsh(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sv.sys, "platform", "win32")
    monkeypatch.setattr(sv.shutil, "which", lambda _name: None)

    output = sv._setup_resolution_error(tmp_path)

    assert "setup-hve.ps1" in output
    assert "setup-hve.cmd" not in output


def test_posix_setup_argv_uses_existing_shell_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = tmp_path / "hve" / "setup-hve.sh"
    script.parent.mkdir()
    script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    monkeypatch.setattr(sv.sys, "platform", "linux")

    argv = sv._build_setup_argv(tmp_path)

    assert argv == [str(script)]
    assert "--yes" not in argv


def test_posix_missing_setup_script_reports_missing_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sv.sys, "platform", "linux")

    assert sv._build_setup_argv(tmp_path) is None
    output = sv._setup_resolution_error(tmp_path)
    assert "setup スクリプトが見つかりません" in output
    assert "setup-hve.sh" in output


@pytest.mark.parametrize(
    ("platform", "relative"),
    [
        ("win32", Path(".venv/Scripts/python.exe")),
        ("linux", Path(".venv/bin/python")),
        ("darwin", Path(".venv/bin/python")),
    ],
)
def test_restart_python_is_resolved_from_repository_venv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    platform: str,
    relative: Path,
) -> None:
    monkeypatch.setattr(sv.sys, "platform", platform)

    assert sv._venv_python(tmp_path) == tmp_path / relative
