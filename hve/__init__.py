"""hve — GitHub Copilot SDK ローカルオーケストレーター

python -m hve で実行可能な Python パッケージです。
使い方:
    python -m hve orchestrate --workflow aad
"""

from __future__ import annotations

__version__ = "0.1.0"

try:
    from .config import SDKConfig
    from .console import Console
    from .prompts import QA_PROMPT, QA_APPLY_PROMPT, REVIEW_PROMPT, CODE_REVIEW_AGENT_FIX_PROMPT, ADVERSARIAL_RECHECK_PROMPT
    from .runner import StepRunner
except ImportError:
    from config import SDKConfig  # type: ignore[no-redef]
    from console import Console  # type: ignore[no-redef]
    from prompts import QA_PROMPT, QA_APPLY_PROMPT, REVIEW_PROMPT, CODE_REVIEW_AGENT_FIX_PROMPT, ADVERSARIAL_RECHECK_PROMPT  # type: ignore[no-redef]
    from runner import StepRunner  # type: ignore[no-redef]

__all__ = [
    "__version__",
    "SDKConfig",
    "Console",
    "QA_PROMPT",
    "QA_APPLY_PROMPT",
    "REVIEW_PROMPT",
    "CODE_REVIEW_AGENT_FIX_PROMPT",
    "ADVERSARIAL_RECHECK_PROMPT",
    "StepRunner",
]
