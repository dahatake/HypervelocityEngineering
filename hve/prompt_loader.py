"""prompt_loader.py — Load Agent prompt body from `.github/prompts/<name>.prompt.md`.

Q1=C 移行後の SDK 注入用。`custom_agents` / `agent` キーは SDK に渡さず、
返値の文字列をメインセッション送信プロンプトの先頭に前置する用途。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

_DEFAULT_PROMPTS_DIR = Path(__file__).resolve().parent.parent / ".github" / "prompts"


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
    base = prompts_dir if prompts_dir is not None else _DEFAULT_PROMPTS_DIR
    path = base / f"{agent_name}.prompt.md"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")
