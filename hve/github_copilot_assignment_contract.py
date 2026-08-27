"""Copilot cloud agent assignment response contract.

GitHub REST API と GUI の双方が同じ pure validator を使用し、割当成功を
応答 schema から推測しないための単一実装を提供する。
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "COPILOT_AGENT_LOGIN",
    "CopilotAssignmentContractError",
    "validate_copilot_assignment_response",
]

COPILOT_AGENT_LOGIN = "copilot-swe-agent[bot]"


class CopilotAssignmentContractError(ValueError):
    """Copilot 割当応答が要求対象を確認できない場合の契約エラー。"""


def validate_copilot_assignment_response(
    response: Any,
    requested_issue_number: int,
) -> dict[str, Any]:
    """割当応答が request Issue と Copilot assignee を確認することを検証する。"""
    if (
        isinstance(requested_issue_number, bool)
        or not isinstance(requested_issue_number, int)
        or requested_issue_number <= 0
    ):
        raise CopilotAssignmentContractError(
            "requested issue number must be a positive integer"
        )
    if not isinstance(response, dict):
        raise CopilotAssignmentContractError(
            "assignment response did not confirm an object"
        )
    response_number = response.get("number")
    if (
        isinstance(response_number, bool)
        or not isinstance(response_number, int)
        or response_number != requested_issue_number
    ):
        raise CopilotAssignmentContractError(
            "assignment response did not confirm the requested issue number"
        )
    assignees = response.get("assignees")
    if not isinstance(assignees, list) or not any(
        isinstance(item, dict) and item.get("login") == COPILOT_AGENT_LOGIN
        for item in assignees
    ):
        raise CopilotAssignmentContractError(
            "assignment response did not confirm Copilot assignee"
        )
    return response