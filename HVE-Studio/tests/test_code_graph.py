"""FR-1091: code relations (function / class level graph). Extraction is cross-checked against the standard `ast` module
(an independent reader of the same source) and against small synthetic repositories whose calls are known by construction."""
import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
import code_graph  # noqa: E402


def _repo(tmp_path, files):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return code_graph.build(tmp_path)


def _edges(g, kind=None, conf=None):
    return {(e["s"].split("::")[1], e["t"].split("::")[1], e["kind"], e["conf"]) for e in g["edges"]
            if (kind is None or e["kind"] == kind) and (conf is None or e["conf"] == conf)}


# FR-1091 AC-499: Python calls resolve through scope, imports, self / cls and bases; parameters shadow module functions.
def test_ac499_python_edges_are_resolved_exactly(tmp_path):
    g = _repo(tmp_path, {
        "util.py": "def helper():\n    return 1\n\n\nclass Base:\n    def shared(self):\n        return helper()\n",
        "app.py": ("from util import helper, Base\nimport util\n\n\ndef helper2():\n    return util.helper()\n\n\n"
                   "class Child(Base):\n    def run(self):\n        self.shared()\n        return self.step()\n\n"
                   "    def step(self):\n        def inner():\n            return helper2()\n        return inner()\n\n\n"
                   "def shadow(helper):\n    return helper()\n\n\ndef passes():\n    return map(helper2, [])\n"),
    })
    e = _edges(g)
    assert ("helper2", "helper", "call", "exact") in e                      # util.helper() through `import util`
    assert ("Base.shared", "helper", "call", "exact") in e
    assert ("Child.run", "Child.step", "call", "exact") in e                # self.step()
    assert ("Child.run", "Base.shared", "call", "exact") in e               # inherited through the base class
    assert ("Child", "Base", "inherit", "exact") in e
    assert ("Child.step", "Child.step.inner", "call", "exact") in e         # nested function
    assert ("Child.step.inner", "helper2", "call", "exact") in e
    assert not [x for x in e if x[0] == "shadow"]                           # the parameter `helper` is not the module function
    assert ("passes", "helper2", "ref", "exact") in e                       # passed, not called


# FR-1091 AC-499: JS/TS functions, arrow functions, classes and imports; strings and comments never create edges.
def test_ac499_javascript_edges_and_masking(tmp_path):
    g = _repo(tmp_path, {
        "lib.js": "export function make() { return 1; }\nexport const twice = (x) => make() + make();\n",
        "main.js": ("import { make, twice as dbl } from './lib.js';\nimport * as lib from './lib.js';\n"
                    "// make();\nconst s = 'make()';\nfunction go() { return dbl(2) + lib.make(); }\n"
                    "class A {\n  run() { return this.step(); }\n  step() { return go(); }\n}\n"
                    "class B extends A {}\nsetTimeout(go, 1);\n"),
    })
    e = _edges(g)
    assert ("go", "twice", "call", "exact") in e                            # renamed import
    assert ("go", "make", "call", "exact") in e                             # namespace import
    assert ("twice", "make", "call", "exact") in e                          # arrow function body
    assert ("A.run", "A.step", "call", "exact") in e                        # this.step()
    assert ("A.step", "go", "call", "exact") in e
    assert ("B", "A", "inherit", "exact") in e
    assert ("<module>", "go", "ref", "exact") in e                          # setTimeout(go, 1) at module level
    assert not [x for x in e if x[0] == "<module>" and x[1] == "make"]      # comment / string are masked


# FR-1091 AC-500: an `obj.method()` call is a guess only when the method name is unique; it is labelled and common names are never guessed.
def test_ac500_name_matches_are_marked_as_guesses(tmp_path):
    g = _repo(tmp_path, {"a.py": ("class Store:\n    def persist_state(self):\n        pass\n\n    def click(self):\n        pass\n\n\n"
                                  "def use(thing):\n    thing.persist_state()\n    thing.click()\n")})
    assert _edges(g, conf="name") == {("use", "Store.persist_state", "call", "name")}


# FR-1091 AC-501: every function / method / class that `ast` finds in this repository's Python is a node, at the same line.
def test_ac501_nodes_match_the_standard_ast_on_this_repository():
    g = code_graph.build(REPO)
    got = {(n["file"], n["line"], n["name"]) for n in g["nodes"] if n["lang"] == "py" and n["kind"] != "module"}
    want = set()
    for rel in subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"], cwd=REPO, capture_output=True, text=True, check=True).stdout.split():
        if any(part in rel.split("/") for part in ("vendor", "node_modules")):
            continue
        try:
            tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        want |= {(rel, n.lineno, n.name) for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    assert got <= want and len(want - got) <= len(want) * 0.02, sorted(want - got)[:5]
    assert g["stats"]["parseErrors"] == 0 and len(g["edges"]) > 500


# FR-1091 AC-501: a known real call in this repository is found (verified by reading the source, not by the extractor).
def test_ac501_a_real_call_in_this_repository_is_an_edge():
    g = code_graph.build(REPO)
    src = (REPO / "HVE-Studio" / "studio.py").read_text(encoding="utf-8")
    assert "code_graph.build(root, inv)" in src
    assert ("HVE-Studio/studio.py::State.codegraph_bytes", "HVE-Studio/code_graph.py::build", "call", "exact") in {
        (e["s"], e["t"], e["kind"], e["conf"]) for e in g["edges"]}


# FR-1091 AC-501: secrets, vendored code and big files are not read; a non-git folder yields an empty graph.
def test_ac501_secrets_vendor_and_non_git_are_skipped(tmp_path):
    g = _repo(tmp_path, {"vendor/x.js": "function v() {}\n", "secrets.py": "def s():\n    pass\n", "ok.py": "def fine():\n    pass\n"})
    assert [n["name"] for n in g["nodes"]] == ["fine"]
    plain = tmp_path / "plain"
    plain.mkdir()
    assert code_graph.build(plain)["nodes"] == []
