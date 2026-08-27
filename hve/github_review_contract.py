"""Pull Request review の event / body 検証を一元化する純粋契約。"""

from __future__ import annotations

from typing import Optional

__all__ = [
    "ALLOWED_EVENTS",
    "ReviewValidationError",
    "validate_pull_request_review",
]

ALLOWED_EVENTS = ("APPROVE", "REQUEST_CHANGES", "COMMENT")
_BODY_REQUIRED_EVENTS = frozenset(("REQUEST_CHANGES", "COMMENT"))


class ReviewValidationError(ValueError):
    """Pull Request review の event / body が契約外であることを示す。"""

    def __init__(self, message: str, user_message: str) -> None:
        super().__init__(message)
        self.user_message = user_message


def validate_pull_request_review(
    event: object,
    body: object,
) -> tuple[str, Optional[str]]:
    """event と body を検証し、payload に使える値を返す。"""
    if not isinstance(event, str) or event not in ALLOWED_EVENTS:
        raise ReviewValidationError(
            f"invalid review event {event!r}. expected one of {list(ALLOWED_EVENTS)}",
            "レビューの種類を解釈できませんでした。",
        )
    if body is not None and not isinstance(body, str):
        raise ReviewValidationError(
            "review body must be a string or None",
            "レビュー本文を解釈できませんでした。",
        )
    if event in _BODY_REQUIRED_EVENTS and not (body or "").strip():
        raise ReviewValidationError(
            f"review body is required for {event}",
            "REQUEST_CHANGES / COMMENT ではレビュー本文を入力してください。",
        )
    return event, body