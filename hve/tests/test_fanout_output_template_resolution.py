"""test_fanout_output_template_resolution.py — output_paths_template の多重プレースホルダ解決

FR-FANOUT-OUT-01 (TBD-11 / TBD-12 解消):
``output_paths_template`` は io-contract 側の意味的プレースホルダ表記
（``{screenId}`` / ``{serviceId}`` / ``{screenNameSlug}`` 等）をそのまま宣言できる。

解決規則:
  1. fan-out キーの別名プレースホルダ（``{key}`` および parser 別 ID 別名）を
     fan-out キーへ置換する。
  2. キー別名を 1 つも含まないエントリは per-key 成果物ではないため、
     fan-out 子の ``output_paths`` へは載せない（契約宣言としてのみ残す）。
  3. 置換後もプレースホルダ（``{...}`` / ``<...>``）が残るエントリは載せない。
  4. glob（``*`` / ``?``）を含む、またはディレクトリ参照（末尾 ``/``）の
     エントリは確定ファイルパスではないため載せない。

いずれも「実生成されないパスを宣言して runner の output_paths ゲートを
誤 fail させない」ための fail-closed 規則。
"""

from pathlib import Path

import pytest

from hve import workflow_registry as wr
from hve.fanout_expander import expand_workflow_fanout, expand_single_step_fanout


def _wf(step: wr.StepDef, wf_id: str = "t") -> wr.WorkflowDef:
    return wr.WorkflowDef(
        id=wf_id,
        name="t",
        label_prefix="t",
        state_labels=wr._make_state_labels("t"),
        params=[],
        steps=[step],
    )


def _child(expanded, step_id: str):
    return next(s for s in expanded.steps if s.id == step_id)


def _screen_catalog(tmp_path: Path) -> None:
    catalog = tmp_path / "docs" / "catalog" / "screen-catalog-APP-009.md"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text(
        "| 画面ID | 画面名 |\n|---|---|\n| S001 | ログイン |\n",
        encoding="utf-8",
    )


def _service_catalog(tmp_path: Path) -> None:
    catalog = tmp_path / "docs" / "catalog" / "service-catalog.md"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text(
        "| サービスID | 名称 |\n|---|---|\n| SVC-01 | 会員 |\n",
        encoding="utf-8",
    )


class TestKeyAliasPlaceholder:
    """規則 1: parser 別の ID 別名プレースホルダが fan-out キーへ解決される。"""

    def test_screen_id_alias_resolves_to_fanout_key(self, tmp_path: Path):
        _screen_catalog(tmp_path)
        step = wr.StepDef(
            id="A", title="t", custom_agent=None, consumed_artifacts=[],
            fanout_parser="screen_catalog",
            output_paths_template=["docs/test-specs/{screenId}-test-spec.md"],
        )
        expanded = expand_workflow_fanout(_wf(step), tmp_path)
        child = _child(expanded, "A/APP-009-S001")
        assert child.output_paths == ["docs/test-specs/APP-009-S001-test-spec.md"]

    def test_service_id_alias_resolves_to_fanout_key(self, tmp_path: Path):
        _service_catalog(tmp_path)
        step = wr.StepDef(
            id="A", title="t", custom_agent=None, consumed_artifacts=[],
            fanout_parser="service_catalog",
            output_paths_template=["docs/test-specs/{serviceId}-test-spec.md"],
        )
        expanded = expand_workflow_fanout(_wf(step), tmp_path)
        child = _child(expanded, "A/SVC-01")
        assert child.output_paths == ["docs/test-specs/SVC-01-test-spec.md"]

    def test_key_and_alias_resolve_to_same_path_are_deduplicated(self, tmp_path: Path):
        _service_catalog(tmp_path)
        step = wr.StepDef(
            id="A", title="t", custom_agent=None, consumed_artifacts=[],
            fanout_parser="service_catalog",
            output_paths_template=[
                "docs/test-specs/{key}-test-spec.md",
                "docs/test-specs/{serviceId}-test-spec.md",
            ],
        )
        expanded = expand_workflow_fanout(_wf(step), tmp_path)
        child = _child(expanded, "A/SVC-01")
        assert child.output_paths == ["docs/test-specs/SVC-01-test-spec.md"]

    def test_alias_of_other_parser_is_not_resolved(self, tmp_path: Path):
        """service_catalog の step で {screenId} は解決しない（誤置換防止）。"""
        _service_catalog(tmp_path)
        step = wr.StepDef(
            id="A", title="t", custom_agent=None, consumed_artifacts=[],
            fanout_parser="service_catalog",
            output_paths_template=["docs/screen/{screenId}-description.md"],
        )
        expanded = expand_workflow_fanout(_wf(step), tmp_path)
        assert _child(expanded, "A/SVC-01").output_paths == []

    def test_static_keys_resolve_only_key_placeholder(self, tmp_path: Path):
        step = wr.StepDef(
            id="A", title="t", custom_agent=None, consumed_artifacts=[],
            fanout_static_keys=["D01"],
            output_paths_template=[
                "knowledge/{key}-summary.md",
                "knowledge/{screenId}-summary.md",
            ],
        )
        expanded = expand_workflow_fanout(_wf(step), tmp_path)
        assert _child(expanded, "A/D01").output_paths == ["knowledge/D01-summary.md"]


class TestFailClosedDrop:
    """規則 2〜4: 確定ファイルパスへ解決できないエントリを子へ載せない。"""

    @pytest.mark.parametrize(
        "template_path",
        [
            # 規則 2: キー別名を含まない（全子で同一 path になる）
            "knowledge/business-requirement-document-status.md",
            "src/app/main.js",
            # 規則 3: 置換後もプレースホルダが残る
            "docs/screen/{key}-{screenNameSlug}-description.md",
            "src/infra/azure/create/services/<service>.sh",
            # 規則 4: glob / ディレクトリ参照
            "knowledge/{key}-*.md",
            "src/test/agent/{key}.Tests/",
        ],
    )
    def test_unresolvable_entry_is_not_declared(self, tmp_path: Path, template_path: str):
        step = wr.StepDef(
            id="A", title="t", custom_agent=None, consumed_artifacts=[],
            fanout_static_keys=["D01"],
            output_paths_template=[template_path],
        )
        expanded = expand_workflow_fanout(_wf(step), tmp_path)
        assert _child(expanded, "A/D01").output_paths == []

    def test_resolvable_and_unresolvable_entries_are_partitioned(self, tmp_path: Path):
        step = wr.StepDef(
            id="A", title="t", custom_agent=None, consumed_artifacts=[],
            fanout_static_keys=["D01"],
            output_paths_template=[
                "knowledge/status.md",
                "knowledge/{key}-*.md",
                "knowledge/{key}-detail.md",
            ],
        )
        expanded = expand_workflow_fanout(_wf(step), tmp_path)
        assert _child(expanded, "A/D01").output_paths == ["knowledge/D01-detail.md"]

    def test_expand_single_step_applies_same_rules(self, tmp_path: Path):
        step = wr.StepDef(
            id="A", title="t", custom_agent=None, consumed_artifacts=[],
            fanout_static_keys=["D01"],
            output_paths_template=[
                "knowledge/{key}-detail.md",
                "knowledge/{key}-*.md",
            ],
        )
        children = expand_single_step_fanout(step, tmp_path)
        assert children is not None
        assert children[0].output_paths == ["knowledge/D01-detail.md"]


class TestDirectoryArtifactCoversDescendants:
    """規則 5: 同一 template 内のディレクトリ成果物配下のファイルは個別に載せない。

    ディレクトリを成果物として宣言している Step では、その配下のファイル構成は
    Agent の裁量（言語・フレームワーク依存）に委ねられる。個別ファイルまで
    output_paths ゲートの対象にすると、契約上は同じ成果物なのに構成差で誤 fail する。
    """

    def test_descendant_of_declared_directory_is_not_declared(self, tmp_path: Path):
        step = wr.StepDef(
            id="A", title="t", custom_agent=None, consumed_artifacts=[],
            fanout_static_keys=["D01"],
            output_paths_template=[
                "src/agent/{key}/",
                "src/agent/{key}/README.md",
            ],
        )
        expanded = expand_workflow_fanout(_wf(step), tmp_path)
        assert _child(expanded, "A/D01").output_paths == []

    def test_placeholderless_directory_also_covers_descendants(self, tmp_path: Path):
        step = wr.StepDef(
            id="A", title="t", custom_agent=None, consumed_artifacts=[],
            fanout_static_keys=["D01"],
            output_paths_template=[
                ".github/workflows/",
                ".github/workflows/deploy-{key}.yml",
            ],
        )
        expanded = expand_workflow_fanout(_wf(step), tmp_path)
        assert _child(expanded, "A/D01").output_paths == []

    def test_sibling_directory_does_not_cover_unrelated_entry(self, tmp_path: Path):
        step = wr.StepDef(
            id="A", title="t", custom_agent=None, consumed_artifacts=[],
            fanout_static_keys=["D01"],
            output_paths_template=[
                "src/agent/{key}/",
                "docs/test-specs/{key}-test-spec.md",
            ],
        )
        expanded = expand_workflow_fanout(_wf(step), tmp_path)
        assert _child(expanded, "A/D01").output_paths == [
            "docs/test-specs/D01-test-spec.md"
        ]

    def test_similar_prefix_without_separator_is_not_covered(self, tmp_path: Path):
        """`src/agent/` は `src/agentx/...` を覆わない（境界の誤判定防止）。"""
        step = wr.StepDef(
            id="A", title="t", custom_agent=None, consumed_artifacts=[],
            fanout_static_keys=["D01"],
            output_paths_template=[
                "src/agent/",
                "src/agentx/{key}.md",
            ],
        )
        expanded = expand_workflow_fanout(_wf(step), tmp_path)
        assert _child(expanded, "A/D01").output_paths == ["src/agentx/D01.md"]


class TestBackwardCompatibility:
    """既存挙動（{key} 単独置換 / template 未指定時の output_paths 継承）を壊さない。"""

    def test_key_placeholder_behaviour_unchanged(self, tmp_path: Path):
        step = wr.StepDef(
            id="Y", title="t", custom_agent=None, consumed_artifacts=[],
            fanout_static_keys=["D01", "D02"],
            output_paths_template=["docs/foo/{key}-detail.md", "docs/bar/{key}.md"],
        )
        expanded = expand_workflow_fanout(_wf(step), tmp_path)
        assert _child(expanded, "Y/D01").output_paths == [
            "docs/foo/D01-detail.md",
            "docs/bar/D01.md",
        ]

    def test_output_paths_inherited_when_template_absent(self, tmp_path: Path):
        step = wr.StepDef(
            id="Z", title="t", custom_agent=None, consumed_artifacts=[],
            fanout_static_keys=["D01"],
            output_paths=["docs/parent-output.md"],
        )
        expanded = expand_workflow_fanout(_wf(step), tmp_path)
        assert _child(expanded, "Z/D01").output_paths == ["docs/parent-output.md"]

    def test_required_input_paths_still_use_key_only_substitution(self, tmp_path: Path):
        """入力側の置換規則は本変更の対象外（{key} 置換のみ）。"""
        step = wr.StepDef(
            id="Z", title="t", custom_agent=None, consumed_artifacts=[],
            fanout_static_keys=["D01"],
            required_input_paths=[
                "docs/agent/agent-detail-{key}.md",
                "docs/screen/{screenId}-{screenNameSlug}-description.md",
            ],
        )
        expanded = expand_workflow_fanout(_wf(step), tmp_path)
        assert _child(expanded, "Z/D01").required_input_paths == [
            "docs/agent/agent-detail-D01.md",
            "docs/screen/{screenId}-{screenNameSlug}-description.md",
        ]


class TestRegistryContractsAreSafe:
    """レジストリ実データ: 展開後 output_paths にプレースホルダ/glob/ディレクトリが残らない。"""

    @pytest.mark.parametrize("wf_id", [w.id for w in wr.list_workflows()])
    def test_no_unresolved_output_paths_in_registry(self, wf_id: str):
        wf = wr.get_workflow(wf_id)
        assert wf is not None
        expanded = expand_workflow_fanout(wf, Path("."))
        for step in expanded.steps:
            for path in getattr(step, "output_paths", None) or []:
                assert "{" not in path and "}" not in path, f"{wf_id}/{step.id}: {path}"
                assert "<" not in path and ">" not in path, f"{wf_id}/{step.id}: {path}"
                assert "*" not in path, f"{wf_id}/{step.id}: {path}"
