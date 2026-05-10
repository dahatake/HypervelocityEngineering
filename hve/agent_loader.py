"""agent_loader.py — `.github/agents/*.agent.md` を Copilot SDK Custom Agent 定義に変換する。

Phase B (Critical No.1 修正): hve runner.py が `custom_agents_config` を構築する前に、
リポジトリの `.github/agents/` 配下の Agent 定義ファイルを読み込み、SDK 形式の dict
リストとして返す。

Agent 定義ファイル（`.agent.md`）の構造:
  ---
  name: <Agent 名>
  description: <短い説明>
  tools: ['read', 'edit', ...]
  ---
  ## 1) 目的
  ...
  ## 4) Prompt 本文（LLM へ渡す本体）
  ```text
  <ここが LLM へ渡される Prompt 本文>
  ```
  ...

抽出規則:
  - YAML frontmatter から `name` `description` `tools` を取得。
  - 「## 4) Prompt 本文」見出し直後の最初のフェンス（``` で始まり ``` で閉じるブロック）の中身を `prompt` とする。
  - フェンスが見つからない場合は frontmatter 直後〜次の `## ` 見出しまでの本文を `prompt` とする。
  - `name` が無い、または frontmatter 自体が無いファイルはスキップ。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml as _yaml  # type: ignore
except ImportError:  # pragma: no cover
    _yaml = None  # type: ignore[assignment]


_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
# 「## 4) Prompt 本文」見出しの直後にあるフェンスブロックを抽出
_PROMPT_SECTION_RE = re.compile(
    r"^##\s*4\)\s*Prompt\s*本文.*?\n+```[a-zA-Z0-9_-]*\n(.*?)\n```",
    re.DOTALL | re.MULTILINE,
)


def _parse_frontmatter(fm_text: str) -> Dict[str, Any]:
    """frontmatter テキストを dict に変換する。

    PyYAML が利用可能ならそれを使う。利用不可の場合は最低限のキーのみ抽出する。
    """
    if _yaml is not None:
        try:
            data = _yaml.safe_load(fm_text)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    # PyYAML 不在時の最小フォールバック（name/description のみ）
    result: Dict[str, Any] = {}
    for line in fm_text.splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+?)\s*$", line)
        if m:
            key = m.group(1)
            val = m.group(2).strip().strip("'\"")
            result[key] = val
    return result


def _extract_prompt_body(body_after_frontmatter: str) -> str:
    """`## 4) Prompt 本文` のフェンスブロック中身を返す。見つからなければ空文字。"""
    m = _PROMPT_SECTION_RE.search(body_after_frontmatter)
    if m:
        return m.group(1).strip()
    return ""


def parse_agent_file(path: Path) -> Optional[Dict[str, Any]]:
    """1 つの `.agent.md` ファイルをパースし、SDK Custom Agent dict を返す。

    無効（frontmatter 無し、name 無し）の場合は None。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    fm_match = _FRONTMATTER_RE.match(text)
    if not fm_match:
        return None

    fm_text = fm_match.group(1)
    body = fm_match.group(2)

    fm = _parse_frontmatter(fm_text)
    name = fm.get("name")
    if not isinstance(name, str) or not name.strip():
        return None

    description = fm.get("description", "")
    if not isinstance(description, str):
        description = str(description)

    tools = fm.get("tools")
    if isinstance(tools, str):
        tools_list: List[str] = [t.strip() for t in tools.split(",") if t.strip()]
    elif isinstance(tools, list):
        tools_list = [str(t).strip() for t in tools if str(t).strip()]
    else:
        tools_list = ["*"]

    prompt = _extract_prompt_body(body)
    if not prompt:
        # フェンスが無い場合は frontmatter 以降の全文を prompt として扱う（互換）。
        prompt = body.strip()

    return {
        "name": name.strip(),
        "display_name": name.strip(),
        "description": description.strip(),
        "tools": tools_list,
        "prompt": prompt,
    }


def load_agent_definitions(agents_dir: Path) -> List[Dict[str, Any]]:
    """`agents_dir` 配下の `*.agent.md` を全件パースして SDK 定義リストを返す。

    - ディレクトリが存在しない場合は空リスト。
    - パースできないファイルは黙ってスキップ（呼び出し側で警告は出さない；
      validate-agents.py が別途 lint を行う前提）。
    - 同名 (name) が複数ある場合は先勝ち（ファイル名昇順）。
    """
    if not agents_dir.is_dir():
        return []

    seen: set[str] = set()
    result: List[Dict[str, Any]] = []
    for p in sorted(agents_dir.glob("*.agent.md")):
        agent = parse_agent_file(p)
        if agent is None:
            continue
        if agent["name"] in seen:
            continue
        seen.add(agent["name"])
        result.append(agent)
    return result


def merge_with_explicit(
    explicit: List[Dict[str, Any]],
    file_based: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """明示設定 (`SDKConfig.custom_agents_config`) とファイルベースの定義をマージする。

    明示設定が優先され、ファイルベース側で同名定義があれば破棄する。
    """
    explicit_names = {
        a.get("name") for a in explicit if isinstance(a, dict) and a.get("name")
    }
    merged: List[Dict[str, Any]] = list(explicit)
    for agent in file_based:
        if agent.get("name") in explicit_names:
            continue
        merged.append(agent)
    return merged
