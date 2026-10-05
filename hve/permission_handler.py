"""permission_handler.py — Step セッション用の PermissionHandler

Step セッション（NFR-SEC-04）は `build_step_permission_handler` を使い、CRITICAL パターンだけを拒否する
（Skill harness-safety-guard 準拠）。
"""

from __future__ import annotations

import re
from typing import Any, Callable, List


# ---------------------------------------------------------------------------
# 安全ガード定義（Skill harness-safety-guard 準拠）
# ---------------------------------------------------------------------------

# CRITICAL 停止: .github/skills/harness-safety-guard/references/danger-patterns.md §1
_CRITICAL_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"rm\s+-[rf]+\s+/"),
    re.compile(r"rm\s+-[rf]+\s+~"),
    re.compile(r"rm\s+-[rf]+\s+\."),
    re.compile(r"DROP\s+TABLE\b", re.IGNORECASE),
    re.compile(r"DROP\s+DATABASE\b", re.IGNORECASE),
    re.compile(r"TRUNCATE\s+TABLE\b", re.IGNORECASE),
    re.compile(r"az\s+resource\s+delete"),
    re.compile(r"az\s+group\s+delete"),
    re.compile(r"az\s+deployment\s+delete"),
    re.compile(r"az\s+keyvault\s+delete"),
    re.compile(r"az\s+storage\s+account\s+delete"),
    re.compile(r"az\s+cosmosdb\s+delete"),
    re.compile(r"az\s+sql\s+server\s+delete"),
    re.compile(r"az\s+functionapp\s+delete"),
]


def build_step_permission_handler(
    approve: Callable[[Any, Any], Any],
    warn: Callable[[str], None],
) -> Callable[[Any, Any], Any]:
    """Step セッション用の SDK 権限コールバックを返す（NFR-SEC-04）。

    シェル実行の権限要求が CRITICAL パターンに一致した場合だけ実行前に拒否して記録し、
    それ以外は `approve` へ委譲する。誤検知で長時間ジョブを止めないため HIGH 以下は拒否しない。
    """

    def _handler(request: Any, invocation: Any) -> Any:
        command = getattr(request, "full_command_text", None)
        if isinstance(command, str):
            for pattern in _CRITICAL_PATTERNS:
                if pattern.search(command):
                    from copilot.generated.rpc import PermissionDecisionReject

                    # コマンド本文は秘密値を含みうるため、記録は一致した規則だけにする
                    warn(f"CRITICAL 操作を実行前に拒否しました（規則: {pattern.pattern}）")
                    return PermissionDecisionReject(
                        feedback="CRITICAL 操作（Skill harness-safety-guard）は実行できません。"
                    )
        return approve(request, invocation)

    return _handler
