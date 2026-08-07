"""Improvements to the regex-based languages (FR-CQ-04 / FR-CQ-11).

Guards the two defects found while reviewing the existing extractors: braces
inside string literals and comments corrupted parent attribution, and
TypeScript-only declarations were invisible because TypeScript reused the
JavaScript pattern table verbatim.

C# / JavaScript / TypeScript were upgraded to tree-sitter as the primary
extractor (FR-CQ-11 Phase 2); the regex extractor guarded here is now the
fallback tier, so these tests call `extract_regex` directly rather than
`languages.extractor_for(...)` — otherwise, in an environment where the
optional tree-sitter grammar is installed, they would silently stop
exercising the regex path they exist to guard.
"""

from __future__ import annotations

from cq import languages
from cq.languages import csharp, javascript, typescript
from cq.languages.linescan import brace_delta, code_only


class TestBraceCounting:
    def test_braces_in_strings_are_ignored(self) -> None:
        assert brace_delta('const a = "{";') == 0
        assert brace_delta("const a = '}';") == 0
        assert brace_delta("const a = `{{{`;") == 0

    def test_braces_in_comments_are_ignored(self) -> None:
        assert brace_delta("doWork(); // }") == 0
        assert brace_delta("doWork(); /* { */") == 0

    def test_real_braces_still_count(self) -> None:
        assert brace_delta("if (a) {") == 1
        assert brace_delta("}") == -1

    def test_escaped_quote_does_not_end_the_string(self) -> None:
        assert code_only(r'a = "he said \" }";').count("}") == 0


class TestJavaScriptScopes:
    SOURCE = """\
class LedgerView {
  render(items) {
    console.log("}");
    return items;
  }

  reset() {
    return 0;
  }
}
"""

    def test_methods_keep_their_class_after_a_brace_in_a_string(self) -> None:
        symbols = {s.name: s for s in javascript.extract_regex(self.SOURCE)}
        assert symbols["render"].parent == "LedgerView"
        assert symbols["reset"].parent == "LedgerView"
        assert symbols["reset"].qualname == "LedgerView.reset"


class TestCSharpScopes:
    SOURCE = """\
public sealed class LedgerService
{
    public void Log()
    {
        Console.WriteLine("}");
    }

    public void Reset()
    {
    }
}
"""

    def test_members_keep_their_type_after_a_brace_in_a_string(self) -> None:
        symbols = {s.name: s for s in csharp.extract_regex(self.SOURCE)}
        assert symbols["Reset"].parent == "LedgerService"


class TestTypeScript:
    SOURCE = """\
export interface Ledger {
  grant(id: string): boolean;
}

export type Points = number;

export enum Status {
  Ok,
  Ng,
}

export abstract class BaseService implements Ledger {
  grant(id: string): boolean {
    return true;
  }

  private reset(): void {
  }
}

export function mountScreen(container: HTMLElement): HTMLElement {
  return container;
}
"""

    def _symbols(self):
        return {s.qualname: s for s in typescript.extract_regex(self.SOURCE)}

    def test_interface_is_extracted(self) -> None:
        assert self._symbols()["Ledger"].kind == "interface"

    def test_type_alias_is_extracted(self) -> None:
        assert self._symbols()["Points"].kind == "type"

    def test_enum_is_extracted(self) -> None:
        assert self._symbols()["Status"].kind == "enum"

    def test_abstract_class_is_extracted(self) -> None:
        assert self._symbols()["BaseService"].kind == "class"

    def test_method_with_return_type_annotation_is_extracted(self) -> None:
        symbols = self._symbols()
        assert symbols["BaseService.grant"].kind == "method"
        assert symbols["BaseService.reset"].kind == "method"

    def test_interface_method_signature_is_extracted(self) -> None:
        assert self._symbols()["Ledger.grant"].kind == "method"

    def test_exported_function_still_works(self) -> None:
        assert self._symbols()["mountScreen"].kind == "function"

    def test_typescript_is_no_longer_the_javascript_extractor(self) -> None:
        assert languages.extractor_for("typescript") is not languages.extractor_for("javascript")
