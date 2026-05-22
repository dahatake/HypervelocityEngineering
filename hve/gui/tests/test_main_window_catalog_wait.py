"""R3: `_wait_catalog_ready` / `_is_catalog_ready` の単体テスト。

`MainWindow` 全体の構築は重いので、テスト対象メソッドは static / 純関数寄りなため
モック self を用いて直接呼び出す。`QApplication.processEvents` 呼出は副作用のみで
本ロジックには影響しないため、no-op で問題ない。
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hve.gui.main_window import MainWindow  # noqa: E402


def test_is_catalog_ready_missing(tmp_path: Path) -> None:
    p = tmp_path / "missing.md"
    assert MainWindow._is_catalog_ready(p) is False


def test_is_catalog_ready_empty(tmp_path: Path) -> None:
    p = tmp_path / "empty.md"
    p.write_text("", encoding="utf-8")
    assert MainWindow._is_catalog_ready(p) is False


def test_is_catalog_ready_nonzero(tmp_path: Path) -> None:
    p = tmp_path / "ok.md"
    p.write_text("data", encoding="utf-8")
    assert MainWindow._is_catalog_ready(p) is True


def test_wait_catalog_ready_immediate(tmp_path: Path) -> None:
    """既にファイルが存在する場合は即座に True を返す（リトライしない）。"""
    p = tmp_path / "ok.md"
    p.write_text("data", encoding="utf-8")
    fake_self = SimpleNamespace()
    # `_wait_catalog_ready` は self を使わず static 相当だが、bound method として呼ぶ。
    result = MainWindow._wait_catalog_ready(fake_self, p, (0.01, 0.01))  # type: ignore[arg-type]
    assert result is True


def test_wait_catalog_ready_retries_then_succeeds(tmp_path: Path) -> None:
    """ファイルが遅延生成されてもリトライで読める。"""
    p = tmp_path / "delayed.md"
    fake_self = SimpleNamespace()

    def delayed_write() -> None:
        time.sleep(0.15)
        p.write_text("data", encoding="utf-8")

    t = threading.Thread(target=delayed_write, daemon=True)
    t.start()
    # intervals=(0.05, 0.2, 0.5) — 合計 0.75s 内に書き込み完了する想定
    with patch.object(MainWindow, "_wait_catalog_ready", wraps=MainWindow._wait_catalog_ready):
        result = MainWindow._wait_catalog_ready(fake_self, p, (0.05, 0.2, 0.5))  # type: ignore[arg-type]
    t.join(timeout=2.0)
    assert result is True


def test_wait_catalog_ready_timeout(tmp_path: Path) -> None:
    """ファイルが最後まで生成されないと False。"""
    p = tmp_path / "never.md"
    fake_self = SimpleNamespace()
    result = MainWindow._wait_catalog_ready(fake_self, p, (0.01, 0.01, 0.01))  # type: ignore[arg-type]
    assert result is False
