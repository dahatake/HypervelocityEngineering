"""`users-guide/tool-search-guide.md` が実装と食い違わないことを固定する。

利用者ガイドは実装から離れやすい。特に閾値・パス・Step 採番は、
ずれると利用者が誤った前提で設計を書いてしまう。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hve.workflow_registry import get_workflow

_REPO = Path(__file__).resolve().parents[2]
_GUIDE = _REPO / "users-guide" / "tool-search-guide.md"


@pytest.fixture(scope="module")
def guide() -> str:
    assert _GUIDE.exists(), "tool-search-guide.md が存在しない"
    return _GUIDE.read_text(encoding="utf-8")


class TestFactsMatchImplementation:
    def test_threshold_matches_validator(self, guide):
        from hve.artifact_validation import _TOOLBOX_TOOL_COUNT_THRESHOLD

        assert str(_TOOLBOX_TOOL_COUNT_THRESHOLD) in guide
        assert f"{_TOOLBOX_TOOL_COUNT_THRESHOLD + 1} 個以上" in guide

    def test_search_limit_range_matches_validator(self, guide):
        from hve.artifact_validation import _TOOLBOX_MAX_SEARCH_LIMIT

        assert f"1〜{_TOOLBOX_MAX_SEARCH_LIMIT}" in guide

    def test_cli_flag_matches(self, guide):
        from hve.__main__ import _build_parser

        sub = next(
            a for a in _build_parser()._actions
            if hasattr(a, "choices") and isinstance(a.choices, dict)
        )
        assert "--enable-tool-search" in sub.choices["orchestrate"].format_help()
        assert "--enable-tool-search" in guide

    def test_eval_output_path_matches_registry(self, guide):
        step = next(s for s in get_workflow("aagd").steps if s.id == "4")
        for path in step.output_paths_template:
            assert path in guide, f"{path} がガイドに無い"

    def test_topologies_match_skill(self, guide):
        from hve.artifact_validation import _TOOLBOX_TOPOLOGIES

        for topology in _TOOLBOX_TOPOLOGIES:
            assert topology in guide


class TestWarnsAboutKnownTraps:
    """実際に踏んだ欠陥を利用者へ引き継ぐ。"""

    def test_warns_about_heading_level(self, guide):
        assert "同じレベル" in guide

    def test_warns_about_meta_dependency_glob(self, guide):
        assert "docs/agent/*.md" in guide
        assert "直下" in guide

    def test_warns_about_toolbox_ordering_at_deploy(self, guide):
        assert "Agent 登録より前" in guide

    def test_explains_deferred_is_allowed(self, guide):
        assert "deferred" in guide
        assert "省略すると FAIL" in guide


class TestEvidenceHandling:
    def test_labels_benchmark_numbers_as_benchmark(self, guide):
        """公開数値を自社実績のように読ませない。"""
        assert "ToolRet" in guide
        assert "確定値ではない" in guide

    def test_records_the_cloud_gap(self, guide):
        assert "設問は無い" in guide

    def test_no_percent_sign_confusion_with_cloud_body(self, guide):
        """Cloud Issue 本文は printf 制約でパーセント記号を避けている。

        ガイド側の表記も揃え、両者を読み比べたときに別の数値に見えないようにする。
        """
        assert "パーセント" in guide


class TestCrossReferenceWithAgenticRetrievalGuide:
    """接続トポロジは AR-CAP / TB-CAP の両方に現れる。片側だけ書くと迷子になる。"""

    def _ar_guide(self) -> str:
        path = _REPO / "users-guide" / "agentic-retrieval-guide.md"
        assert path.exists(), "agentic-retrieval-guide.md が存在しない"
        return path.read_text(encoding="utf-8")

    def test_guides_link_to_each_other(self, guide):
        assert "agentic-retrieval-guide.md" in guide
        assert "tool-search-guide.md" in self._ar_guide()

    def test_ar_guide_documents_both_topologies(self):
        from hve.artifact_validation import _TOOLBOX_TOPOLOGIES

        ar_guide = self._ar_guide()
        for topology in _TOOLBOX_TOPOLOGIES:
            assert topology in ar_guide

    def test_ar_guide_states_the_direct_kb_tool_restriction(self):
        """`direct-kb` だけの制約を `via-toolbox` にも適用する誤解を防ぐ。"""
        ar_guide = self._ar_guide()
        assert "knowledge_base_retrieve" in ar_guide
        assert "のみ" in ar_guide


class TestStepNumberingTable:
    """Cloud と registry の採番が一致していることを明示する。"""

    def test_states_the_unified_step_id(self, guide):
        assert "`1 / 2.1 / 2.2 / 2.3 / 3 / 4`" in guide
        assert "`Step.4`" in guide

    def test_explains_the_display_only_container(self, guide):
        """コンテナ `Step.2` は SSoT に無い。誤解を防ぐ。"""
        assert "表示上のもの" in guide

    def test_cloud_step_exists_as_documented(self, guide):
        workflow = (
            _REPO / ".github" / "workflows" / "auto-ai-agent-dev-reusable.yml"
        ).read_text(encoding="utf-8")
        assert "[AAGD] Step.4: tool search 実測評価" in workflow

    def test_registry_and_cloud_ssot_agree(self):
        from hve.dag_parity import extract_bash_workflow_steps

        bash = set(
            extract_bash_workflow_steps(
                _REPO / ".github" / "scripts" / "bash" / "lib" / "workflow-registry.sh",
                "aagd",
            )
        )
        hve = {s.id for s in get_workflow("aagd").steps if not s.is_container}
        assert bash == hve
