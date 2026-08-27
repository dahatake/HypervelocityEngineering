"""FR-WF-ARD-02: ARD のユーザー提供資料を一次情報として最優先参照させる契約。

ユーザー提供資料（`attached_docs` / パス指定の `target_business`）は ARD の
どの Step の `required_input_paths` にも宣言されず、テンプレートへのパラメータ
注入だけが到達経路である。そのため優先度の明示が失われると、Agent は固定パスの
既定入力だけを読み、ユーザーが指定したファイルを参照しないまま完了しうる。
"""
from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_UNTARGETED_PROMPT = _REPO_ROOT / ".github" / "prompts" / "Arch-ARD-BusinessAnalysis-Untargeted.prompt.md"
_TARGETED_PROMPT = _REPO_ROOT / ".github" / "prompts" / "Arch-ARD-BusinessAnalysis-Targeted.prompt.md"
_STEP1_TEMPLATE = _REPO_ROOT / ".github" / "prompts" / "steps" / "ard" / "step-1.prompt.md"
_STEP2_TEMPLATE = _REPO_ROOT / ".github" / "prompts" / "steps" / "ard" / "step-2.prompt.md"

# Targeted 側で既に使われている規範表現。Untargeted / テンプレートでも同一表現に揃える。
_PRIORITY_PHRASE = "一次情報として最優先"


def _section(path: Path, heading: str) -> str:
    """指定見出しの本文（次の同レベル以上の見出しまで）を返す。"""
    text = path.read_text(encoding="utf-8")
    level = len(heading) - len(heading.lstrip("#"))
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:  # pragma: no cover - 見出し変更時の診断用
        raise AssertionError(f"見出しが見つかりません: {heading} ({path})")
    body: list[str] = []
    for line in lines[start + 1:]:
        m = re.match(r"^(#+)\s", line)
        if m and len(m.group(1)) <= level:
            break
        body.append(line)
    return "\n".join(body)


class TestArdAttachedDocsPriority:
    """FR-WF-ARD-02: Prompt / Body テンプレートへの最優先参照規定。"""

    def test_untargeted_prompt_input_section_declares_priority(self) -> None:
        section = _section(_UNTARGETED_PROMPT, "## 2) 入力（必ず参照）")
        assert _PRIORITY_PHRASE in section, (
            "Untargeted Prompt の入力節にユーザー提供資料の最優先参照規定がありません"
        )

    def test_untargeted_prompt_body_references_attached_docs(self) -> None:
        text = _UNTARGETED_PROMPT.read_text(encoding="utf-8")
        assert "{添付資料}" in text, "Untargeted Prompt 本文の添付資料プレースホルダが失われています"

    def test_step1_template_input_section_declares_priority(self) -> None:
        section = _section(_STEP1_TEMPLATE, "## 入力")
        assert "{attached_docs}" in section, "step-1.md の入力節に {attached_docs} がありません"
        assert _PRIORITY_PHRASE in section, (
            "step-1.md の入力節にユーザー提供資料の最優先参照規定がありません"
        )

    def test_targeted_prompt_keeps_priority(self) -> None:
        text = _TARGETED_PROMPT.read_text(encoding="utf-8")
        assert _PRIORITY_PHRASE in text, "Targeted Prompt の最優先参照規定が失われています"

    def test_step2_template_keeps_attached_docs(self) -> None:
        section = _section(_STEP2_TEMPLATE, "## 入力")
        assert "{attached_docs}" in section, "step-2.md の入力節に {attached_docs} がありません"
        assert "{target_business}" in section, "step-2.md の入力節に {target_business} がありません"
        assert _PRIORITY_PHRASE in section, (
            "step-2.md の入力節にユーザー提供資料の最優先参照規定がありません"
        )

    def test_step2_template_completion_declares_priority(self) -> None:
        section = _section(_STEP2_TEMPLATE, "## 完了条件")
        assert "添付資料・指定資料" in section, (
            "step-2.md の完了条件が attached_docs とパス指定 target_business の両方を扱っていません"
        )
        assert _PRIORITY_PHRASE in section, (
            "step-2.md の完了条件にユーザー提供資料の最優先参照規定がありません"
        )

    def test_step2_template_expands_target_business_once(self) -> None:
        """FR-WF-ARD-02 (v2.57): `{target_business}` は 1 箇所だけ展開する。

        パス指定時の展開結果を 2 箇所へ埋め込むと、リクエストサイズが二重に増える。
        """
        text = _STEP2_TEMPLATE.read_text(encoding="utf-8")
        assert text.count("{target_business}") == 1, (
            "step-2.md は {target_business} を 1 箇所だけ展開しなければなりません "
            f"(実際: {text.count('{target_business}')} 箇所)"
        )
