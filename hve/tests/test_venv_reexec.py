"""`_reexec_in_venv_if_needed` の単体テスト。

システム Python から ``python -m hve`` が起動された場合に、リポジトリ同梱の
``.venv`` の Python へ自動再 exec する挙動を検証する。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import hve.__main__ as m


def _expected_venv_py() -> Path:
    """関数本体と同じロジックで .venv の Python パスを算出する。"""
    repo_root = Path(m.__file__).resolve().parent.parent
    if os.name == "nt":
        return repo_root / ".venv" / "Scripts" / "python.exe"
    return repo_root / ".venv" / "bin" / "python"


@pytest.fixture(autouse=True)
def _clean_optout_env(monkeypatch):
    monkeypatch.delenv("HVE_NO_VENV_REEXEC", raising=False)
    yield


def test_optout_env_skips_reexec(monkeypatch):
    """HVE_NO_VENV_REEXEC=1 のときは何もしない。"""
    monkeypatch.setenv("HVE_NO_VENV_REEXEC", "1")

    def _boom(*_a, **_k):  # 呼ばれてはならない
        raise AssertionError("subprocess.run must not be called when opted out")

    monkeypatch.setattr(subprocess, "run", _boom)
    # 例外も SystemExit も発生せず、静かに return すること。
    assert m._reexec_in_venv_if_needed() is None


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
    assert m._reexec_in_venv_if_needed() is None


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
        m._reexec_in_venv_if_needed()

    assert exc_info.value.code == 7
    # 再構築されたコマンドが `<venv_py> -m hve gui` であること。
    assert captured["argv"][0] == str(venv_py)
    assert captured["argv"][1:3] == ["-m", "hve"]
    assert captured["argv"][3:] == ["gui"]
    # 再帰防止フラグが注入されていること。
    assert captured["env"]["HVE_NO_VENV_REEXEC"] == "1"
