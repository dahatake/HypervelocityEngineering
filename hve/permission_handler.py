"""permission_handler.py — ScopedPermissionHandler

自己改善ループ（Self-Improve）で使用する、
操作スコープを制限したカスタム PermissionHandler。

許可する操作:
    - ファイル読み書き（work/ および qa/ ディレクトリ配下のみ）
    - grep / ruff / pytest の実行
    - markdownlint の実行

拒否する操作:
    - rm -rf（ファイル破壊）
    - git push --force（Git 破壊）
    - az resource delete / az group delete（Azure 破壊）
    - その他の破壊的コマンド（Skill harness-safety-guard 準拠）
"""

from __future__ import annotations

import re
from typing import Any, List


# ---------------------------------------------------------------------------
# 安全ガード定義（Skill harness-safety-guard 準拠）
# ---------------------------------------------------------------------------

# CRITICAL 停止: 絶対に実行しない
_CRITICAL_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"rm\s+-rf\s+[/~\.]"),
    re.compile(r"DROP\s+(TABLE|DATABASE)", re.IGNORECASE),
    re.compile(r"TRUNCATE", re.IGNORECASE),
    re.compile(r"az\s+resource\s+delete"),
    re.compile(r"az\s+group\s+delete"),
]

# HIGH 停止: 確認要求
_HIGH_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"git\s+push\s+--force"),
    re.compile(r"git\s+reset\s+--hard"),
    re.compile(r"git\s+checkout\s+\."),
]

# 許可するコマンドプレフィックス
_ALLOWED_COMMANDS: tuple[str, ...] = (
    "ruff",
    "pytest",
    "markdownlint",
    "grep",
    "find",
    "cat",
    "ls",
    "echo",
    "python",
    "python3",
)

# 許可するファイルパスプレフィックス
_ALLOWED_WRITE_PATHS: tuple[str, ...] = (
    "work/",
    "qa/",
    "./work/",
    "./qa/",
)


class ScopedPermissionHandler:
    """Self-Improve ループ専用の PermissionHandler。

    Copilot SDK の PermissionHandler プロトコルに準拠し、
    Skill harness-safety-guard を実装する。

    使用方法:
        handler = ScopedPermissionHandler()
        session_opts["on_permission_request"] = handler.handle
    """

    def __init__(self, strict: bool = True) -> None:
        """初期化。

        Args:
            strict: True の場合、許可リスト外の操作を全て拒否する（デフォルト: True）。
                    False の場合、CRITICAL/HIGH パターンのみ拒否する。
        """
        self.strict = strict
        self._denied_operations: List[str] = []

    def handle(self, permission_request: Any) -> bool:
        """PermissionHandler コールバック。

        Args:
            permission_request: Copilot SDK の PermissionRequest オブジェクト。

        Returns:
            True: 操作を許可、False: 操作を拒否。
        """
        operation = self._extract_operation(permission_request)
        return self._evaluate(operation)

    def _extract_operation(self, req: Any) -> str:
        """PermissionRequest から操作文字列を抽出する。"""
        # SDK の PermissionRequest は tool_name と arguments を持つことが多い
        tool_name = getattr(req, "tool_name", "") or getattr(req, "toolName", "") or ""
        arguments = getattr(req, "arguments", {}) or {}

        if isinstance(arguments, dict):
            cmd = arguments.get("command", "") or arguments.get("cmd", "")
            path = arguments.get("path", "") or arguments.get("filePath", "")
            return f"{tool_name} {cmd} {path}".strip()
        return str(tool_name)

    def _evaluate(self, operation: Any) -> bool:
        """操作を評価して許可/拒否を返す。

        Args:
            operation: 操作文字列または dict 形式の PermissionRequest。
                       dict の場合は "operation" または "command" キーを使用する。
        """
        # dict 形式（PermissionRequest 辞書）のサポート
        if isinstance(operation, dict):
            operation = (
                operation.get("operation")
                or operation.get("command")
                or operation.get("cmd")
                or str(operation)
            )
        elif not isinstance(operation, str):
            operation = str(operation)

        # CRITICAL パターン: 絶対拒否
        for pattern in _CRITICAL_PATTERNS:
            if pattern.search(operation):
                self._denied_operations.append(f"[CRITICAL] {operation}")
                return False

        # HIGH パターン: 拒否（確認要求の代わりに拒否）
        for pattern in _HIGH_PATTERNS:
            if pattern.search(operation):
                self._denied_operations.append(f"[HIGH] {operation}")
                return False

        if not self.strict:
            return True

        # strict モード: 許可リストに一致するコマンドのみ許可
        # _extract_operation() の先頭には tool_name が付与されるため、
        # 判定は全文字列と、tool_name を除いたコマンド部分の両方で行う
        op_lower = operation.lower()
        first_space = op_lower.find(" ")
        # tool_name プレフィックスを除いたコマンド部分（例: "shell ruff check ." → "ruff check ."）
        stripped_cmd_lower = op_lower[first_space + 1:].lstrip() if first_space != -1 else op_lower
        for allowed in _ALLOWED_COMMANDS:
            if op_lower.startswith(allowed) or stripped_cmd_lower.startswith(allowed):
                return True

        # ファイル書き込みパス制限
        if any(word in op_lower for word in ("write", "save", "create", "overwrite")):
            for allowed_path in _ALLOWED_WRITE_PATHS:
                if allowed_path in operation:
                    return True
            # 許可パス外への書き込みは拒否
            self._denied_operations.append(f"[PATH_DENIED] {operation}")
            return False

        # strict モード: 許可リスト/許可パスに一致しない操作はデフォルト拒否
        self._denied_operations.append(f"[STRICT_DENIED] {operation}")
        return False

    @property
    def denied_operations(self) -> List[str]:
        """拒否した操作のリストを返す（デバッグ用）。"""
        return list(self._denied_operations)

    def clear_denied(self) -> None:
        """拒否リストをクリアする。"""
        self._denied_operations.clear()


def is_safe_command(command: str) -> bool:
    """コマンド文字列が安全かどうかを判定するスタンドアロン関数。

    Skill harness-safety-guard 準拠。

    Args:
        command: チェックするコマンド文字列。

    Returns:
        True: 安全（実行可能）、False: 危険（実行不可）。
    """
    for pattern in _CRITICAL_PATTERNS + _HIGH_PATTERNS:
        if pattern.search(command):
            return False
    return True
