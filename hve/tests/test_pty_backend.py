"""hve/tests/test_pty_backend.py — PTY バックエンド抽象レイヤのテスト。

実 PTY が必要なテストは ``pty_backend.is_pty_available()`` が False の環境
(CI など) では skip する。Windows / POSIX 両対応。
"""

from __future__ import annotations

import sys
import time

import pytest

from hve.gui import pty_backend


# ---------------------------------------------------------------------------
# 純粋ロジック (バックエンド不在でも実行可能)
# ---------------------------------------------------------------------------


def test_spawn_rejects_empty_argv() -> None:
    """空 argv は PtyBackendError。"""
    with pytest.raises(pty_backend.PtyBackendError):
        pty_backend.spawn([])


def test_spawn_rejects_non_list_argv() -> None:
    """argv が list[str] でない場合は PtyBackendError。"""
    with pytest.raises(pty_backend.PtyBackendError):
        pty_backend.spawn(["echo", 123])  # type: ignore[list-item]


def test_missing_dependency_hint_mentions_extras() -> None:
    """エラーメッセージに extras インストール手順が含まれる。"""
    hint = pty_backend.missing_dependency_hint()
    assert "gui-pty" in hint


# ---------------------------------------------------------------------------
# 実 PTY 起動テスト (依存があれば実行)
# ---------------------------------------------------------------------------


pty_required = pytest.mark.skipif(
    not pty_backend.is_pty_available(),
    reason="PTY backend (pywinpty/ptyprocess) not installed",
)


def _echo_argv() -> list[str]:
    """プラットフォーム別の "hello を出力して終わる" コマンド。"""
    if sys.platform.startswith("win"):
        # cmd.exe の echo は確実に存在する
        return ["cmd.exe", "/c", "echo hello"]
    return ["/bin/sh", "-c", "echo hello"]


def _read_until_eof(sess: pty_backend.PtySession, timeout: float = 5.0) -> bytes:
    """子プロセスが終了し、かつバッファ空になるまで読み続ける。"""
    deadline = time.monotonic() + timeout
    buf = bytearray()
    while time.monotonic() < deadline:
        chunk = sess.read_nowait(4096)
        if chunk:
            buf.extend(chunk)
            continue
        if not sess.is_alive():
            # 終了後にも残バッファを念のため 1 度読む
            tail = sess.read_nowait(4096)
            if tail:
                buf.extend(tail)
                continue
            break
        time.sleep(0.05)
    return bytes(buf)


@pty_required
def test_spawn_echo_produces_output() -> None:
    """単純な echo コマンドが PTY 経由で出力を返す。"""
    sess = pty_backend.spawn(_echo_argv())
    try:
        out = _read_until_eof(sess, timeout=10.0)
    finally:
        sess.close(grace_seconds=1.0)
    assert b"hello" in out, f"unexpected output: {out!r}"


@pty_required
def test_close_terminates_long_running_process() -> None:
    """無限ループのプロセスを close() で確実に終了させる。"""
    if sys.platform.startswith("win"):
        argv = ["cmd.exe", "/c", "ping -n 60 127.0.0.1 > NUL"]
    else:
        argv = ["/bin/sh", "-c", "sleep 30"]
    sess = pty_backend.spawn(argv)
    assert sess.is_alive()
    code = sess.close(grace_seconds=1.0)
    assert not sess.is_alive()
    # exit_code は OS により 0 でない値が入りうる (terminated by signal 等)
    # 値そのものは検証せず、取得可能であることのみ確認。
    _ = code
