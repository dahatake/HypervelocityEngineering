"""hve.mdq_enforcement — Agent への markdown-query Skill 利用強制プロンプト生成。

GUI 設定 ``[mdq] target_folders`` が非空のとき、Agent が当該フォルダ配下の
Markdown を参照する際に ``python -m mdq search`` を最優先で使用するよう強制
する追加プロンプトを生成する。空のときは ``None`` を返し、呼び出し側は何も
注入しない（要件: 「設定がなければ、何もしない」）。

設計:
  - 副作用なし・純関数。テスト容易性を優先。
  - 出力は日本語の命令形ブロック。Skill 定義 (.github/skills/markdown-query/SKILL.md)
    の USE FOR / PREFER OVER と整合させる。
"""
from __future__ import annotations

from typing import Iterable, Optional

try:  # pragma: no cover - script-style import compatibility
    from .prompt_loader import load_prompt_file
except ImportError:  # pragma: no cover
    from prompt_loader import load_prompt_file  # type: ignore[no-redef]


def build_enforcement_prompt(target_folders: Iterable[str]) -> Optional[str]:
    """対象フォルダリストから Agent 向け強制プロンプトを生成する。

    Args:
        target_folders: GUI で設定済みのリポジトリ相対フォルダリスト。

    Returns:
        非空リストが与えられたとき: 強制プロンプト文字列。
        空または None: ``None``（呼び出し側で注入スキップ）。
    """
    folders = [f.strip() for f in (target_folders or []) if f and str(f).strip()]
    if not folders:
        return None

    template_lines = load_prompt_file(
        "runtime/addenda/mdq-enforcement.prompt.md"
    ).splitlines()
    if len(template_lines) < 8 or template_lines[3].rstrip() != "対象フォルダ:":
        raise ValueError(
            "mdq enforcement addendum template が不正です: runtime/addenda/mdq-enforcement.prompt.md"
        )
    folder_list = [f"  - `{f}`" for f in folders]
    return "\n".join([
        *template_lines[:4],
        *folder_list,
        *template_lines[4:],
    ]) + "\n"
