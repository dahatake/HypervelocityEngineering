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


_BLOCK_HEADER = "# Markdown-Query Skill 強制利用ルール (GUI 設定由来)"


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

    folder_list = "\n".join(f"  - `{f}`" for f in folders)
    return (
        f"{_BLOCK_HEADER}\n"
        "以下のフォルダ配下の Markdown ファイル (.md) を参照する必要が生じた場合は、"
        "`read_file` や `grep_search` を使う前に、必ず `markdown-query` Skill"
        " (`python -m mdq search --q \"<キーワード>\" --top-k 5 --max-tokens 800`)"
        " を最優先で使用すること。\n"
        "\n対象フォルダ:\n"
        f"{folder_list}\n"
        "\n例外:\n"
        "  - `python -m mdq search` のヒットが 0 件のとき、または対象が `.md` 以外のとき"
        "に限り、`grep_search` / `read_file` へフォールバックしてよい。\n"
        "  - 索引未生成・索引が古いと判定された場合は `python -m mdq index` を実行してから再検索する。\n"
    )
