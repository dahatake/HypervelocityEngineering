"""Contracts for the tree-sitter backed languages (FR-CQ-04 / FR-CQ-05 / FR-CQ-11).

The fixtures encode the pitfalls found while bringing these languages up; each
one is named in the test that guards it, so the expectations stay readable
without an external spike report.
"""

from __future__ import annotations

import subprocess
from collections import Counter
from contextlib import closing
from pathlib import Path

import pytest

from cq import chunking, config, indexer, languages, store
from cq.languages import treesitter as ts

pytest.importorskip("tree_sitter", reason="optional [code] extra is not installed")

JAVA = """\
package com.example.svc;

import java.util.List;

/** Grants reward points. */
@Service
public class RewardService implements Ledger {
    private final int seed;

    public RewardService(int seed) {
        this.seed = seed;
    }

    /** Grants points to a member. */
    @Override
    public <T extends Number> GrantResult grant(GrantCommand command, T attempts) {
        Runnable task = new Runnable() {
            public void run() {
                System.out.println("} not a brace {");
            }
        };
        task.run();
        String block = \"\"\"
                { still not a brace }
                \"\"\";
        return new GrantResult(block, attempts.intValue());
    }

    public interface Callback {
        void onDone(String id);
    }

    public enum Status {
        OK,
        NG
    }

    public record GrantCommand(String id, int amount) {}

    @Test
    public void grantsPoints() {}
}
"""

GO = """\
package svc

import (
\t"errors"
\ttpl "html/template"
)

// Ledger grants points.
type Ledger interface {
\tGrant(id string) error
}

// Service is the default ledger.
type Service struct {
\tseed int
}

// Grant grants points to a member.
func (s *Service) Grant(id string) error {
\traw := `{ not a brace }`
\t_ = tpl.HTMLEscapeString(raw)
\treturn errors.New("nope")
}

func (s Service) Reset() {}

func (b *Bucket[T]) Add(item T) {}

func Map[T any](xs []T) []T { return xs }

type ID = string

func TestGrant(t *testing.T) {}
"""

RUST = """\
//! Reward service.

use crate::core::Ledger as CoreLedger;

/// Grants reward points.
pub struct Service {
    seed: u32,
}

pub enum Status {
    Ok,
    Ng,
}

pub trait Ledger {
    fn grant(&self, id: &str) -> bool;
}

pub type Points = u32;

impl Service {
    /// Grants points to a member.
    pub fn grant<T>(&self, id: &str, extra: T) -> bool
    where
        T: Into<Points>,
    {
        let raw = r#"{ not a brace }"#;
        let _ = (raw, extra, id);
        true
    }
}

impl Ledger for Service {
    fn grant(&self, id: &str) -> bool {
        let _ = id;
        true
    }
}

pub mod inner {
    pub fn helper() -> u32 {
        0
    }
}

macro_rules! trace_it {
    () => {};
}

#[cfg(feature = "latest")]
pub fn latest_only() {}

#[test]
fn grants_points() {}
"""

C = """\
#include <stdio.h>
#include "svc/ledger.h"

#define MAX_RETRY 3
#define GRANT(x) ((x) + 1)

struct Grant {
    int amount;
};

union Payload {
    int i;
};

enum Status { OK, NG };

typedef struct {
    int id;
} Member;

typedef int (*callback)(void);

int parse_header(const char *raw);

int parse_header(const char *raw) {
    char brace = '{';
    (void)brace;
    (void)raw;
    return grant_helper(0);
}

#ifdef FEATURE
static void feature_on(void) {}
#else
static void feature_off(void) {}
#endif
"""

CPP = """\
#include <vector>

namespace svc {

class Ledger {
public:
    virtual ~Ledger() = default;
    virtual bool grant(int id) = 0;
    bool helper(int id);
};

template <typename T>
class Service : public Ledger {
public:
    Service();
    ~Service();
    bool grant(int id) override;
    Service& operator+=(int n);
    using Alias = T;
};

}  // namespace svc

bool svc::Ledger::helper(int id) {
    const char *raw = R"delim({ not a brace })delim";
    (void)raw;
    (void)id;
    return true;
}

namespace {
void anonymous_helper() {}
}
"""

HEADER_CPP = """\
#ifndef SVC_LEDGER_H
#define SVC_LEDGER_H

namespace svc {

class LedgerHeader {
public:
    bool grant(int id);
};

}  // namespace svc

#endif
"""

HEADER_C = """\
#ifndef SVC_LEDGER_C_H
#define SVC_LEDGER_C_H

struct LedgerHandle {
    int fd;
};

int ledger_open(const char *path);

#endif
"""

SOURCES = {
    "java": JAVA,
    "go": GO,
    "rust": RUST,
    "c": C,
    "cpp": CPP,
}

EXPECTED = {
    "java": [
        ("class", "RewardService"),
        ("constructor", "RewardService.RewardService"),
        ("method", "RewardService.grant"),
        ("interface", "RewardService.Callback"),
        ("method", "RewardService.Callback.onDone"),
        ("enum", "RewardService.Status"),
        ("class", "RewardService.GrantCommand"),
        ("method", "RewardService.grantsPoints"),
    ],
    "go": [
        ("interface", "Ledger"),
        ("method", "Ledger.Grant"),
        ("struct", "Service"),
        ("method", "Service.Grant"),
        ("method", "Service.Reset"),
        ("method", "Bucket.Add"),
        ("function", "Map"),
        ("type", "ID"),
        ("function", "TestGrant"),
    ],
    "rust": [
        ("struct", "Service"),
        ("enum", "Status"),
        ("interface", "Ledger"),
        ("method", "Ledger.grant"),
        ("type", "Points"),
        ("method", "Service.grant"),
        ("method", "Service.grant"),
        ("module", "inner"),
        ("function", "inner.helper"),
        ("macro", "trace_it"),
        ("function", "latest_only"),
        ("function", "grants_points"),
    ],
    "c": [
        ("macro", "GRANT"),
        ("struct", "Grant"),
        ("struct", "Payload"),
        ("enum", "Status"),
        ("type", "Member"),
        ("type", "callback"),
        ("prototype", "parse_header"),
        ("function", "parse_header"),
        ("function", "feature_on"),
        ("function", "feature_off"),
    ],
    "cpp": [
        ("namespace", "svc"),
        ("class", "svc::Ledger"),
        ("method", "svc::Ledger::~Ledger"),
        ("method", "svc::Ledger::grant"),
        ("method", "svc::Ledger::helper"),
        ("method", "svc::Ledger::helper"),
        ("class", "svc::Service"),
        ("method", "svc::Service::Service"),
        ("method", "svc::Service::~Service"),
        ("method", "svc::Service::grant"),
        ("method", "svc::Service::operator+="),
        ("type", "svc::Service::Alias"),
        ("function", "anonymous_helper"),
    ],
}


def _symbols(lang: str):
    return languages.support_for(lang).extract(SOURCES[lang])


@pytest.mark.parametrize("lang", sorted(SOURCES))
class TestSymbolContract:
    def test_expected_symbols_are_extracted(self, lang: str) -> None:
        """Multisets, not sets: duplicate qualnames are distinct definitions."""
        got = Counter((s.kind, s.qualname) for s in _symbols(lang))
        want = Counter(EXPECTED[lang])
        assert (want - got) == Counter(), f"missing: {sorted((want - got).elements())}"
        assert (got - want) == Counter(), f"unexpected: {sorted((got - want).elements())}"

    def test_line_ranges_stay_inside_the_file(self, lang: str) -> None:
        total = len(SOURCES[lang].splitlines())
        for symbol in _symbols(lang):
            assert 1 <= symbol.start_line <= symbol.end_line <= total

    def test_extraction_is_deterministic(self, lang: str) -> None:
        assert _symbols(lang) == _symbols(lang)

    def test_every_callable_has_a_signature(self, lang: str) -> None:
        callables = {"function", "method", "constructor", "prototype", "macro"}
        assert all(s.signature for s in _symbols(lang) if s.kind in callables)

    def test_chunks_partition_the_file(self, lang: str) -> None:
        source = SOURCES[lang]
        total = len(source.splitlines())
        for budget in (1600, 200):
            chunks = chunking.chunk_source(source, lang, max_chars=budget)
            covered = [n for c in chunks for n in range(c.start_line, c.end_line + 1)]
            assert covered == list(range(1, total + 1)), f"{lang}@{budget}"

    def test_chunking_is_deterministic(self, lang: str) -> None:
        first = chunking.chunk_source(SOURCES[lang], lang, max_chars=200)
        second = chunking.chunk_source(SOURCES[lang], lang, max_chars=200)
        assert [(c.start_line, c.end_line) for c in first] == [
            (c.start_line, c.end_line) for c in second
        ]


class TestJava:
    def test_javadoc_head_drops_the_closing_marker(self) -> None:
        by_name = {s.qualname: s for s in _symbols("java")}
        assert by_name["RewardService"].doc_head == "Grants reward points."

    def test_annotations_are_recorded(self) -> None:
        by_name = {s.qualname: s for s in _symbols("java")}
        assert "Override" in by_name["RewardService.grant"].decorators

    def test_test_annotation_marks_the_method(self) -> None:
        by_name = {s.qualname: s for s in _symbols("java")}
        assert by_name["RewardService.grantsPoints"].is_test
        assert not by_name["RewardService.grant"].is_test

    def test_anonymous_class_members_are_not_reparented(self) -> None:
        """D7: `run` must not become a member of the enclosing named class."""
        assert not any(s.name == "run" for s in _symbols("java"))

    def test_imports_and_calls_are_indexed(self) -> None:
        refs, imports = languages.graph_extractor_for("java")(JAVA)
        assert any(module == "java.util.List" for _, module in imports)
        assert any(name == "run" for _, name in refs)


class TestGo:
    def test_type_declaration_keeps_its_doc_comment(self) -> None:
        """D9: the comment sits above `type_declaration`, not `type_spec`."""
        by_name = {s.qualname: s for s in _symbols("go")}
        assert by_name["Ledger"].doc_head == "Ledger grants points."

    def test_pointer_and_generic_receivers_resolve_to_the_base_type(self) -> None:
        by_name = {s.qualname: s for s in _symbols("go")}
        assert by_name["Service.Grant"].parent == "Service"
        assert by_name["Bucket.Add"].parent == "Bucket"

    def test_testing_convention_marks_the_function(self) -> None:
        by_name = {s.qualname: s for s in _symbols("go")}
        assert by_name["TestGrant"].is_test
        assert not by_name["Map"].is_test

    def test_grouped_imports_are_indexed(self) -> None:
        _, imports = languages.graph_extractor_for("go")(GO)
        assert {module for _, module in imports} == {"errors", "html/template"}


class TestRust:
    def test_module_functions_are_not_promoted_to_methods(self) -> None:
        """D4: only type-like scopes bind a function to a type."""
        by_name = {s.qualname: s for s in _symbols("rust")}
        assert by_name["inner.helper"].kind == "function"

    def test_inherent_and_trait_impls_are_both_indexed(self) -> None:
        grants = [s for s in _symbols("rust") if s.qualname == "Service.grant"]
        assert len(grants) == 2
        assert grants[0].start_line != grants[1].start_line

    def test_cfg_feature_latest_is_not_a_test(self) -> None:
        by_name = {s.qualname: s for s in _symbols("rust")}
        assert not by_name["latest_only"].is_test
        assert by_name["grants_points"].is_test

    def test_use_declarations_are_imports(self) -> None:
        _, imports = languages.graph_extractor_for("rust")(RUST)
        assert any("crate::core::Ledger" in module for _, module in imports)


class TestCFamily:
    def test_function_like_macro_is_indexed(self) -> None:
        """D1: `preproc_function_def` exposes `name`, not `declarator`."""
        assert ("macro", "GRANT") in {(s.kind, s.qualname) for s in _symbols("c")}

    def test_object_like_macro_is_out_of_scope(self) -> None:
        assert "MAX_RETRY" not in {s.name for s in _symbols("c")}

    def test_prototype_and_definition_are_distinct(self) -> None:
        kinds = {s.kind for s in _symbols("c") if s.qualname == "parse_header"}
        assert kinds == {"prototype", "function"}

    def test_function_pointer_typedef_is_a_type(self) -> None:
        by_name = {s.qualname: s for s in _symbols("c")}
        assert by_name["callback"].kind == "type"

    def test_both_preprocessor_branches_are_indexed(self) -> None:
        names = {s.name for s in _symbols("c")}
        assert {"feature_on", "feature_off"} <= names

    def test_operator_overload_is_found_without_field_names(self) -> None:
        """D6: `reference_declarator` exposes unnamed fields."""
        assert "svc::Service::operator+=" in {s.qualname for s in _symbols("cpp")}

    def test_out_of_class_definition_keeps_the_class_parent(self) -> None:
        """D5: the qualifier is resolved against the types declared in the file."""
        helpers = [s for s in _symbols("cpp") if s.qualname == "svc::Ledger::helper"]
        assert helpers and all(s.parent == "svc::Ledger" and s.kind == "method" for s in helpers)

    def test_anonymous_namespace_contributes_no_scope(self) -> None:
        """D8: `(anonymous)` must not leak into a qualname."""
        assert "anonymous_helper" in {s.qualname for s in _symbols("cpp")}

    def test_includes_are_imports(self) -> None:
        _, imports = languages.graph_extractor_for("c")(C)
        assert {module for _, module in imports} == {"stdio.h", "svc/ledger.h"}


class TestHeaderDisambiguation:
    def test_cpp_header_is_detected_by_cpp_only_nodes(self) -> None:
        from cq.languages import cfamily

        assert cfamily.language_for_header(HEADER_CPP) == "cpp"

    def test_plain_c_header_is_not_claimed_by_cpp(self) -> None:
        from cq.languages import cfamily

        assert cfamily.language_for_header(HEADER_C) == "c"

    def test_error_counting_alone_cannot_separate_them(self) -> None:
        """Recorded so the weaker rule is never reintroduced."""
        from cq.languages import cfamily

        c_root = ts.parse(cfamily.C_GRAMMAR, HEADER_C).root_node
        cpp_root = ts.parse(cfamily.CPP_GRAMMAR, HEADER_C).root_node
        assert cfamily._errors(c_root) == cfamily._errors(cpp_root) == 0

    def test_resolver_routes_dot_h_by_content(self) -> None:
        assert languages.resolve_language(".h", lambda: HEADER_CPP) == "cpp"
        assert languages.resolve_language(".h", lambda: HEADER_C) == "c"


class TestDegradationWithoutGrammars:
    def test_missing_grammar_degrades_instead_of_raising(self, monkeypatch) -> None:
        grammar = ts.Grammar(
            lang="absent",
            module="tree_sitter_absent",
            kinds={},
            scopes={},
            name_of=lambda n, s: "",
            scope_name_of=lambda n, s: "",
            doc_markers=("//",),
        )
        monkeypatch.setattr(ts, "_PARSERS", {})
        with pytest.raises(languages.ExtractionError):
            ts.extract(grammar, "int a;\n")


SUFFIXES = {"java": ".java", "go": ".go", "rust": ".rs", "c": ".c", "cpp": ".cpp"}


@pytest.fixture(scope="module")
def db(tmp_path_factory) -> Path:
    repo = tmp_path_factory.mktemp("ts-corpus")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "cq.toml").write_text("[profiles.test]\nroots = ['pkg']\n", encoding="utf-8")
    pkg = repo / "pkg"
    pkg.mkdir()
    for lang, suffix in SUFFIXES.items():
        (pkg / f"sample{suffix}").write_text(SOURCES[lang], encoding="utf-8")
    (pkg / "api.h").write_text(HEADER_CPP, encoding="utf-8")
    database = repo / ".cq" / "index-test.sqlite"
    report = indexer.build_index(repo, config.resolve_profile(repo, "test"), db_path=database)
    assert report.errors == 0 and report.degraded == 0
    return database


class TestIndexIntegration:
    """End-to-end index pass: this repository holds no source in these languages,
    so the whole `build_index` path would otherwise stay unmeasured."""

    def test_every_language_file_records_the_tree_sitter_fidelity(self, db: Path) -> None:
        with closing(store.open_store(db, create=False)) as conn:
            rows = dict(conn.execute("SELECT lang, parser FROM files").fetchall())
        assert rows == {lang: "tree-sitter" for lang in list(SUFFIXES) + ["cpp"]}

    def test_header_language_is_resolved_from_content(self, db: Path) -> None:
        with closing(store.open_store(db, create=False)) as conn:
            lang = conn.execute(
                "SELECT lang FROM files WHERE path LIKE '%api.h'"
            ).fetchone()[0]
        assert lang == "cpp"

    @pytest.mark.parametrize("lang", sorted(SUFFIXES))
    def test_symbols_and_chunks_are_persisted_per_language(self, db: Path, lang: str) -> None:
        path = f"pkg/sample{SUFFIXES[lang]}"
        with closing(store.open_store(db, create=False)) as conn:
            symbols = conn.execute(
                "SELECT COUNT(*) FROM symbols WHERE path = ?", (path,)
            ).fetchone()[0]
            chunks = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE path = ?", (path,)
            ).fetchone()[0]
        assert symbols == len(EXPECTED[lang])
        assert chunks > 0

    def test_graph_rows_are_persisted(self, db: Path) -> None:
        with closing(store.open_store(db, create=False)) as conn:
            refs = conn.execute("SELECT COUNT(*) FROM refs").fetchone()[0]
            imports = conn.execute("SELECT COUNT(*) FROM imports").fetchone()[0]
        assert refs > 0 and imports > 0

    def test_chunks_link_to_existing_symbols(self, db: Path) -> None:
        with closing(store.open_store(db, create=False)) as conn:
            orphans = conn.execute(
                "SELECT COUNT(*) FROM chunks c WHERE c.symbol_id IS NOT NULL"
                " AND NOT EXISTS (SELECT 1 FROM symbols s WHERE s.symbol_id = c.symbol_id)"
            ).fetchone()[0]
            linked = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE symbol_id IS NOT NULL"
            ).fetchone()[0]
        assert orphans == 0
        assert linked > 0
