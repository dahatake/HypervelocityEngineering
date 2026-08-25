"""hve — GitHub Copilot SDK ローカルオーケストレーター

python -m hve で実行可能な Python パッケージです。
使い方:
    python -m hve orchestrate --workflow aad
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__version__ = "0.8.46"

# 公開属性 -> 実体を持つサブモジュール名。
# 遅延解決にすることで `import hve` 自体が重い依存 (cq / copilot SDK / PySide6 等)
# を引き込まなくなり、`hve.__main__` の .venv 再 exec ガードが依存解決より先に動く。
_LAZY_ATTRS: dict[str, str] = {
    "SDKConfig": "config",
    "Console": "console",
    "REVIEW_PROMPT": "prompts",
    "CODE_REVIEW_AGENT_FIX_PROMPT": "prompts",
    "CODE_REVIEW_CLI_PROMPT": "prompts",
    "ADVERSARIAL_RECHECK_PROMPT": "prompts",
    "QA_PROMPT_V2": "prompts",
    "QA_MERGE_SAVE_PROMPT": "prompts",
    "QA_CONSOLIDATE_PROMPT": "prompts",
    "PRE_EXECUTION_QA_PROMPT_V2": "prompts",
    "MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT": "prompts",
    "is_workiq_available": "workiq",
    "build_workiq_mcp_config": "workiq",
    "StepRunner": "runner",
    "QAMerger": "qa_merger",
    "QADocument": "qa_merger",
    "QAQuestion": "qa_merger",
    "Choice": "qa_merger",
}

__all__ = ["__version__", *_LAZY_ATTRS]


def __getattr__(name: str) -> Any:
    module_name = _LAZY_ATTRS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(f".{module_name}", __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})


if TYPE_CHECKING:  # 型チェッカ / IDE 向けの静的な再エクスポート
    from .config import SDKConfig
    from .console import Console
    from .prompts import (
        ADVERSARIAL_RECHECK_PROMPT,
        CODE_REVIEW_AGENT_FIX_PROMPT,
        CODE_REVIEW_CLI_PROMPT,
        MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT,
        PRE_EXECUTION_QA_PROMPT_V2,
        QA_CONSOLIDATE_PROMPT,
        QA_MERGE_SAVE_PROMPT,
        QA_PROMPT_V2,
        REVIEW_PROMPT,
    )
    from .qa_merger import Choice, QADocument, QAMerger, QAQuestion
    from .runner import StepRunner
    from .workiq import build_workiq_mcp_config, is_workiq_available
