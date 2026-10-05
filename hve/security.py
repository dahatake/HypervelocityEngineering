"""security.py — HVE 共通の最小サニタイズ関数。

用途の異なる次の2関数を提供する。

- ``sanitize_user_input``: free-textをLLM promptへ埋め込む前の構造保護。
- ``sanitize_diagnostic_text``: 診断・ログ表示前の代表的なcredentialマスク。

後者は完全な秘密情報検出を保証しない。permission判定やprompt injection対策の
代替として使わず、診断出力の防御層にだけ使用する。
"""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

# ユーザー入力のデフォルト最大長
_DEFAULT_MAX_LENGTH: int = 10_000

# LLM プロンプト構造を破壊する可能性がある区切りトークン
# <system>, </system>, <assistant>, </assistant>, <user>, </user> のみを対象とする。
# 正常な日本語・Markdown・コード入力を壊さないよう最小限に限定する。
_PROMPT_DELIMITER_PATTERN = re.compile(
    r"(</?(?:system|assistant|user)>)",
    re.IGNORECASE,
)


def sanitize_diagnostic_text(text: str) -> str:
    """診断用テキストの代表的な認証トークン・password・JWTをマスクする。

    完全なサニタイズは保証しないため、credentialを保存可能にする判定や
    ``sanitize_user_input``の代替には使用しない。
    """
    if not text:
        return ""
    sanitized = text
    sanitized = re.sub(
        r"(?i)\b(authorization\s*:\s*)(bearer|basic)\s+([A-Za-z0-9._~+/=-]+)",
        r"\1\2 [REDACTED]",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)\b(token|access_token|refresh_token|id_token|api[_-]?key|apikey|password|passwd|pwd|secret|client[_-]?secret)\b(\s*[:=]\s*)([^\s,;]+)",
        r"\1\2[REDACTED]",
        sanitized,
    )
    return re.sub(
        r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9._-]+\.[A-Za-z0-9._-]+\b",
        "[REDACTED]",
        sanitized,
    )


def is_sanitization_enabled() -> bool:
    """HVE_PROMPT_SANITIZATION 環境変数でサニタイズが有効かを返す。

    デフォルトは有効（セキュリティ機能のため安全側のデフォルト）。
    緊急回避用に ``HVE_PROMPT_SANITIZATION=false`` で無効化できる。
    """
    raw = os.environ.get("HVE_PROMPT_SANITIZATION", "").strip().lower()
    if raw in ("false", "0", "no"):
        return False
    return True


def sanitize_user_input(text: str, max_length: int = _DEFAULT_MAX_LENGTH) -> str:
    """Issue Template の free-text 入力をサニタイズする。

    プロンプトインジェクション対策として以下を実施する:

    1. **制御文字除去**: ``\\x00``〜``\\x1f`` のうち ``\\t``・``\\n``・``\\r`` 以外を除去
    2. **区切りトークンのエスケープ**: ``<system>``・``</system>``・``<assistant>``・
       ``</assistant>``・``<user>``・``</user>`` をバッククォートで囲んで無効化
    3. **最大長制限**: デフォルト 10000 文字。超過時は切り詰め＋警告ログ出力

    サニタイズが発動した場合のみ警告ログを出力する（差分デバッグ用）。
    ``HVE_PROMPT_SANITIZATION=false`` で機能を無効化できる（緊急回避用）。

    Args:
        text: サニタイズ対象の文字列
        max_length: 最大文字数（デフォルト 10000）

    Returns:
        サニタイズ後の文字列
    """
    if not text:
        return text

    if not is_sanitization_enabled():
        return text

    original_len = len(text)
    result = text

    # 1. 制御文字除去（\t=0x09, \n=0x0a, \r=0x0d は保持）
    # \x00-\x08: NUL〜BS, \x0b: VT, \x0c: FF, \x0e-\x1f: SO〜US
    result = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", result)

    # 2. LLM プロンプト区切りトークンのエスケープ
    result = _PROMPT_DELIMITER_PATTERN.sub(r"`\1`", result)

    # 3. 最大長制限
    if len(result) > max_length:
        logger.warning(
            "sanitize_user_input: 入力が最大長 %d 文字を超えています（%d 文字）。切り詰めます。",
            max_length,
            len(result),
        )
        result = result[:max_length]

    # サニタイズが発動した場合のみ差分を警告ログに出力
    if result != text:
        logger.warning(
            "sanitize_user_input: 入力がサニタイズされました（元 %d 文字 → 後 %d 文字）。",
            original_len,
            len(result),
        )

    return result
