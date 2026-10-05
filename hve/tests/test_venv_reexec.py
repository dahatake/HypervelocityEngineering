"""`_reexec_in_venv_if_needed` の単体テスト。

システム Python から ``python -m hve`` が起動された場合に、リポジトリ同梱の
``.venv`` の Python へ自動再 exec する挙動を検証する。
"""
from __future__ import annotations

import os
import subprocess
import sys
import sysconfig
import types
from pathlib import Path

import pytest

import hve.__main__ as m
import hve.startup_version as sv


def _expected_venv_py() -> Path:
    """関数本体と同じロジックで .venv の Python パスを算出する。"""
    repo_root = Path(sv.__file__).resolve().parent.parent
    if os.name == "nt":
        return repo_root / ".venv" / "Scripts" / "python.exe"
    return repo_root / ".venv" / "bin" / "python"


@pytest.fixture(autouse=True)
def _clean_optout_env(monkeypatch):
    monkeypatch.delenv("HVE_NO_VENV_REEXEC", raising=False)
    monkeypatch.delenv("HVE_STARTUP_VERSION_CHECKED", raising=False)
    yield


def test_optout_env_skips_reexec(monkeypatch):
    """HVE_NO_VENV_REEXEC=1 のときは何もしない。"""
    monkeypatch.setenv("HVE_NO_VENV_REEXEC", "1")

    def _boom(*_a, **_k):  # 呼ばれてはならない
        raise AssertionError("subprocess.run must not be called when opted out")

    monkeypatch.setattr(subprocess, "run", _boom)
    # 例外も SystemExit も発生せず、静かに return すること。
    assert sv._reexec_in_venv_if_needed() is None


def test_noop_when_already_in_venv(monkeypatch):
    """既に .venv の Python で動作している場合は再 exec しない。"""
    venv_py = _expected_venv_py()
    if not venv_py.exists():
        pytest.skip(".venv python not present in this environment")

    # samefile が True を返す = 現在の実行 Python が .venv の Python。
    monkeypatch.setattr(os.path, "samefile", lambda _a, _b: True)

    def _boom(*_a, **_k):
        raise AssertionError("subprocess.run must not be called when already in venv")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(os, "execve", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("os.execve must not be called when already in venv")
    ))
    assert sv._reexec_in_venv_if_needed() is None


def test_reexec_spawns_venv_python(monkeypatch):
    """システム Python 起動時は .venv の Python へ argv を引き継いで再 exec する。"""
    venv_py = _expected_venv_py()
    if not venv_py.exists():
        pytest.skip(".venv python not present in this environment")

    # 「.venv 外の Python で起動された」状況を再現。
    monkeypatch.setattr(os.path, "samefile", lambda _a, _b: False)
    monkeypatch.setattr(sys, "argv", ["hve/__main__.py", "gui"])

    captured: dict = {}

    def _fake_run(argv, env=None):
        captured["argv"] = argv
        captured["env"] = env

        class _R:
            returncode = 7

        return _R()

    def _fake_execve(_path, argv, env):
        captured["argv"] = argv
        captured["env"] = env
        # execve は本来戻らないため SystemExit で模倣する。
        raise SystemExit(7)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    monkeypatch.setattr(os, "execve", _fake_execve)

    with pytest.raises(SystemExit) as exc_info:
        sv._reexec_in_venv_if_needed()

    assert exc_info.value.code == 7
    # 再構築されたコマンドが `<venv_py> -m hve gui` であること。
    assert captured["argv"][0] == str(venv_py)
    assert captured["argv"][1:3] == ["-m", "hve"]
    assert captured["argv"][3:] == ["gui"]
    # 再帰防止フラグが注入されていること。
    assert captured["env"]["HVE_NO_VENV_REEXEC"] == "1"


def test_console_bootstrap_invokes_guards_before_main_import(monkeypatch):
    """console script は軽量 bootstrap の guard 後にだけ main を import する。"""
    calls: list[str] = []
    fake_main = types.ModuleType("hve.__main__")
    fake_main.main = lambda: (calls.append("main"), 0)[1]  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hve.__main__", fake_main)
    monkeypatch.setattr(sv, "_configure_stdio_encoding", lambda: calls.append("stdio"))
    monkeypatch.setattr(sv, "_reexec_in_venv_if_needed", lambda: calls.append("guard"))
    monkeypatch.setattr(
        sv,
        "check_startup_version",
        lambda _argv: (calls.append("version"), None)[1],
    )

    assert sv.console_main() == 0
    assert calls == ["stdio", "guard", "version", "main"]


def test_console_bootstrap_stops_before_main_import_when_check_finishes(
    monkeypatch,
) -> None:
    fake_main = types.ModuleType("hve.__main__")
    monkeypatch.setitem(sys.modules, "hve.__main__", fake_main)
    monkeypatch.setattr(sv, "_reexec_in_venv_if_needed", lambda: None)
    monkeypatch.setattr(sv, "check_startup_version", lambda _argv: 9)

    assert sv.console_main() == 9


@pytest.mark.skipif(os.name != "nt", reason="Windows console launcher encoding contract")
def test_console_script_version_warning_is_utf8(tmp_path: Path) -> None:
    """軽量 console shim も pipe へ UTF-8 の警告を出力する。"""
    repo_root = Path(sv.__file__).resolve().parent.parent
    source_version = sv._read_source_version(repo_root)
    assert source_version is not None
    dist_info = tmp_path / "hve-0.0.0.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: hve\nVersion: 0.0.0\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env.pop(sv._CHECKED_ENV, None)
    env.pop("HVE_NO_VENV_REEXEC", None)
    env.pop("PYTHONSTARTUP", None)
    # The installed launcher can belong to a different editable worktree.
    # Keep fake distribution metadata first, but import the source under test.
    env["PYTHONPATH"] = os.pathsep.join((str(tmp_path), str(repo_root)))
    launcher = Path(sysconfig.get_path("scripts")) / "hve.exe"

    completed = subprocess.run(
        [str(launcher), "--help"],
        cwd=tmp_path,
        env=env,
        input=b"",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    stderr = completed.stderr.decode("utf-8")
    assert completed.returncode == 0
    assert "0.0.0" not in stderr
    assert source_version in stderr
    assert "標準入力が TTY ではないため自動アップグレードせず続行します。" in stderr


def test_flat_script_version_check_uses_top_level_fallback(monkeypatch) -> None:
    """``python hve/__main__.py`` は package 文脈なしでも checker を解決する。"""
    calls: list[tuple[str, ...]] = []
    fake = types.ModuleType("startup_version")

    def check_startup_version(argv) -> int:
        calls.append(tuple(argv))
        return 13

    fake.check_startup_version = check_startup_version  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "startup_version", fake)
    monkeypatch.setattr(m, "__package__", "")
    monkeypatch.setattr(m, "__spec__", None)
    monkeypatch.setattr(sys, "argv", ["hve/__main__.py", "gui"])

    with pytest.raises(SystemExit) as exc_info:
        m._run_startup_version_check()

    assert exc_info.value.code == 13
    assert calls == [("gui",)]


def test_console_script_entry_point_targets_lightweight_bootstrap():
    """pyproject の console script が重い `hve.__main__` を import しないこと。

    `hve.__main__` 内の関数を指すと entry point 解決だけで重い依存を先に import する。
    """
    import tomllib

    pyproject = Path(m.__file__).resolve().parent.parent / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    assert data["project"]["scripts"]["hve"] == "hve.startup_version:console_main"


def test_console_script_target_import_does_not_reach_heavy_config() -> None:
    """fresh process で entry point module の import が `hve.config` より先に完了する。"""
    import tomllib

    repo_root = Path(m.__file__).resolve().parent.parent
    data = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    module_name = data["project"]["scripts"]["hve"].split(":", 1)[0]
    code = f'''\
import importlib
import importlib.abc
import sys

class BlockHeavyConfig(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "hve.config":
            raise RuntimeError("entry point imported hve.config before its guard")
        return None

sys.meta_path.insert(0, BlockHeavyConfig())
importlib.import_module({module_name!r})
'''
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_legacy_console_shim_runs_guards_before_heavy_import() -> None:
    """更新前に生成済みの旧 ``hve.__main__:_console_main`` shim も救済する。"""
    repo_root = Path(m.__file__).resolve().parent.parent
    code = '''\
import importlib.abc
import sys
import sysconfig
from pathlib import Path
import hve.startup_version as startup

events = []
startup._reexec_in_venv_if_needed = lambda: events.append("guard")
startup.check_startup_version = lambda _argv: (events.append("version"), None)[1]
sys.argv[0] = str(Path(sysconfig.get_path("scripts")) / "hve.exe")

class BlockHeavyConfig(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "hve.config":
            raise RuntimeError("blocked-heavy-import")
        return None

sys.meta_path.insert(0, BlockHeavyConfig())
try:
    import hve.__main__
except RuntimeError as exc:
    assert str(exc) == "blocked-heavy-import"
else:
    raise AssertionError("hve.config was not blocked")
assert events == ["guard", "version"], events
'''
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_library_import_from_unrelated_hve_named_process_does_not_run_guards(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """同名だけの利用者スクリプトを旧console shimと誤認しない。"""
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "hve.exe")])

    assert m._is_legacy_console_shim_import() is False


def test_entrypoint_guards_precede_heavy_imports():
    """`python -m hve` は venv 正規化、version check の順で重い import 前に呼ぶ。

    module level の `from .config import ...`（-> `cq`）はファイル末尾の
    `if __name__ == "__main__":` ブロックより先に評価される。ガードを末尾に
    しか置かないと、.venv 外の Python 起動時に依存欠落で先に落ちる。
    """
    import ast

    tree = ast.parse(Path(m.__file__).resolve().read_text(encoding="utf-8"))

    def is_main_guard(node: ast.stmt) -> bool:
        if not isinstance(node, ast.If):
            return False
        return any(
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "__name__"
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq)
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == "__main__"
            for test in ast.walk(node.test)
        )

    def runtime_import_lines(statements: list[ast.stmt]) -> list[int]:
        lines: list[int] = []
        for statement in statements:
            if isinstance(statement, ast.ImportFrom):
                if (statement.module or "").split(".", 1)[0] == "config":
                    lines.append(statement.lineno)
                continue
            if isinstance(statement, ast.Import):
                if any(alias.name.split(".", 1)[0] == "config" for alias in statement.names):
                    lines.append(statement.lineno)
                continue
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            child_blocks: list[ast.stmt] = []
            for field in ("body", "orelse", "finalbody"):
                child_blocks.extend(getattr(statement, field, []))
            for handler in getattr(statement, "handlers", []):
                child_blocks.extend(handler.body)
            runtime_lines = runtime_import_lines(child_blocks)
            lines.extend(runtime_lines)
        return lines

    config_import_lines = runtime_import_lines(tree.body)
    config_import_line = min(config_import_lines) if config_import_lines else None
    early_main_guards = [
        node
        for node in tree.body
        if is_main_guard(node)
        and (config_import_line is None or node.lineno < config_import_line)
    ]
    assert len(early_main_guards) == 1
    guard_calls = [
        (getattr(child.value.func, "id", None), child.lineno)
        for child in early_main_guards[0].body
        if isinstance(child, ast.Expr) and isinstance(child.value, ast.Call)
    ]
    assert [name for name, _line in guard_calls] == [
        "_configure_stdio_encoding",
        "_reexec_in_venv_if_needed",
        "_run_startup_version_check",
    ]
    if config_import_line is not None:
        assert guard_calls[-1][1] < config_import_line


def test_main_direct_call_does_not_run_startup_version_check(monkeypatch) -> None:
    """ライブラリ・テストからの ``main(argv)`` は暗黙 setup を起動しない。"""
    def forbidden() -> None:
        raise AssertionError("main(argv) must not run the startup version check")

    monkeypatch.setattr(m, "_run_startup_version_check", forbidden)
    monkeypatch.setattr(m, "_start_startup_index_refresh", lambda _command: None)
    monkeypatch.setattr(m, "_cmd_emit_prompt", lambda _args: 0)

    assert m.main(["emit-prompt", "pre-qa"]) == 0


def test_startup_version_check_has_one_call_site_per_real_entrypoint() -> None:
    """module と console bootstrap が各1回だけ共通 checker を呼ぶ。"""
    import ast

    main_tree = ast.parse(Path(m.__file__).resolve().read_text(encoding="utf-8"))
    main_calls = [
        node
        for node in ast.walk(main_tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "_run_startup_version_check"
    ]
    bootstrap_tree = ast.parse(Path(sv.__file__).resolve().read_text(encoding="utf-8"))
    console_main = next(
        node
        for node in bootstrap_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "console_main"
    )
    console_calls = [
        node
        for node in ast.walk(console_main)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "check_startup_version"
    ]

    assert len(main_calls) == 1
    assert len(console_calls) == 1


def test_internal_version_marker_is_not_published_as_user_setting() -> None:
    """専用 process-tree marker の具体名を users-guide へ公開しない。"""
    repo_root = Path(m.__file__).resolve().parent.parent
    published = [
        path.relative_to(repo_root).as_posix()
        for path in (repo_root / "users-guide").rglob("*.md")
        if sv._CHECKED_ENV in path.read_text(encoding="utf-8")
    ]

    assert published == []
