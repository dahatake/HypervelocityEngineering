"""prompt_loader.py — `.github/prompts/` を root とする Prompt 読込の単一実装。

FR-PROMPT-SRC-02: flat Agent 本文・Step bodyタfan-out 追加本文・runtime / cloud の
内部 Prompt をすべて本モジュール経由で読む。`load_prompt(agent_name)` は flat Agent
本文用の互換 facade（Q1=C 移行後の SDK 注入用。`custom_agents` / `agent` キーは
SDK へ渡さず、返値をメインセッション送信プロンプトの先頭へ前置する）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PROMPTS_DIR = _REPO_ROOT / ".github" / "prompts"
_WINDOWS_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:")


class _BlankPromptError(ValueError):
    """Internal signal used by the legacy flat compatibility facade."""


def _normalize_prompt_relative_path(relative_path: str) -> tuple[str, ...]:
    if not isinstance(relative_path, str):
        raise ValueError("prompt path must be a string")
    if not relative_path.strip():
        raise ValueError("prompt path must not be empty or whitespace-only")
    if relative_path != relative_path.strip():
        raise ValueError("prompt path must not contain leading or trailing whitespace")
    if "\\" in relative_path:
        raise ValueError("prompt path must use POSIX '/' separators")
    if relative_path.startswith("/"):
        raise ValueError("prompt path must be relative to the prompts root")
    if _WINDOWS_DRIVE_PATH_RE.match(relative_path):
        raise ValueError("prompt path must not be a Windows drive path")

    parts = relative_path.split("/")
    if parts[:2] == [".github", "prompts"]:
        parts = parts[2:]
    if not parts:
        raise ValueError("prompt path must reference a .prompt.md file")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("prompt path must not contain empty, '.' or '..' components")
    if not parts[-1].endswith(".prompt.md"):
        raise ValueError("prompt path must end with '.prompt.md'")
    return tuple(parts)


def _resolve_prompts_base(prompts_dir: Optional[Path]) -> tuple[Path, Path]:
    base = Path(prompts_dir) if prompts_dir is not None else _DEFAULT_PROMPTS_DIR
    resolved_base = base.resolve()
    if prompts_dir is None:
        repo_root = _REPO_ROOT.resolve()
        if not resolved_base.is_relative_to(repo_root):
            raise ValueError(
                "default prompts directory must resolve inside the repository root"
            )
    return base, resolved_base


def _resolve_prompt_path(relative_path: str, *, prompts_dir: Optional[Path]) -> Path:
    parts = _normalize_prompt_relative_path(relative_path)
    base, resolved_base = _resolve_prompts_base(prompts_dir)
    lexical_base = base.absolute()
    lexical_candidate = lexical_base.joinpath(*parts)
    if not lexical_candidate.is_relative_to(lexical_base):
        raise ValueError("prompt path escapes the prompts root")
    resolved_candidate = lexical_candidate.resolve()
    if not resolved_candidate.is_relative_to(resolved_base):
        raise ValueError("prompt path resolves outside the prompts root")
    return resolved_candidate


def _read_prompt_text(path: Path, *, required: bool) -> str:
    if not path.is_file():
        if required:
            raise FileNotFoundError(f"prompt file not found: {path}")
        return ""
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise _BlankPromptError("prompt file must not be empty or whitespace-only")
    return text


def load_prompt_file(
    relative_path: str, *, prompts_dir: Optional[Path] = None, required: bool = True
) -> str:
    """Load a prompt file relative to the prompts root.

    Args:
        relative_path: prompt-root-relative POSIX path, or canonical
            `.github/prompts/...` repository-relative path.
        prompts_dir: テスト用にプロンプトディレクトリを上書きする。
        required: 必須ファイルなら欠損時に FileNotFoundError を送出する。
            False のとき空文字を返すのは**欠損時だけ**で、存在するファイルが
            空・空白のみなら ValueError、不正 UTF-8 なら UnicodeDecodeError を送出する。

    Returns:
        UTF-8 decoded prompt body text.

    Raises:
        ValueError: 安全でない path、または空・空白のみの prompt ファイル。
        FileNotFoundError: `required=True` で prompt ファイルが欠損。
        UnicodeDecodeError: prompt ファイルが UTF-8 として不正。
    """
    path = _resolve_prompt_path(relative_path, prompts_dir=prompts_dir)
    return _read_prompt_text(path, required=required)


def _validate_legacy_agent_name(agent_name: str) -> None:
    if not isinstance(agent_name, str):
        raise ValueError("agent name must be a string")
    if agent_name != agent_name.strip():
        raise ValueError("agent name must not contain leading or trailing whitespace")
    if "/" in agent_name or "\\" in agent_name:
        raise ValueError("agent name must be a flat prompt name without path separators")
    if _WINDOWS_DRIVE_PATH_RE.match(agent_name):
        raise ValueError("agent name must not be a Windows drive path")


def load_prompt(agent_name: str, prompts_dir: Optional[Path] = None) -> str:
    """Return the prompt body text for the given agent name.

    Args:
        agent_name: Agent 識別子（例: "Arch-UI-List"）。空・None なら空文字を返す。
        prompts_dir: テスト用にプロンプトディレクトリを上書きする。
            未指定時はリポジトリの `.github/prompts/` を使用。

    Returns:
        プロンプト本文。ファイルが存在しない場合は空文字（呼び出し側が警告判断）。
    """
    if not agent_name:
        return ""
    _validate_legacy_agent_name(agent_name)
    try:
        return load_prompt_file(
            f"{agent_name}.prompt.md", prompts_dir=prompts_dir, required=False
        )
    except FileNotFoundError:
        return ""
    except _BlankPromptError:
        return ""


def substitute_work_placeholders(
    text: str, *, run_id: str, identifier: str = "0"
) -> str:
    """Agent プロンプト本文の WORK プレースホルダを実値へ置換する。

    各 Agent プロンプトの WORK 定義 `work/run/<run-id>/<Agent>/Issue-<識別子>/`
    は `<run-id>` `<識別子>` がリテラルのプレースホルダのまま LLM に渡るため、
    LLM が run-scoped 実パスを知らされず `work/` 直下に作業ディレクトリを
    作りうる。本関数で実値置換し、run-id 配下への作成を保証する。

    Args:
        text: 置換対象のプロンプト本文。
        run_id: `<run-id>` を置換する実値。空文字なら `<run-id>` 置換をスキップ。
        identifier: `<識別子>` を置換する実値（既定 "0"）。空文字なら置換をスキップ。

    Returns:
        置換後の文字列。
    """
    if not text:
        return text
    if run_id:
        text = text.replace("<run-id>", run_id)
    if identifier:
        text = text.replace("<識別子>", identifier)
    return text
