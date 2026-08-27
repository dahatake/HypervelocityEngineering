"""test_adi_downstream_contract.py — ADI ルーティング表の下流接続契約。

FR-WF-ADI-12: AKM は `docs/catalog/design-doc-routing.md` が存在する場合それを優先し、
存在しない場合は従来どおり `docs-original/` を走査する（後方互換）。ADI の
質問票 fan-out は後段 Step 4 の routing 表ではなく Step 1 の正規化済み出力を読む。

Prompt 側の契約テストであり、実行時挙動ではなく指示文の存在を固定する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROUTING_PATH = "docs/catalog/design-doc-routing.md"

_FANOUT_COMMONS = {
    "akm": _REPO_ROOT / ".github" / "prompts" / "fanout" / "akm" / "_common.prompt.md",
}


@pytest.mark.parametrize("workflow_id", sorted(_FANOUT_COMMONS))
def test_fanout_common_references_routing_table(workflow_id: str) -> None:
    text = _FANOUT_COMMONS[workflow_id].read_text(encoding="utf-8")
    assert _ROUTING_PATH in text, (
        f"{workflow_id} の fan-out 共通指示が ADI ルーティング表を参照していません"
    )


@pytest.mark.parametrize("workflow_id", sorted(_FANOUT_COMMONS))
def test_fanout_common_declares_backward_compatible_fallback(workflow_id: str) -> None:
    """ルーティング表が無い場合に従来経路へフォールバックすることを明示している。"""
    text = _FANOUT_COMMONS[workflow_id].read_text(encoding="utf-8")
    assert "存在しない場合は従来どおり" in text, (
        f"{workflow_id} の fan-out 共通指示に後方互換フォールバックの記述がありません"
    )
    assert "docs-original/" in text


@pytest.mark.parametrize("workflow_id", sorted(_FANOUT_COMMONS))
def test_fanout_common_keeps_readonly_rule(workflow_id: str) -> None:
    """ADI 接続を足しても docs-original/ の読み取り専用規定が残っていること。"""
    text = _FANOUT_COMMONS[workflow_id].read_text(encoding="utf-8")
    assert "読み取り専用" in text or "書き込みは禁止" in text


def test_adi_fanout_common_exists_and_forbids_cross_document_writes() -> None:
    common = _REPO_ROOT / ".github" / "prompts" / "fanout" / "adi" / "_common.prompt.md"
    text = common.read_text(encoding="utf-8")
    assert "{{key}}" in text
    assert "並列実行ルール" in text
    assert "docs/catalog/" in text


def test_adi_questionnaire_fanout_reads_normalized_content_without_routing() -> None:
    common = _REPO_ROOT / ".github" / "prompts" / "fanout" / "adi" / "_questionnaire.prompt.md"
    text = common.read_text(encoding="utf-8")
    assert "{{key}}" in text
    assert "docs/original-design-doc-ingest/index.json" in text
    assert "docs/original-design-doc-ingest/<slug>/content.md" in text
    assert _ROUTING_PATH not in text


def test_adi_questionnaire_prompt_matches_scope_and_validator_contract() -> None:
    prompt = (
        _REPO_ROOT / ".github" / "prompts" / "QA-DocConsistency.prompt.md"
    ).read_text(encoding="utf-8")
    assert "# Original ドキュメント質問票" in prompt
    assert "末尾 `/` 付き" in prompt
    assert "前方一致" in prompt
    assert "`docs-original/` 外" in prompt
