"""GitHub Copilot CLI を使う Issue / PR タイトル生成の単一実装（FR-GUI-39）。"""

from __future__ import annotations

import re
import subprocess
import tempfile
from typing import Any, Callable, Optional

from hve.auth import find_copilot_binary

try:
    from .prompt_loader import load_prompt_file
except ImportError:  # pragma: no cover - top-level import compatibility
    from hve.prompt_loader import load_prompt_file  # type: ignore[import-not-found,no-redef]

__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_SOURCE_CHARS",
    "MAX_TITLE_CHARS",
    "GitHubTitleGenerationError",
    "generate_github_title",
]

DEFAULT_TIMEOUT_SECONDS = 120.0
MAX_SOURCE_CHARS = 12_000
MAX_TITLE_CHARS = 120
_TARGET_KINDS = frozenset({"issue", "pull_request"})
_FENCE_RE = re.compile(r"^`{3,}[A-Za-z0-9_-]*$")
_TITLE_LABEL_RE = re.compile(r"^(?:title|タイトル)\s*[:：]\s*", re.IGNORECASE)
_LIST_PREFIX_RE = re.compile(r"^(?:[-*+]\s+|\d+[.)]\s+)")
_META_TITLE_RE = re.compile(
    r"(?:GitHub\s*タイトル|タイトル(?:を|の)?生成|入力本文|"
    r"generate\s+(?:a\s+)?(?:github\s+)?title|title\s+generation|input\s+text|"
    r"no\s+task\s+(?:was\s+)?provided|task\s+(?:was\s+)?not\s+provided|"
    r"(?:issue\s+)?description\s+not\s+(?:supplied|provided)|"
    r"(?:タスク|文章|要約対象)(?:が|は)?.{0,12}(?:提供|指定)されてい)",
    re.IGNORECASE,
)
_JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
_TITLE_GENERATION_PROMPT = load_prompt_file("runtime/gui/github-title-generator.prompt.md")


class GitHubTitleGenerationError(RuntimeError):
    """Copilot CLI から安全なタイトルを確定できない。"""


def _build_prompt(
    target_kind: str,
    source_text: str,
    *,
    fallback_title: str,
    required_prefix: str,
) -> str:
    source = source_text[:MAX_SOURCE_CHARS]
    return _TITLE_GENERATION_PROMPT.format(source_text=source)


def _unwrap_markdown(text: str) -> str:
    value = text.strip()
    pairs = (("**", "**"), ("__", "__"), ("`", "`"), ('"', '"'), ("'", "'"))
    changed = True
    while changed and value:
        changed = False
        for left, right in pairs:
            if value.startswith(left) and value.endswith(right) and len(value) > len(left) + len(right):
                value = value[len(left) : -len(right)].strip()
                changed = True
    return value


def _normalize_title(raw: Any, required_prefix: str, source_text: str) -> str:
    if not isinstance(raw, str):
        return ""
    raw = raw.split("●", 1)[0]
    lines = [
        line.strip()
        for line in raw.splitlines()
        if line.strip() and not _FENCE_RE.fullmatch(line.strip())
    ]
    if not lines:
        return ""

    title = _TITLE_LABEL_RE.sub("", lines[0])
    title = _LIST_PREFIX_RE.sub("", title)
    title = _unwrap_markdown(title)
    title = re.sub(r"[\x00-\x1f\x7f]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    if not title:
        return ""
    if _META_TITLE_RE.search(title):
        return ""
    if _JAPANESE_RE.search(source_text) and not _JAPANESE_RE.search(title):
        return ""

    prefix = re.sub(r"\s+", " ", required_prefix or "")
    if prefix and not title.casefold().startswith(prefix.casefold()):
        title = f"{prefix}{title}"
    return title[:MAX_TITLE_CHARS].rstrip()


def generate_github_title(
    target_kind: str,
    source_text: str,
    *,
    fallback_title: str = "",
    required_prefix: str = "",
    cli_path: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    runner: Callable[..., Any] = subprocess.run,
) -> str:
    """本文コンテキストから安全な 1 行タイトルを生成する。"""
    if target_kind not in _TARGET_KINDS:
        raise GitHubTitleGenerationError("タイトル生成の target 種別が不正です。")
    if not isinstance(source_text, str) or not source_text.strip():
        raise GitHubTitleGenerationError("タイトル生成に使う本文が空です。")

    executable = (cli_path or "").strip() or find_copilot_binary()
    if not executable:
        raise GitHubTitleGenerationError("GitHub Copilot CLI が見つかりません。")

    prompt = _build_prompt(
        target_kind,
        source_text,
        fallback_title=fallback_title,
        required_prefix=required_prefix,
    )
    argv = [
        executable,
        "--no-auto-update",
        "-p",
        prompt,
        "--silent",
        "--stream",
        "off",
        "--no-color",
        "--no-custom-instructions",
        "--no-ask-user",
        "--available-tools=ask_user",
        "--model",
        "auto",
        "--output-format",
        "text",
    ]
    try:
        with tempfile.TemporaryDirectory(prefix="hve-github-title-") as cwd:
            completed = runner(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
                cwd=cwd,
            )
    except subprocess.TimeoutExpired as exc:
        raise GitHubTitleGenerationError("GitHub Copilot CLI がタイムアウトしました。") from exc
    except OSError as exc:
        raise GitHubTitleGenerationError("GitHub Copilot CLI を起動できませんでした。") from exc

    returncode = getattr(completed, "returncode", -1)
    if returncode != 0:
        raise GitHubTitleGenerationError(
            f"GitHub Copilot CLI が終了コード {returncode} を返しました。"
        )

    title = _normalize_title(
        getattr(completed, "stdout", ""), required_prefix, source_text
    )
    if not title:
        raise GitHubTitleGenerationError("GitHub Copilot CLI のタイトル応答が空です。")
    return title
