"""hve.gui.copilot_cli_bridge — GitHub Copilot CLI 薄いラッパ。

GUI Orchestrator が GitHub Copilot CLI を **唯一の信頼ソース** として扱うための
ブリッジ層。バイナリの解決と ``copilot login`` の実行を担う。
Plugin / MCP / Skill の一覧は SDK discovery（``hve.toolsearch.resource_inventory``）
が単一実装であり、本モジュールは CLI subprocess による列挙を持たない（FR-GUI-51）。

設計方針:
    - 例外を呼び出し側に伝播させない（失敗時は None / False / 負の終了コード）。
    - サブプロセス起動は同期 (subprocess.run, timeout 付き)。
    - GUI/UI スレッドからは ``QThread`` 等で包んで呼ぶこと（本モジュールは UI 非依存）。

参考: ``work/copilot-cli-bridge/T00-cli-survey.md`` （実機調査結果）
"""

from __future__ import annotations

import os
import subprocess
from typing import List, Optional

__all__ = ["CopilotCliBridge"]


class CopilotCliBridge:
    """``copilot`` CLI を呼び出すためのインスタンスレス薄ラッパ。

    すべてのメソッドはステートレスで、内部キャッシュも持たない（呼び出し側で
    必要なら ``functools.lru_cache`` 等を被せる）。
    """

    # ------------------------------------------------------------
    # バイナリ解決
    # ------------------------------------------------------------
    @staticmethod
    def find_binary() -> Optional[str]:
        """SDKが実セッションで選ぶ``copilot`` runtime pathを返す。"""
        try:
            from hve.auth import find_copilot_binary
        except ImportError:
            return None
        try:
            return find_copilot_binary()
        except Exception:
            return None

    @classmethod
    def is_available(cls) -> bool:
        """``copilot`` バイナリが解決できるかを返す。"""
        return cls.find_binary() is not None

    # ------------------------------------------------------------
    # 内部: subprocess 実行
    # ------------------------------------------------------------
    @staticmethod
    def _run(
        argv: List[str], *, timeout: float, cwd: Optional[str] = None
    ) -> tuple[int, str, str]:
        """``subprocess.run`` を ``capture_output=True, text=True`` で実行。

        Returns:
            ``(returncode, stdout, stderr)`` のタプル。
            起動失敗 / タイムアウト時は ``(-1, "", <reason>)``。
        """
        try:
            proc = subprocess.run(
                argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
                creationflags=(
                    getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    if os.name == "nt"
                    else 0
                ),
            )
        except subprocess.TimeoutExpired:
            return -1, "", f"timeout after {timeout}s"
        except FileNotFoundError as exc:
            return -1, "", f"binary not found: {exc}"
        except Exception as exc:  # pragma: no cover - 防御的
            return -1, "", f"{type(exc).__name__}: {exc}"
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    # ------------------------------------------------------------
    # 認証関連 (既存 hve.auth へ委譲)
    # ------------------------------------------------------------
    @staticmethod
    def is_logged_in(*, timeout: float = 30.0) -> bool:
        """GitHub Copilot に認証済かどうか。"""
        try:
            from hve import auth as _auth
        except ImportError:
            return False
        try:
            return bool(_auth.is_authenticated(timeout=timeout))
        except Exception:
            return False

    @staticmethod
    def run_login_blocking(
        *, host: str = "https://github.com", timeout: Optional[float] = None
    ) -> int:
        """``copilot login`` を同期実行する。GUI からはワーカースレッド経由で呼ぶこと。

        Returns:
            終了コード（0=成功）。バイナリ未検出は ``-1``、タイムアウトは ``-2``。
        """
        try:
            from hve import auth as _auth
        except ImportError:
            return -1
        exe = CopilotCliBridge.find_binary()
        if not exe:
            return -1
        try:
            return int(_auth.run_login(host=host, binary=exe, timeout=timeout))
        except subprocess.TimeoutExpired:
            return -2
        except Exception:
            return -1
