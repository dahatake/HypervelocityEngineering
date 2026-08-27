"""FR-PROMPT-09 — 入力別名を単一解決器で全判定へ適用する契約の RED テスト。

`run_workflow` は実 Copilot セッションを起動するため呼ばない。統合点は
純粋関数（成果物検出 / meta 依存判定 / Step Prompt / Fleet task）で検証する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hve import orchestrator
from hve.input_aliases import AliasResolver, ResolvedAlias, resolver_from_params
from hve.workflow_registry import StepDef, get_step

_APP_CATALOG = "docs/catalog/app-catalog.md"


@pytest.fixture()
def alias_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "my-catalog.md").write_text("# catalog", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestResolverFromParams:
    def test_builds_resolver_from_params_pairs(self):
        r = resolver_from_params({"input_aliases": [(_APP_CATALOG, "inputs/my-catalog.md")]})
        assert r.actual_for(_APP_CATALOG) == "inputs/my-catalog.md"

    def test_absent_key_yields_empty_resolver(self):
        assert not resolver_from_params({})

    def test_accepts_resolved_alias_objects(self):
        r = resolver_from_params(
            {"input_aliases": [ResolvedAlias(canonical="a.md", actual="b.md")]}
        )
        assert r.actual_for("a.md") == "b.md"


class TestArtifactDetectionUsesAliases:
    def test_alias_satisfies_missing_canonical_artifact(self, alias_repo: Path):
        existing = orchestrator._detect_existing_artifacts(
            "aas", {"input_aliases": [(_APP_CATALOG, "inputs/my-catalog.md")]}
        )
        assert existing.get("app_catalog") == "inputs/my-catalog.md"

    def test_without_alias_the_canonical_is_still_missing(self, alias_repo: Path):
        existing = orchestrator._detect_existing_artifacts("aas", {})
        assert "app_catalog" not in existing

    def test_unknown_alias_does_not_invent_artifacts(self, alias_repo: Path):
        existing = orchestrator._detect_existing_artifacts(
            "aas", {"input_aliases": [("docs/catalog/no-such.md", "inputs/my-catalog.md")]}
        )
        assert "app_catalog" not in existing


class TestMetaDependencyUsesAliases:
    def test_alias_satisfies_meta_dependency_pattern(self, alias_repo: Path):
        resolver = AliasResolver([ResolvedAlias(canonical=_APP_CATALOG, actual="inputs/my-catalog.md")])
        assert orchestrator._artifact_pattern_exists(_APP_CATALOG, resolver) is True

    def test_missing_pattern_without_alias_is_false(self, alias_repo: Path):
        assert orchestrator._artifact_pattern_exists(_APP_CATALOG, AliasResolver([])) is False

    def test_alias_target_must_exist_on_disk(self, alias_repo: Path):
        resolver = AliasResolver([ResolvedAlias(canonical=_APP_CATALOG, actual="inputs/absent.md")])
        assert orchestrator._artifact_pattern_exists(_APP_CATALOG, resolver) is False


class TestStepPromptAddendum:
    def _step(self) -> StepDef:
        step = get_step("aas", "1")
        assert step is not None
        return step

    def test_adds_addendum_for_related_step(self):
        prompt = orchestrator._build_step_prompt(
            self._step(),
            {"branch": "main", "input_aliases": [(_APP_CATALOG, "inputs/my-catalog.md")]},
            None,
            lambda **_kwargs: "BODY",
            None,
        )
        assert "inputs/my-catalog.md" in prompt
        assert _APP_CATALOG in prompt

    def test_does_not_embed_file_contents(self, alias_repo: Path):
        prompt = orchestrator._build_step_prompt(
            self._step(),
            {"branch": "main", "input_aliases": [(_APP_CATALOG, "inputs/my-catalog.md")]},
            None,
            lambda **_kwargs: "BODY",
            None,
        )
        assert "# catalog" not in prompt

    def test_unrelated_step_prompt_is_unchanged(self):
        step = self._step()
        base = orchestrator._build_step_prompt(
            step, {"branch": "main"}, None, lambda **_kwargs: "BODY", None
        )
        with_alias = orchestrator._build_step_prompt(
            step,
            {
                "branch": "main",
                # `aas` Step 1 が要求しない入力の別名は当該 Step の Prompt を変えない
                "input_aliases": [("docs/catalog/use-case-catalog.md", "inputs/my-catalog.md")],
            },
            None,
            lambda **_kwargs: "BODY",
            None,
        )
        assert with_alias == base

    def test_no_aliases_leaves_prompt_unchanged(self):
        base = orchestrator._build_step_prompt(
            self._step(), {"branch": "main"}, None, lambda **_kwargs: "BODY", None
        )
        assert "別名" not in base


class TestFleetRequiredInputsUseAliases:
    def test_fleet_task_required_inputs_are_resolved(self):
        step = get_step("aas", "1")
        assert step is not None
        resolver = AliasResolver(
            [ResolvedAlias(canonical=_APP_CATALOG, actual="inputs/my-catalog.md")]
        )
        resolved = resolver.resolve_paths(list(step.required_input_paths))
        assert "inputs/my-catalog.md" in resolved
        assert _APP_CATALOG not in resolved

    def test_orchestrator_exposes_single_resolver_helper(self):
        """統合点は同じ解決器を通す（実装の重複を禁止する）。"""
        assert callable(getattr(orchestrator, "_alias_resolver_for_params", None))


class TestOutputContractsAreUnchanged:
    def test_output_paths_are_never_aliased(self):
        step = get_step("aas", "1")
        assert step is not None
        resolver = AliasResolver(
            [ResolvedAlias(canonical="docs/catalog/app-arch-catalog.md", actual="inputs/my-catalog.md")]
        )
        # 出力側へは解決器を適用しない（呼ばれないことを契約として明記する）。
        assert list(step.output_paths) == ["docs/catalog/app-arch-catalog.md"]
        assert resolver.actual_for("docs/catalog/app-arch-catalog.md") == "inputs/my-catalog.md"


class TestRequirementIsDeclared:
    def test_fr_prompt_09_is_declared(self):
        text = Path("hve-dev/requirement-definition.md").read_text(encoding="utf-8")
        assert "**FR-PROMPT-09**" in text
