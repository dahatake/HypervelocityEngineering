"""HVE アプリケーション保守の選択的要件参照契約（T03 RED）。

FR-MAINT-01〜03 / NFR-CTX-01 に対応し、長大な要求定義書を常時注入せず、
短い repository-wide ルーター、HVE コア限定 instructions、オンデマンド Skill から
同じ要求トレーサビリティ手順へ到達することを固定する。
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import yaml  # type: ignore[import-untyped]


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILL = (
    _REPO_ROOT
    / ".github"
    / "skills"
    / "hve-requirement-traceability"
    / "SKILL.md"
)
_ROUTING = _REPO_ROOT / ".github" / "skills" / "_routing" / "README.md"
_INSTRUCTIONS = (
    _REPO_ROOT
    / ".github"
    / "instructions"
    / "hve-maintenance.instructions.md"
)
_COPILOT_INSTRUCTIONS = _REPO_ROOT / ".github" / "copilot-instructions.md"
_REQUIREMENT_DEFINITION = "hve-dev/requirement-definition.md"
_REQUIREMENT_MAPPING = "hve-dev/requirement-test-mapping.md"
_FEATURE_INVENTORY = "hve-dev/hve-feature-inventory.csv"
_TEST_INVENTORY = "hve-dev/hve-test-inventory.csv"
_TDD_POLICY = "hve-dev/hve-tdd-change-policy.md"
_TDD_POLICY_GENERATOR = "hve-dev/generate_tdd_inventory.py"
_SKILL_REFERENCE = ".github/skills/hve-requirement-traceability/SKILL.md"
_APPLY_TO = (
    "hve/**,mdq/**,cq/**,hve-dev/**,tools/skills/markdown_query/**,"
    "tools/skills/code_query/**"
)
_ROUTING_ROW = (
    "| HVE アプリケーション自体の保守 / 要求トレーサビリティ "
    "| `hve-requirement-traceability` "
    "| `.github/skills/hve-requirement-traceability/SKILL.md` "
    "| active 要件と実在テストを選択取得 |"
)
_FEATURE_STEPS = (
    "要求定義へ active 要件を追加または改訂する。",
    "要求テストマッピングへ受入テストを追加し、未実装なら `要追加` と記録する。",
    "同じ対象テストを作成して RED を確認する。",
    "`hve-dev/hve-feature-inventory.csv` と `hve-dev/hve-test-inventory.csv` を再生成し、新規 ID・source・status・テストパスを照合する。",
    "実装する。",
    "同じ対象テストで GREEN を確認する。",
    "要求テストマッピングへ実結果を反映する。",
)
_RETRIEVAL_STEPS = (
    "`python -m mdq search --q \"<検索語>\" --paths \"hve-dev/requirement-definition.md\" --top-k 5 --max-tokens 800` で初回取得する。",
    "初回結果が不足する場合に限り、親見出しを 1 段取得する。",
    "親見出しでも不足する場合に限り、隣接チャンクを 1 段取得する。",
    "隣接チャンクでも不足する場合に限り、関連章を取得する。",
    "0 件または矛盾時は検索語を変えて最大 2 回再試行し、解消しなければ理由を記録して確認を求める。",
)
_SCOPE_LINES = (
    "- HVE アプリケーション自体の保守にだけ適用する。",
    "- HVE が生成・支援する他アプリケーションには適用しない。",
)
_BEFORE_EDIT_LINES = (
    f"1. `{_FEATURE_INVENTORY}` で候補 ID を絞り込む。",
    f"2. `{_REQUIREMENT_DEFINITION}` で定義と source を確認する。",
    f"3. `{_REQUIREMENT_MAPPING}` で対応テストを確認する。",
    f"- `source={_REQUIREMENT_DEFINITION}` かつ `active-or-described` だけを適用可能とする。",
    "- 未知・競合・`deprecated-or-removed`・`partial-or-not-supported` の ID は現行要件として適用してはならない。",
    "- 索引と要求定義の不整合を解消するまで実装へ進まない。",
    "- 適用してよいのは規範要件（`FR-*` / `NFR-*` / `G-*` の定義行と、当該要件が明示的に参照する従属表・箇条書き・スキーマ）だけとする。逆抽出の表・構成・確認時点の記述は説明的基線、改訂履歴・解消済み TBD・`deprecated-or-removed` は履歴情報であり、現行要件として適用しない。",
    "- 現行コードと規範要件が矛盾する場合、コードを正解として要件を上書きせず、バグ修正か仕様変更かを明示して解消する。仕様変更なら実装前に規範要件を改訂する。",
)
_BOOTSTRAP_LINES = (
    *(f"{index}. {step}" for index, step in enumerate(_FEATURE_STEPS, 1)),
    f"- 索引照合では `source={_REQUIREMENT_DEFINITION}`、`active-or-described`、テストパスを確認する。",
    "- 新規 ID は要求定義書の定義行を一次情報とする。",
    "- 新規 ID は同一変更セット内だけで暫定規範として扱う。",
    "- 索引照合が完了するまで新規 ID を他の変更から利用しない。",
    "- bootstrap 中の新規 ID を既存要件へ偽装しない。",
    f"- `{_TDD_POLICY}` または生成元 `{_TDD_POLICY_GENERATOR}` が §3.7 と矛盾する場合は §3.7 を正とし、同一変更で同期する。",
)
_FEATURE_LINES = (
    *(f"{index}. {step}" for index, step in enumerate(_FEATURE_STEPS, 1)),
    "- feature では要件 ID・実在テストパス・RED / GREEN 証跡の N/A を認めない。",
    "- bugfix / maintenance で N/A を使う場合は具体的理由と人間レビューを必須とする。",
    f"- `{_TDD_POLICY}` と生成元 `{_TDD_POLICY_GENERATOR}` は §3.7 と同一変更で同期する。",
    "- 変更種別は `feature` / `bugfix` / `maintenance` の 3 値とする。観測できる能力・動作・公開インタフェース・設定・Workflow / Prompt / I/O 契約を追加または変更するなら `feature`、既存の規範要件または明示済み受入条件へ戻すだけなら `bugfix`、実行時の観測可能な挙動を変えないなら `maintenance` とする。分類を確定できない場合は `feature` とする。",
)
_RETRIEVAL_LINES = (
    "- 検索キーは Issue 本文、対象パス、対象 symbol、失敗テスト、Workflow / Step ID から構成する。",
    f"- 要件 ID が既知の場合は検索せず、`{_FEATURE_INVENTORY}` の当該行の `line` 列が指す定義行だけを読む。ID が未知の場合に限り以下の検索へ進む。",
    *(f"{index}. {step}" for index, step in enumerate(_RETRIEVAL_STEPS, 1)),
    "- 索引欠損・stale・検索 CLI 障害時は、特定済みの要件 ID または見出しだけを read / grep する。",
    "- 本規則を汎用 Markdown 検索 fallback より優先する。",
    "- 要求書全文へ自動 fallback しない。",
)
_FULL_READ_LINES = (
    "- ユーザーの明示要求がある場合。",
    "- 要求定義書自体を横断改訂する場合。",
    "- 章単位でも解消できない複数章の矛盾がある場合。",
    "- 上記以外では要求定義書全文を取得しない。",
)
_PURPOSE_LINES = (
    "HVE アプリケーション自体の保守で、関連する active 要件と実在テストだけを選択的に確認する。",
)
_NON_GOAL_LINES = (
    "- HVE が生成・支援する他アプリケーションの要件検索は扱わない。",
    "- HVE が生成・支援する他アプリケーションの成果物間の重複は扱わない。`app-scope-resolution` Skill と生成物側のカタログが担う。",
    "- 要求定義書全文を常時読み込まない。",
    "- 要件 ID、変更種別、テスト結果を推測しない。",
)
_CROSS_SURFACE_LINES = (
    "HVE 対象パスへ新規の判定・生成・検証ロジックを追加する場合にだけ適用する（FR-MAINT-07）。",
    "1. `hve-dev/hve-surface-inventory.csv` の `rule_tokens` 列を対象の規範リテラルで検索する。",
    "2. 不足する場合に限り `behavior_summary` 列を検索する。",
    "3. なお不足する場合に限り `symbol` 列を検索する。",
    "- この順序は、名前や構文の類似だけでは識別子の異なる同一手続きへ到達できないために定める。",
    "- シンボル名の不一致だけを根拠に既存実装が無いと判断してはならない。",
    "- 2 面以上に同一ルールの判定実装がある場合は新規実装を追加せず、単一実装へ寄せる。",
    "- ヒット 0 件の場合に限り新規実装を許可し、どの実行面を単一実装とするかをタスク完了報告へ記録する。",
    "- 索引が生成元と一致しない場合は stale として扱い、再生成するまで判断根拠に使わない。",
)
_SKILL_H2_HEADINGS = (
    "目的",
    "適用範囲",
    "Non-goals（このスキルの範囲外）",
    "編集前確認",
    "面横断の再利用確認",
    "新規要件 ID の bootstrap",
    "feature の TDD 順序",
    "関連要件の選択取得",
    "全文取得の例外",
)


def _read_required(path: Path) -> str:
    assert path.is_file(), f"required customization file is missing: {path}"
    return path.read_text(encoding="utf-8-sig")


def _frontmatter(text: str) -> str:
    assert text.startswith("---\n")
    end = text.find("\n---\n", 4)
    assert end >= 0
    return text[4:end]


def _frontmatter_data(text: str) -> dict[str, object]:
    frontmatter = _frontmatter(text)
    node = yaml.compose(frontmatter)
    assert isinstance(node, yaml.MappingNode)

    def assert_unique_mapping_keys(current: yaml.Node, path: str = "$") -> None:
        if isinstance(current, yaml.MappingNode):
            keys = [(key.tag, key.value) for key, _value in current.value]
            assert len(keys) == len(set(keys)), (
                f"duplicate frontmatter keys at {path}: "
                f"{[value for _tag, value in keys]}"
            )
            assert all(
                tag != "tag:yaml.org,2002:merge" and value != "<<"
                for tag, value in keys
            ), (
                f"YAML merge keys are not allowed in frontmatter at {path}"
            )
            for key, value in current.value:
                assert_unique_mapping_keys(value, f"{path}.{key.value}")
        elif isinstance(current, yaml.SequenceNode):
            for index, value in enumerate(current.value):
                assert_unique_mapping_keys(value, f"{path}[{index}]")

    assert_unique_mapping_keys(node)
    data = yaml.safe_load(frontmatter)
    assert isinstance(data, dict)
    return data


def _body(text: str) -> str:
    end = text.find("\n---\n", 4)
    assert end >= 0
    return text[end + len("\n---\n") :]


def _nonempty_lines(text: str) -> tuple[str, ...]:
    return tuple(line.rstrip() for line in text.splitlines() if line.strip())


def _opening_fence(line: str) -> tuple[str, int] | None:
    match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
    if not match:
        return None
    marker, info = match.groups()
    if marker[0] == "`" and "`" in info:
        return None
    return marker[0], len(marker)


def _closing_fence(line: str, fence: tuple[str, int]) -> bool:
    match = re.match(r"^ {0,3}(`{3,}|~{3,})[ \t]*$", line)
    if not match:
        return False
    marker = match.group(1)
    return marker[0] == fence[0] and len(marker) >= fence[1]


def _strip_html_comments(
    line: str, in_comment: bool = False
) -> tuple[str, bool, bool]:
    """Strip comments while preserving visible text before and after them."""
    visible = ""
    remaining = line
    changed = False
    if in_comment:
        changed = True
        if "-->" not in remaining:
            return "", True, changed
        _comment, remaining = remaining.split("-->", 1)
    while "<!--" in remaining:
        prefix, remainder = remaining.split("<!--", 1)
        visible += prefix
        changed = True
        if "-->" not in remainder:
            return visible, True, changed
        _comment, remaining = remainder.split("-->", 1)
    return visible + remaining, False, changed


def _description_clauses(description: str) -> tuple[str, str, str]:
    matches = list(
        re.finditer(
            r"\b(USE FOR|DO NOT USE FOR|WHEN)\s*:",
            description,
            re.IGNORECASE,
        )
    )
    assert [match.group(1).upper() for match in matches] == [
        "USE FOR",
        "DO NOT USE FOR",
        "WHEN",
    ]
    clauses: list[str] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(description)
        clause = description[match.end() : end].strip()
        assert clause
        clauses.append(clause)
    return clauses[0], clauses[1], clauses[2]


def _parse_h2_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Return preamble and visible H2 sections using Markdown's 0-3 space rule."""
    preamble: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None
    fence: tuple[str, int] | None = None
    html_comment = False

    def append_content(line: str) -> None:
        if current is None:
            preamble.append(line)
        else:
            current[1].append(line)

    for line in text.splitlines():
        if fence is not None:
            append_content(line)
            if _closing_fence(line, fence):
                fence = None
            continue
        if html_comment:
            append_content(line)
            _visible_line, html_comment, _comment_changed = _strip_html_comments(
                line, in_comment=True
            )
            continue
        visible_line = line
        opening = _opening_fence(line)
        if opening is not None:
            fence = opening
            append_content(line)
            continue
        if re.match(r"^(?: {4}|\t)", line):
            append_content(line)
            continue
        if re.match(r"^ {0,3}<!--", line):
            append_content(line)
            _visible_line, html_comment, _comment_changed = _strip_html_comments(line)
            continue
        visible_line, html_comment, _comment_changed = _strip_html_comments(visible_line)
        heading = re.match(r"^ {0,3}##(?!#)\s+(.+?)\s*$", visible_line)
        if heading:
            current = (heading.group(1), [])
            sections.append(current)
            continue
        append_content(line)
    return "\n".join(preamble), [
        (heading, "\n".join(lines)) for heading, lines in sections
    ]


def _h2_sections(text: str) -> list[tuple[str, str]]:
    return _parse_h2_sections(text)[1]


def _visible_markdown_lines(text: str) -> tuple[tuple[int, str], ...]:
    """Return physical line numbers and text outside fences/comments."""
    visible: list[tuple[int, str]] = []
    fence: tuple[str, int] | None = None
    html_comment = False
    for line_number, line in enumerate(text.splitlines()):
        if fence is not None:
            if _closing_fence(line, fence):
                fence = None
            continue
        if html_comment:
            _visible_line, html_comment, _comment_changed = _strip_html_comments(
                line, in_comment=True
            )
            continue
        visible_line = line
        opening = _opening_fence(line)
        if opening is not None:
            fence = opening
            continue
        if re.match(r"^(?: {4}|\t)", line):
            continue
        if re.match(r"^ {0,3}<!--", line):
            _visible_line, html_comment, _comment_changed = _strip_html_comments(line)
            continue
        visible_line, html_comment, _comment_changed = _strip_html_comments(visible_line)
        if visible_line.strip():
            visible.append((line_number, visible_line.rstrip()))
    return tuple(visible)


def _section_exact(text: str, title: str) -> str:
    matches = [body for heading, body in _h2_sections(text) if heading == title]
    assert len(matches) == 1, f"expected one section {title!r}, found {len(matches)}"
    return matches[0]


def test_skill_is_discoverable_and_routed_for_hve_maintenance() -> None:
    skill = _read_required(_SKILL)
    frontmatter = _frontmatter_data(skill)
    routing = _read_required(_ROUTING)

    assert set(frontmatter) >= {"name", "description", "metadata"}
    assert frontmatter.get("name") == "hve-requirement-traceability"
    description = str(frontmatter.get("description", ""))
    use_for, do_not_use_for, when = _description_clauses(description)
    assert re.search(r"HVE", description, re.I)
    assert re.search(r"requirement|traceability|要求|要件", use_for, re.I)
    assert re.search(r"maintenance|bugfix|bug fix|保守|バグ修正", use_for, re.I)
    assert not re.search(r"unrelated|generated app|non-HVE|他アプリ", use_for, re.I)
    assert not re.search(
        r"ignore|forbid|prohibit|must\s+not|do\s+not|禁止|除外|使用しない|適用しない",
        use_for,
        re.I,
    )
    assert re.search(r"generated app|non-HVE|他アプリ", do_not_use_for, re.I)
    assert not re.search(r"maintenance|bugfix|bug fix|HVE core|HVE 保守", do_not_use_for, re.I)
    assert re.search(r"HVE|hve|mdq|hve-dev", when)
    assert not re.search(r"generated app|non-HVE|他アプリ", when, re.I)
    assert not re.search(r"ignore|除外|使用しない", when, re.I)
    metadata = frontmatter.get("metadata")
    assert isinstance(metadata, dict)
    assert metadata.get("origin") == "user"
    assert re.fullmatch(r"\d+\.\d+\.\d+", str(metadata.get("version", "")))
    headings = tuple(heading for heading, _body in _h2_sections(skill))
    assert len(headings) == len(_SKILL_H2_HEADINGS)
    assert set(headings) == set(_SKILL_H2_HEADINGS)
    skill_body = _body(skill)
    # Coding Agents consume raw customization source, so HTML comments are not
    # semantically invisible and must not carry hidden or split instructions.
    assert "<!--" not in skill_body
    assert "-->" not in skill_body
    preamble, _sections = _parse_h2_sections(skill_body)
    assert _nonempty_lines(preamble) == ("# hve-requirement-traceability",)
    visible_rows = _visible_markdown_lines(routing)
    visible_routing = "\n".join(line for _line_number, line in visible_rows)
    assert visible_routing.count(_SKILL_REFERENCE) == 1
    matching_rows = [(line_number, line) for line_number, line in visible_rows if line == _ROUTING_ROW]
    assert len(matching_rows) == 1
    line_number, _line = matching_rows[0]
    physical_lines = routing.splitlines()
    assert line_number >= 2
    header = physical_lines[line_number - 2].rstrip()
    separator = physical_lines[line_number - 1].rstrip()
    assert header == "| フェーズ / トリガー | 参照 Skill | パス | 説明 |"
    assert re.fullmatch(r"\|(?:\s*:?-+:?\s*\|){4}", separator)


def test_skill_purpose_and_non_goals_are_fixed() -> None:
    skill = _read_required(_SKILL)
    assert _nonempty_lines(_section_exact(skill, "目的")) == _PURPOSE_LINES
    assert _nonempty_lines(
        _section_exact(skill, "Non-goals（このスキルの範囲外）")
    ) == _NON_GOAL_LINES


def test_skill_is_limited_to_hve_application_maintenance() -> None:
    skill = _read_required(_SKILL)
    scope = _section_exact(skill, "適用範囲")
    assert _nonempty_lines(scope) == _SCOPE_LINES


def test_skill_checks_inventory_requirement_and_mapping_before_editing() -> None:
    skill = _read_required(_SKILL)
    before_edit = _section_exact(skill, "編集前確認")
    assert _nonempty_lines(before_edit) == _BEFORE_EDIT_LINES


def test_skill_defines_bootstrap_before_implementation() -> None:
    skill = _read_required(_SKILL)
    bootstrap = _section_exact(skill, "新規要件 ID の bootstrap")
    assert _nonempty_lines(bootstrap) == _BOOTSTRAP_LINES


def test_skill_defines_cross_surface_reuse_check() -> None:
    skill = _read_required(_SKILL)
    section = _section_exact(skill, "面横断の再利用確認")
    assert _nonempty_lines(section) == _CROSS_SURFACE_LINES


def test_skill_defines_feature_tdd_order_and_na_boundaries() -> None:
    skill = _read_required(_SKILL)
    feature = _section_exact(skill, "feature の TDD 順序")
    assert _nonempty_lines(feature) == _FEATURE_LINES


def test_inventory_generator_collects_nonignored_untracked_files() -> None:
    generator = _read_required(_REPO_ROOT / _TDD_POLICY_GENERATOR)
    assert '["git", "ls-files", "--cached", "--others", "--exclude-standard"]' in generator


def test_skill_uses_bounded_mdq_retrieval_and_staged_expansion() -> None:
    skill = _read_required(_SKILL)
    retrieval = _section_exact(skill, "関連要件の選択取得")
    assert _nonempty_lines(retrieval) == _RETRIEVAL_LINES
    search_matches = re.findall(
        r"`(python\s+-m\s+mdq\s+search\b[^`]*)`",
        retrieval,
    )
    assert len(search_matches) == 1
    assert search_matches[0] in _RETRIEVAL_STEPS[0]
    command = shlex.split(search_matches[0])
    assert command == [
        "python",
        "-m",
        "mdq",
        "search",
        "--q",
        "<検索語>",
        "--paths",
        _REQUIREMENT_DEFINITION,
        "--top-k",
        "5",
        "--max-tokens",
        "800",
    ]
    for failure in ("索引欠損", "stale", "検索 CLI 障害"):
        assert failure in retrieval
    assert "特定済みの要件 ID" in retrieval or "特定済みの見出し" in retrieval
    assert "read / grep" in retrieval


def test_skill_limits_full_document_reads() -> None:
    skill = _read_required(_SKILL)
    full_read = _section_exact(skill, "全文取得の例外")
    assert _nonempty_lines(full_read) == _FULL_READ_LINES


def test_path_specific_instructions_are_narrow_and_delegate_to_skill() -> None:
    instructions = _read_required(_INSTRUCTIONS)
    frontmatter = _frontmatter_data(instructions)

    assert set(frontmatter) >= {"description", "applyTo"}
    description = frontmatter["description"]
    assert isinstance(description, str)
    assert description.strip()
    apply_to = frontmatter["applyTo"]
    assert isinstance(apply_to, str)
    actual_patterns = {part.strip() for part in apply_to.split(",") if part.strip()}
    expected_patterns = {part.strip() for part in _APPLY_TO.split(",")}
    assert actual_patterns == expected_patterns
    body_lines = _nonempty_lines(_body(instructions))
    assert body_lines == (
        "# HVE アプリケーション保守",
        f"- HVE コアパスの変更・不具合調査では `{_SKILL_REFERENCE}` を使用する。",
    )


def test_repository_wide_router_is_short_and_does_not_embed_requirements() -> None:
    instructions = _read_required(_COPILOT_INSTRUCTIONS)
    router = _section_exact(instructions, "§12 HVE アプリケーション保守ルーティング")

    nonempty_lines = list(_nonempty_lines(router))
    assert len(nonempty_lines) == 3
    assert all(line.startswith("- ") for line in nonempty_lines)
    traceability_headings = [
        heading
        for heading, _body in _h2_sections(instructions)
        if re.search(r"HVE|Hypervelocity Engineering", heading, re.I)
        and re.search(
            r"トレーサビリティ|要求|要件|保守|traceability|requirement|maintenance",
            heading,
            re.I,
        )
    ]
    assert len(traceability_headings) == 1
    assert "HVE アプリケーション保守ルーティング" in traceability_headings[0]
    assert nonempty_lines == [
        f"- HVE 対象変更・不具合調査では `{_SKILL_REFERENCE}` を使用する。",
        "- HVE コアパスでは `.github/instructions/hve-maintenance.instructions.md` も適用する。",
        "- `hve-dev/requirement-definition.md` 全文を既定の入力にしない。",
    ]
    assert not re.search(r"\b(?:FR-MAINT-0[1-4]|NFR-CTX-01)\b", router)
    assert not re.search(r"^#{3,}\s|^\|", router, re.MULTILINE)
    for detailed_term in (
        "active-or-described",
        "--top-k",
        "--max-tokens",
        "Requirement-IDs",
        "deprecated-or-removed",
    ):
        assert detailed_term not in router
    whole_file_without_router = instructions.replace(router, "", 1)
    router_outside_sources = (
        whole_file_without_router,
        re.sub(r"<!--.*?-->", "", whole_file_without_router, flags=re.DOTALL),
    )
    for source in router_outside_sources:
        assert not re.search(
            r"(?<![A-Za-z0-9-])(?:FR-MAINT-0[1-4]|NFR-CTX-01)(?![A-Za-z0-9-])",
            source,
        )
        assert source.count(_REQUIREMENT_DEFINITION) == 0
    for known_path in (
        _REQUIREMENT_MAPPING,
        _FEATURE_INVENTORY,
        _TEST_INVENTORY,
        _TDD_POLICY,
        _TDD_POLICY_GENERATOR,
        _SKILL_REFERENCE,
        ".github/instructions/hve-maintenance.instructions.md",
    ):
        assert all(source.count(known_path) == 0 for source in router_outside_sources)
    for detailed_term in (
        "active-or-described",
        "partial-or-not-supported",
        "--top-k",
        "--max-tokens",
        "Change-Type",
        "Change-Type-Reason",
        "Requirement-IDs",
        "Requirement-N/A-Reason",
        "Test-Paths",
        "Test-N/A-Reason",
        "TDD-Evidence",
        "Manual-Review-Required",
        "deprecated-or-removed",
        "親見出し",
        "隣接チャンク",
        "検索語を変えて最大 2 回",
        "要求書全文へ自動 fallback",
    ):
        assert all(detailed_term not in source for source in router_outside_sources)
    instruction_sources = (
        instructions,
        re.sub(r"<!--.*?-->", "", instructions, flags=re.DOTALL),
    )
    assert all(
        source.count("hve-requirement-traceability") == 1
        for source in instruction_sources
    )
