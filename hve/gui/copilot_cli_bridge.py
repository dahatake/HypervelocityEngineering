"""hve.gui.copilot_cli_bridge — GitHub Copilot CLI 薄いラッパ。

GUI Orchestrator が GitHub Copilot CLI を **唯一の信頼ソース** として扱うための
ブリッジ層。CLI のサブコマンド (``copilot mcp list`` / ``copilot mcp get`` /
``copilot plugin list`` / ``copilot login``) を呼び出し、stdout を解析して
構造化データを返す。

設計方針:
    - 例外を呼び出し側に伝播させない（失敗時は空 dict / None / False）。
    - サブプロセス起動は同期 (subprocess.run, timeout 付き)。
    - GUI/UI スレッドからは ``QThread`` 等で包んで呼ぶこと（本モジュールは UI 非依存）。
    - JSON 出力可能なコマンドは必ず ``--json`` を使う（text 解析は最小化）。
    - ``copilot plugin list`` のみ ``--json`` 未対応のため行ベース正規表現で解析。

参考: ``work/copilot-cli-bridge/T00-cli-survey.md`` （実機調査結果）
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

__all__ = ["CopilotCliBridge", "PluginInfo"]


# ``copilot plugin list`` 1 行の形式:
#   "  • <plugin-name>@<source> (v<version>)"
# bullet 記号は環境エンコーディング次第で文字化けし得るため、
# 行頭の英数字以外の任意 1 文字以上をスキップして name@source 部を捕捉する。
_PLUGIN_LINE_RE = re.compile(
    r"^\s*[^\w\s]+\s+(?P<name>[A-Za-z0-9_.\-]+)@(?P<source>[A-Za-z0-9_.\-]+)\s+\(v(?P<version>[^)]+)\)\s*$"
)


@dataclass(frozen=True)
class PluginInfo:
    """``copilot plugin list`` の 1 エントリ。"""

    name: str
    source: str
    version: str


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
        """``copilot`` 実行ファイル絶対パスを返す。見つからなければ ``None``。

        既存 ``hve.auth.find_copilot_binary`` を再利用 (SDK 同梱 → PATH)。
        """
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
        argv: List[str], *, timeout: float
    ) -> tuple[int, str, str]:
        """``subprocess.run`` を ``capture_output=True, text=True`` で実行。

        Returns:
            ``(returncode, stdout, stderr)`` のタプル。
            起動失敗 / タイムアウト時は ``(-1, "", <reason>)``。
        """
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return -1, "", f"timeout after {timeout}s"
        except FileNotFoundError as exc:
            return -1, "", f"binary not found: {exc}"
        except Exception as exc:  # pragma: no cover - 防御的
            return -1, "", f"{type(exc).__name__}: {exc}"
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    # ------------------------------------------------------------
    # MCP server 列挙
    # ------------------------------------------------------------
    @classmethod
    def list_mcp_servers(cls, *, timeout: float = 15.0) -> Dict[str, Dict[str, Any]]:
        """``copilot mcp list --json`` を実行し ``{name: <ServerDef>}`` を返す。

        失敗時は空 dict を返す。
        """
        exe = cls.find_binary()
        if not exe:
            return {}
        rc, out, _err = cls._run([exe, "mcp", "list", "--json"], timeout=timeout)
        if rc != 0 or not out.strip():
            return {}
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            return {}
        servers = data.get("mcpServers") if isinstance(data, dict) else None
        if not isinstance(servers, dict):
            return {}
        out_dict: Dict[str, Dict[str, Any]] = {}
        for name, defn in servers.items():
            if isinstance(name, str) and isinstance(defn, dict):
                out_dict[name] = defn
        return out_dict

    @classmethod
    def get_mcp_server(
        cls, name: str, *, timeout: float = 15.0
    ) -> Optional[Dict[str, Any]]:
        """``copilot mcp get <name> --json`` を実行し ``<ServerDef>`` を返す。

        失敗 / 未登録時は ``None``。
        """
        if not name:
            return None
        exe = cls.find_binary()
        if not exe:
            return None
        rc, out, _err = cls._run(
            [exe, "mcp", "get", name, "--json"], timeout=timeout
        )
        if rc != 0 or not out.strip():
            return None
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        defn = data.get(name)
        return defn if isinstance(defn, dict) else None

    # ------------------------------------------------------------
    # Plugin 列挙 (text 解析)
    # ------------------------------------------------------------
    @classmethod
    def list_plugins(cls, *, timeout: float = 15.0) -> List[PluginInfo]:
        """``copilot plugin list`` を実行し ``PluginInfo`` のリストを返す。

        ``--json`` 未対応（v1.0.48 時点）のため行ベース正規表現で解析する。
        失敗時は空リストを返す。
        """
        exe = cls.find_binary()
        if not exe:
            return []
        rc, out, _err = cls._run([exe, "plugin", "list"], timeout=timeout)
        if rc != 0:
            return []
        plugins: List[PluginInfo] = []
        for line in out.splitlines():
            m = _PLUGIN_LINE_RE.match(line)
            if not m:
                continue
            plugins.append(
                PluginInfo(
                    name=m.group("name"),
                    source=m.group("source"),
                    version=m.group("version"),
                )
            )
        return plugins

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
