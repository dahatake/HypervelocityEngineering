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
    from .prompts import (
        QA_PROMPT, QA_APPLY_PROMPT, REVIEW_PROMPT,
        CODE_REVIEW_AGENT_FIX_PROMPT, CODE_REVIEW_CLI_PROMPT, ADVERSARIAL_RECHECK_PROMPT,
        QA_PROMPT_V2, QA_MERGE_SAVE_PROMPT, QA_CONSOLIDATE_PROMPT,
    )
    from .workiq import is_workiq_available, build_workiq_mcp_config
    from .runner import StepRunner
    from .qa_merger import QAMerger, QADocument, QAQuestion, Choice
except ImportError:
    from config import SDKConfig  # type: ignore[no-redef]
    from console import Console  # type: ignore[no-redef]
    from prompts import (  # type: ignore[no-redef]
        QA_PROMPT, QA_APPLY_PROMPT, REVIEW_PROMPT,
        CODE_REVIEW_AGENT_FIX_PROMPT, CODE_REVIEW_CLI_PROMPT, ADVERSARIAL_RECHECK_PROMPT,
        QA_PROMPT_V2, QA_MERGE_SAVE_PROMPT, QA_CONSOLIDATE_PROMPT,
    )
    from workiq import is_workiq_available, build_workiq_mcp_config  # type: ignore[no-redef]
    from runner import StepRunner  # type: ignore[no-redef]
    from qa_merger import QAMerger, QADocument, QAQuestion, Choice  # type: ignore[no-redef]

__all__ = [
    "__version__",
    "SDKConfig",
    "Console",
    "QA_PROMPT",
    "QA_APPLY_PROMPT",
    "REVIEW_PROMPT",
    "CODE_REVIEW_AGENT_FIX_PROMPT",
    "CODE_REVIEW_CLI_PROMPT",
    "ADVERSARIAL_RECHECK_PROMPT",
    "QA_PROMPT_V2",
    "QA_MERGE_SAVE_PROMPT",
    "QA_CONSOLIDATE_PROMPT",
    "is_workiq_available",
    "build_workiq_mcp_config",
    "StepRunner",
    "QAMerger",
    "QADocument",
    "QAQuestion",
    "Choice",
]
