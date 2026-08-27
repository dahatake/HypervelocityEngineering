"""Git ref 名の副作用なし共通検証。"""

from __future__ import annotations

_INVALID_BRANCH_CHARS = frozenset(" ~^:?*[\\")


def is_valid_branch_name(value: object) -> bool:
    """``git check-ref-format --branch`` 相当の主要制約を検証する。"""
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if value == "@" or value.startswith(("-", "/")):
        return False
    if value.endswith(("/", ".")) or "//" in value or ".." in value or "@{" in value:
        return False
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        return False
    if any(char in _INVALID_BRANCH_CHARS for char in value):
        return False
    return all(
        part and not part.startswith(".") and not part.endswith(".lock")
        for part in value.split("/")
    )


__all__ = ["is_valid_branch_name"]
