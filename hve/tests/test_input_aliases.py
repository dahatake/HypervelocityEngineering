"""FR-PROMPT-08 — 入力別名（canonical → actual）の安全契約の RED テスト。

前提となる `required_input_paths` / `output_paths` は registry の実測値を用いる。
- `aas` Step `1`   : IN `docs/catalog/app-catalog.md`, `docs/architectural-requirements-app-*.md` / OUT `docs/catalog/app-arch-catalog.md`
- `aas` Step `2.1` : IN `docs/catalog/app-arch-catalog.md`, `docs/catalog/app-catalog.md`, `docs/catalog/use-case-catalog.md`
- `aad-web` Step `2.1` : IN `docs/catalog/screen-catalog-{key}.md`
- `asdw-web` Step `3.2` : IN `src/test/api/`
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from hve.input_aliases import (
    AliasResolver,
    InputAliasError,
    ResolvedAlias,
    build_alias_addendum,
    normalize_alias_pairs,
    validate_aliases,
)
from hve.workflow_registry import get_step

_APP_CATALOG = "docs/catalog/app-catalog.md"
_USE_CASE_CATALOG = "docs/catalog/use-case-catalog.md"
_APP_ARCH_CATALOG = "docs/catalog/app-arch-catalog.md"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "my-catalog.md").write_text("# catalog", encoding="utf-8")
    (tmp_path / "inputs" / "my-use-cases.md").write_text("# uc", encoding="utf-8")
    return tmp_path


class TestNormalizeAliasPairs:
    def test_normalizes_windows_separators(self):
        aliases = normalize_alias_pairs([("docs\\catalog\\x.md", "inputs\\y.md")])
        assert aliases == (ResolvedAlias(canonical="docs/catalog/x.md", actual="inputs/y.md"),)

    def test_rejects_pair_of_wrong_arity(self):
        with pytest.raises(InputAliasError):
            normalize_alias_pairs([("only-one",)])

    def test_rejects_empty_component(self):
        with pytest.raises(InputAliasError):
            normalize_alias_pairs([("docs/a.md", "   ")])

    def test_rejects_non_string_component(self):
        with pytest.raises(InputAliasError):
            normalize_alias_pairs([("docs/a.md", 3)])

    def test_rejects_duplicate_canonical(self):
        with pytest.raises(InputAliasError):
            normalize_alias_pairs(
                [("docs/a.md", "inputs/x.md"), ("docs/a.md", "inputs/y.md")]
            )

    def test_preserves_declaration_order(self):
        aliases = normalize_alias_pairs(
            [("docs/b.md", "inputs/x.md"), ("docs/a.md", "inputs/y.md")]
        )
        assert [a.canonical for a in aliases] == ["docs/b.md", "docs/a.md"]


class TestCanonicalMustBeLiteralActiveInput:
    def test_accepts_literal_required_input_of_active_step(self, repo: Path):
        aliases = validate_aliases(
            normalize_alias_pairs([(_APP_CATALOG, "inputs/my-catalog.md")]),
            workflow_id="aas",
            step_ids=["1"],
            repo_root=repo,
        )
        assert aliases == (
            ResolvedAlias(canonical=_APP_CATALOG, actual="inputs/my-catalog.md"),
        )

    def test_rejects_canonical_not_required_by_any_active_step(self, repo: Path):
        with pytest.raises(InputAliasError) as exc:
            validate_aliases(
                normalize_alias_pairs(
                    [("docs/catalog/no-such-input.md", "inputs/my-catalog.md")]
                ),
                workflow_id="aas",
                step_ids=["1"],
                repo_root=repo,
            )
        assert "docs/catalog/no-such-input.md" in str(exc.value)

    def test_rejects_canonical_required_only_by_unselected_step(self, repo: Path):
        """`use-case-catalog` は Step 2.1 の入力。Step 1 だけを選んだときは拒否される。"""
        with pytest.raises(InputAliasError):
            validate_aliases(
                normalize_alias_pairs([(_USE_CASE_CATALOG, "inputs/my-use-cases.md")]),
                workflow_id="aas",
                step_ids=["1"],
                repo_root=repo,
            )

    def test_accepts_when_the_requiring_step_is_selected(self, repo: Path):
        aliases = validate_aliases(
            normalize_alias_pairs([(_USE_CASE_CATALOG, "inputs/my-use-cases.md")]),
            workflow_id="aas",
            step_ids=["2.1"],
            repo_root=repo,
        )
        assert aliases[0].canonical == _USE_CASE_CATALOG

    def test_empty_step_ids_means_all_steps(self, repo: Path):
        aliases = validate_aliases(
            normalize_alias_pairs([(_USE_CASE_CATALOG, "inputs/my-use-cases.md")]),
            workflow_id="aas",
            step_ids=[],
            repo_root=repo,
        )
        assert aliases[0].canonical == _USE_CASE_CATALOG

    def test_rejects_unknown_workflow(self, repo: Path):
        with pytest.raises(InputAliasError):
            validate_aliases(
                normalize_alias_pairs([(_APP_CATALOG, "inputs/my-catalog.md")]),
                workflow_id="no-such-workflow",
                step_ids=[],
                repo_root=repo,
            )


class TestV1UnsupportedShapes:
    def test_rejects_glob_canonical(self, repo: Path):
        with pytest.raises(InputAliasError) as exc:
            validate_aliases(
                normalize_alias_pairs(
                    [("docs/architectural-requirements-app-*.md", "inputs/my-catalog.md")]
                ),
                workflow_id="aas",
                step_ids=["1"],
                repo_root=repo,
            )
        assert "glob" in str(exc.value).lower()

    def test_rejects_placeholder_canonical(self, repo: Path):
        with pytest.raises(InputAliasError):
            validate_aliases(
                normalize_alias_pairs(
                    [("docs/catalog/screen-catalog-{key}.md", "inputs/my-catalog.md")]
                ),
                workflow_id="aad-web",
                step_ids=["2.1"],
                repo_root=repo,
            )

    def test_rejects_directory_canonical(self, repo: Path):
        with pytest.raises(InputAliasError):
            validate_aliases(
                normalize_alias_pairs([("src/test/api/", "inputs/my-catalog.md")]),
                workflow_id="asdw-web",
                step_ids=["3.2"],
                repo_root=repo,
            )


class TestActualPathPolicy:
    def test_rejects_absolute_actual(self, repo: Path):
        absolute = str((repo / "inputs" / "my-catalog.md").resolve())
        with pytest.raises(InputAliasError):
            validate_aliases(
                normalize_alias_pairs([(_APP_CATALOG, absolute)]),
                workflow_id="aas",
                step_ids=["1"],
                repo_root=repo,
            )

    def test_rejects_parent_escape(self, repo: Path):
        with pytest.raises(InputAliasError):
            validate_aliases(
                normalize_alias_pairs([(_APP_CATALOG, "../outside.md")]),
                workflow_id="aas",
                step_ids=["1"],
                repo_root=repo,
            )

    def test_rejects_missing_actual(self, repo: Path):
        with pytest.raises(InputAliasError):
            validate_aliases(
                normalize_alias_pairs([(_APP_CATALOG, "inputs/absent.md")]),
                workflow_id="aas",
                step_ids=["1"],
                repo_root=repo,
            )

    def test_rejects_directory_actual(self, repo: Path):
        with pytest.raises(InputAliasError):
            validate_aliases(
                normalize_alias_pairs([(_APP_CATALOG, "inputs")]),
                workflow_id="aas",
                step_ids=["1"],
                repo_root=repo,
            )

    @pytest.mark.skipif(
        sys.platform == "win32" and not os.environ.get("HVE_TEST_ALLOW_SYMLINK"),
        reason="Windows では symlink 作成に管理者権限または開発者モードが必要なため",
    )
    def test_rejects_symlink_actual(self, repo: Path):
        target = repo / "inputs" / "my-catalog.md"
        link = repo / "inputs" / "link.md"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            pytest.skip("symlink を作成できない環境")
        with pytest.raises(InputAliasError):
            validate_aliases(
                normalize_alias_pairs([(_APP_CATALOG, "inputs/link.md")]),
                workflow_id="aas",
                step_ids=["1"],
                repo_root=repo,
            )


class TestProducerOutputConflict:
    def test_rejects_alias_over_selected_producer_output(self, repo: Path):
        """`app-arch-catalog` は Step 1 の出力。Step 1 を選ぶと差し替えできない。"""
        with pytest.raises(InputAliasError) as exc:
            validate_aliases(
                normalize_alias_pairs([(_APP_ARCH_CATALOG, "inputs/my-catalog.md")]),
                workflow_id="aas",
                step_ids=["1", "2.1"],
                repo_root=repo,
            )
        assert _APP_ARCH_CATALOG in str(exc.value)

    def test_allows_alias_when_producer_step_is_not_selected(self, repo: Path):
        aliases = validate_aliases(
            normalize_alias_pairs([(_APP_ARCH_CATALOG, "inputs/my-catalog.md")]),
            workflow_id="aas",
            step_ids=["2.1"],
            repo_root=repo,
        )
        assert aliases[0].canonical == _APP_ARCH_CATALOG


class TestAliasResolver:
    def test_actual_for_returns_none_for_unaliased(self):
        r = AliasResolver([ResolvedAlias(canonical="a.md", actual="b.md")])
        assert r.actual_for("a.md") == "b.md"
        assert r.actual_for("c.md") is None

    def test_resolve_paths_keeps_unaliased_unchanged_and_preserves_order(self):
        r = AliasResolver([ResolvedAlias(canonical="a.md", actual="b.md")])
        assert r.resolve_paths(["a.md", "c.md"]) == ["b.md", "c.md"]

    def test_empty_resolver_is_falsy(self):
        assert not AliasResolver([])
        assert AliasResolver([ResolvedAlias(canonical="a.md", actual="b.md")])

    def test_resolve_paths_normalizes_windows_separators(self):
        r = AliasResolver([ResolvedAlias(canonical="docs/a.md", actual="in/b.md")])
        assert r.resolve_paths(["docs\\a.md"]) == ["in/b.md"]


class TestBuildAliasAddendum:
    def test_preserves_representative_output(self):
        step = get_step("aas", "1")
        assert step is not None
        addendum = build_alias_addendum(
            step,
            AliasResolver(
                [
                    ResolvedAlias(
                        canonical=_APP_CATALOG,
                        actual="inputs/my-catalog.md",
                    )
                ]
            ),
        )
        assert addendum == "\n".join(
            [
                "## 入力ファイルの別名（Prompt 版）",
                "",
                "以下の入力は canonical のパスではなく、指定された実ファイルを読むこと。出力先のパスは canonical のまま変更しない。",
                "- `docs/catalog/app-catalog.md` → `inputs/my-catalog.md`",
            ]
        ).replace(
            "変更しない。\n-",
            "変更しない。\n\n-",
        )


class TestRequirementIsDeclared:
    def test_fr_prompt_08_is_declared(self):
        text = Path("hve-dev/requirement-definition.md").read_text(encoding="utf-8")
        assert "**FR-PROMPT-08**" in text
