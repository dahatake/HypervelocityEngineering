"""ローカル最上位起動時の HVE バージョン整合性チェック。

FR-LOCAL-SURFACE-03 に従い、現在 checkout 済みの ``pyproject.toml`` と
editable-install の distribution metadata を比較する。リモートへの問い合わせは
行わず、更新には既存の OS 別 setup スクリプトだけを使用する。
"""
from __future__ import annotations

import importlib.metadata as metadata
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Sequence

_PACKAGE_NAME = "hve"
_CHECKED_ENV = "HVE_STARTUP_VERSION_CHECKED"
_NO_VENV_REEXEC_ENV = "HVE_NO_VENV_REEXEC"
_VERSION_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
)


def _configure_stdio_encoding() -> None:
    """stdout/stderr を UTF-8 に再設定する（Windows cp932 対策）。"""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # pragma: no cover - top-level guard
            pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _venv_python(repo_root: Path) -> Path:
    if sys.platform.startswith("win"):
        return repo_root / ".venv" / "Scripts" / "python.exe"
    return repo_root / ".venv" / "bin" / "python"


def _reexec_in_venv_if_needed() -> None:
    """リポジトリ同梱 ``.venv`` の Python へ最上位起動を正規化する。"""
    if os.environ.get(_NO_VENV_REEXEC_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return

    try:
        repo_root = _repo_root()
        venv_py = _venv_python(repo_root)
        if not venv_py.exists():
            return
        try:
            already_in_venv = os.path.samefile(sys.executable, str(venv_py))
        except OSError:
            already_in_venv = Path(sys.executable).resolve() == venv_py.resolve()
        if already_in_venv:
            return
        new_argv = [str(venv_py), "-m", "hve", *sys.argv[1:]]
        new_env = dict(os.environ)
        new_env[_NO_VENV_REEXEC_ENV] = "1"
    except Exception:  # pragma: no cover - 検出失敗時は従来挙動へフォールバック
        return

    print(
        f"[hve] Detected non-.venv Python; re-executing with .venv: {venv_py}",
        file=sys.stderr,
    )
    if os.name == "nt":
        try:
            completed = subprocess.run(new_argv, env=new_env)
        except Exception:  # pragma: no cover - 起動失敗時は現在の Python で続行
            return
        raise SystemExit(completed.returncode)

    try:
        os.execve(str(venv_py), new_argv, new_env)
    except Exception:  # pragma: no cover - exec 失敗時は現在の Python で続行
        return


def _parse_version(value: str | None) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = _VERSION_RE.fullmatch(value.strip())
    if match is None:
        return None
    try:
        return tuple(int(part) for part in match.groups())  # type: ignore[return-value]
    except ValueError:
        return None


def _read_source_version(repo_root: Path) -> str | None:
    try:
        data = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return None
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    value = project.get("version")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _read_installed_version() -> str | None:
    """stale な placeholder 0.0.0 を無視し、現在有効な dist-info の version を優先する。

    実際の editable install や既存の package metadata で `0.0.0` を返すレガシー
    dist-info が残っていても、これは「インストール済み version」として扱わない。
    代わりに、元の `metadata.version()` が正常な version を返した場合はそれを使い、
    その値が 0.0.0 のときだけ stale dist-info を走査して置き換えを試みる。
    """
    try:
        value = metadata.version(_PACKAGE_NAME)
    except (metadata.PackageNotFoundError, OSError, UnicodeError):
        return None

    if isinstance(value, str):
        normalized = value.strip()
        if normalized and normalized != "0.0.0":
            return normalized
        if not normalized:
            return None
    else:
        return None

    candidates: list[str] = []
    try:
        for dist in metadata.distributions():
            try:
                name = dist.metadata.get("Name")
            except Exception:
                name = None
            if not isinstance(name, str) or name.strip().lower() != _PACKAGE_NAME:
                continue
            try:
                version = dist.version
            except Exception:
                version = None
            if isinstance(version, str):
                candidate = version.strip()
                if candidate and candidate != "0.0.0":
                    candidates.append(candidate)
    except (AttributeError, OSError, UnicodeError):
        pass

    valid_candidates: list[tuple[str, tuple[int, int, int]]] = []
    for candidate in dict.fromkeys(candidates):
        parsed = _parse_version(candidate)
        if parsed is not None:
            valid_candidates.append((candidate, parsed))
    if not valid_candidates:
        return None
    return max(valid_candidates, key=lambda item: item[1])[0]


def _windows_stdin_is_console() -> bool:
    try:
        import ctypes
        import msvcrt

        handle = msvcrt.get_osfhandle(sys.stdin.fileno())
        mode = ctypes.c_ulong(0)
        return bool(
            ctypes.windll.kernel32.GetConsoleMode(  # type: ignore[attr-defined]
                ctypes.c_void_p(handle), ctypes.byref(mode)
            )
        )
    except (AttributeError, OSError, ValueError):
        return False


def _is_interactive() -> bool:
    try:
        if not bool(getattr(sys.stdin, "isatty", lambda: False)()):
            return False
        return not sys.platform.startswith("win") or _windows_stdin_is_console()
    except (OSError, ValueError):
        return False


def _ask_yes_no(prompt: str) -> bool:
    while True:
        print(prompt, end="", file=sys.stderr, flush=True)
        try:
            answer = sys.stdin.readline()
        except (OSError, ValueError):
            return False
        if answer == "":
            return False
        normalized = answer.strip().lower()
        if normalized in {"y", "yes"}:
            return True
        if normalized in {"", "n", "no"}:
            return False
        print("y または n で回答してください。", file=sys.stderr)


def _build_setup_argv(repo_root: Path) -> list[str] | None:
    if sys.platform.startswith("win"):
        setup = repo_root / "hve" / "setup-hve.ps1"
        pwsh = shutil.which("pwsh.exe")
        if not setup.is_file() or not pwsh:
            return None
        return [
            pwsh,
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(setup),
        ]

    setup = repo_root / "hve" / "setup-hve.sh"
    if not setup.is_file():
        return None
    return [str(setup)]


def _setup_resolution_error(repo_root: Path) -> str:
    script = "setup-hve.ps1" if sys.platform.startswith("win") else "setup-hve.sh"
    setup = repo_root / "hve" / script
    if not setup.is_file():
        return f"[hve] ERROR: setup スクリプトが見つかりません: {setup}"
    if sys.platform.startswith("win") and not shutil.which("pwsh.exe"):
        return (
            "[hve] ERROR: PowerShell 7+ (pwsh.exe) が見つかりません。"
            f"{repo_root / 'hve' / 'setup-hve.cmd'} を手動で実行してください。"
        )
    return f"[hve] ERROR: setup を解決できません: {setup}"


def _run_setup_and_restart(
    repo_root: Path,
    source_version: str,
    launch_argv: Sequence[str],
) -> int:
    setup_argv = _build_setup_argv(repo_root)
    if setup_argv is None:
        print(_setup_resolution_error(repo_root), file=sys.stderr)
        return 1

    try:
        completed = subprocess.run(
            setup_argv,
            cwd=str(repo_root),
            check=False,
            shell=False,
        )
    except OSError as exc:
        print(
            f"[hve] ERROR: setup を起動できません ({type(exc).__name__})。",
            file=sys.stderr,
        )
        return 1
    if completed.returncode != 0:
        print(
            f"[hve] ERROR: setup が失敗しました (exit={completed.returncode})。",
            file=sys.stderr,
        )
        return completed.returncode

    installed_after = _read_installed_version()
    if installed_after != source_version:
        actual = installed_after if _parse_version(installed_after) is not None else "確認不能"
        print(
            "[hve] ERROR: setup 後の HVE バージョンが checkout 版と一致しません "
            f"(installed={actual}, latest={source_version})。",
            file=sys.stderr,
        )
        return 1

    restart_argv = [
        str(_venv_python(repo_root)),
        "-m",
        "hve",
        *launch_argv,
    ]
    restart_env = dict(os.environ)
    restart_env[_CHECKED_ENV] = "1"
    try:
        restarted = subprocess.run(
            restart_argv,
            env=restart_env,
            check=False,
            shell=False,
        )
    except OSError as exc:
        print(
            f"[hve] ERROR: 更新後の HVE を起動できません ({type(exc).__name__})。",
            file=sys.stderr,
        )
        return 1
    return restarted.returncode


def check_startup_version(launch_argv: Sequence[str] | None = None) -> int | None:
    """FR-LOCAL-SURFACE-03: ローカル最上位起動時の HVE 版を確認する。

    ``None`` は現在のプロセスで通常 dispatch を続行することを表す。整数は setup
    または更新後に再起動した HVE の終了コードであり、呼び出し元がその値で終了する。
    """
    if os.environ.get(_CHECKED_ENV) == "1":
        return None
    os.environ[_CHECKED_ENV] = "1"

    repo_root = _repo_root()
    source_version = _read_source_version(repo_root)
    source_parsed = _parse_version(source_version)
    if source_version is None or source_parsed is None:
        print(
            "[hve] WARNING: checkout の HVE source version を確認できないため、"
            "起動時のバージョンチェックをスキップします。",
            file=sys.stderr,
        )
        return None

    installed_version = _read_installed_version()
    installed_parsed = _parse_version(installed_version)
    if installed_version is not None and installed_parsed == source_parsed:
        return None

    if installed_parsed is not None and installed_parsed > source_parsed:
        print(
            "[hve] WARNING: インストール済み HVE の方が checkout 版より新しいため "
            f"downgrade しません (installed={installed_version}, latest={source_version})。",
            file=sys.stderr,
        )
        return None

    if installed_parsed is None:
        if not _is_interactive():
            print(
                "[hve] WARNING: HVE のインストール済みバージョンを確認できません。"
                f"checkout の最新バージョンは {source_version} です。"
                "標準入力が TTY ではないため自動セットアップせず続行します。",
                file=sys.stderr,
            )
            return None
        should_update = _ask_yes_no(
            "HVE のインストール済みバージョンを確認できません。"
            f"最新の`{source_version}`のバージョンをセットアップしますか? [y/N]: "
        )
    else:
        if not _is_interactive():
            print(
                "[hve] WARNING: "
                f"現在インストールされているバージョンは{installed_version}です。"
                f"最新のバージョンは{source_version}です。"
                "標準入力が TTY ではないため自動アップグレードせず続行します。",
                file=sys.stderr,
            )
            return None
        should_update = _ask_yes_no(
            f"現在インストールされているバージョンは`{installed_version}`です。"
            f"最新の`{source_version}`のバージョンにアップグレードしますか? [y/N]: "
        )

    if not should_update:
        return None
    return _run_setup_and_restart(
        repo_root,
        source_version,
        tuple(sys.argv[1:] if launch_argv is None else launch_argv),
    )


def console_main() -> int:
    """軽量な ``hve`` console script bootstrap。"""
    _configure_stdio_encoding()
    _reexec_in_venv_if_needed()
    result = check_startup_version(tuple(sys.argv[1:]))
    if result is not None:
        return result

    from .__main__ import main

    return main()
