"""test_workflow_categories.py — ワークフロー一覧のカテゴリー表の契約（FR-GUI-21）。

GUI Step 1 左ペインと CLI 対話ウィザードが共有するカテゴリー表
`hve.workflow_registry.WORKFLOW_CATEGORIES` を検証する。
"""

from __future__ import annotations

from hve.workflow_registry import WORKFLOW_CATEGORIES, list_workflows


# FR-GUI-21 が定める順序付きカテゴリー定義。
EXPECTED_CATEGORIES = (
    ("Business Engineering (要求定義)", ("ard",)),
    ("Architecture Design", ("aas",)),
    ("Software Engineering", ("aad-web", "asdw-web", "adfd", "adfdv")),
    ("既存ドキュメントのインポート", ("adi",)),
    ("Knowledge Management", ("akm", "adoc")),
    ("AI Agent", ("ada", "aag", "aagd", "aar")),
)


class TestWorkflowCategories:
    """`WORKFLOW_CATEGORIES` の網羅性・重複禁止・順序。"""

    def test_definition_matches_contract(self) -> None:
        actual = tuple((name, tuple(ids)) for name, ids in WORKFLOW_CATEGORIES)
        assert actual == EXPECTED_CATEGORIES

    def test_ai_agent_category_is_last(self) -> None:
        names = [name for name, _ids in WORKFLOW_CATEGORIES]
        assert names[-1] == "AI Agent"

    def test_ai_agent_category_contains_ada(self) -> None:
        members = dict((name, tuple(ids)) for name, ids in WORKFLOW_CATEGORIES)
        assert members["AI Agent"] == ("ada", "aag", "aagd", "aar")

    def test_every_registered_workflow_is_categorized(self) -> None:
        categorized = {wf_id for _name, ids in WORKFLOW_CATEGORIES for wf_id in ids}
        registered = {wf.id for wf in list_workflows()}
        assert registered - categorized == set()

    def test_no_unknown_workflow_id(self) -> None:
        categorized = [wf_id for _name, ids in WORKFLOW_CATEGORIES for wf_id in ids]
        registered = {wf.id for wf in list_workflows()}
        assert [wf_id for wf_id in categorized if wf_id not in registered] == []

    def test_no_workflow_appears_in_two_categories(self) -> None:
        categorized = [wf_id for _name, ids in WORKFLOW_CATEGORIES for wf_id in ids]
        assert len(categorized) == len(set(categorized))

    def test_category_names_are_unique(self) -> None:
        names = [name for name, _ids in WORKFLOW_CATEGORIES]
        assert len(names) == len(set(names))


class TestWorkflowEnumerationTables:
    """\u8868\u793a\u9806\u30fb\u8868\u793a\u540d\u306e\u5217\u6319\u8868\u304c\u767b\u9332\u6e08\u307f\u5168\u30ef\u30fc\u30af\u30d5\u30ed\u30fc\u3092\u542b\u3080\u3053\u3068\uff08FR-GUI-21\uff09\u3002"""

    def _registered(self) -> set:
        return {wf.id for wf in list_workflows()}

    def test_page_options_canonical_order_covers_all(self) -> None:
        from hve.gui.page_options import _WORKFLOW_CANONICAL_ORDER

        assert self._registered() - set(_WORKFLOW_CANONICAL_ORDER) == set()

    def test_plan_review_gap_canonical_order_covers_all(self) -> None:
        from hve.autopilot.plan_review_gap import _WORKFLOW_CANONICAL_ORDER

        assert self._registered() - set(_WORKFLOW_CANONICAL_ORDER) == set()

    def test_workflow_priority_covers_all(self) -> None:
        from hve.gui.workflow_step_requirements import WORKFLOW_PRIORITY

        assert self._registered() - set(WORKFLOW_PRIORITY) == set()

    def test_display_names_cover_all(self) -> None:
        from hve.template_engine import _WORKFLOW_DISPLAY_NAMES

        assert self._registered() - set(_WORKFLOW_DISPLAY_NAMES) == set()
