from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_COMPLETION_LOCAL = (
    _ROOT / ".github" / "prompts" / "runtime" / "template" / "completion-local.prompt.md"
)
_CODE_REVIEW_CLI = (
    _ROOT / ".github" / "prompts" / "runtime" / "review" / "code-review-cli.prompt.md"
)
_CODE_REVIEW_FIX = (
    _ROOT / ".github" / "prompts" / "runtime" / "review" / "code-review-agent-fix.prompt.md"
)
_COPILOT_INSTRUCTIONS = _ROOT / ".github" / "copilot-instructions.md"

_COMPLETION_SECTIONS = ["利用者の判断待ち", "実施内容", "検証結果", "未実施・blocked 理由"]
_CONTINUE_RULE = [
    "## 続行規則",
    "- 次の安全な操作が明確で、承認境界・停止規則に触れない場合は、利用者の判断待ちにせず続行する。",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_completion_report_blocked_first() -> None:
    content = _read(_COMPLETION_LOCAL)
    lines = content.splitlines()

    assert "{done_label}" in content
    structure_line = next(
        (line for line in lines if "completion-report.md" in line and "先頭から" in line),
        "",
    )
    assert structure_line
    positions = [structure_line.index(section) for section in _COMPLETION_SECTIONS]
    assert positions == sorted(positions)


def test_code_review_merge_blocking_findings_include_failure_evidence() -> None:
    content = _read(_CODE_REVIEW_CLI)

    assert content.count("{diff}") == 1
    # FR-CLI-97: 重大度で報告を絞らず、全件を重大度付きで報告させる
    assert "マージを止める問題だけを報告" not in content
    assert "出力しないでください" not in content
    assert "全件" in content
    for severity in ("Blocker", "Major", "Minor"):
        assert severity in content
    for required in ("ファイル", "行", "重大度", "理由", "どう失敗するか"):
        assert required in content
    # オーバーエンジニアリングは報告対象から外さない（リポジトリ共通の禁止事項）
    assert "要件にない汎用化・不要な抽象化" in content
    assert "Blocker として報告" in content
    # 合格判定は Blocker 件数だけで決め、harness の合格判定行の解釈を維持する
    assert "Blocker = 0 なら PASS" in content
    assert "合格判定: ✅ PASS または ❌ FAIL" in content


def test_code_review_fix_targets_only_blockers() -> None:
    content = _read(_CODE_REVIEW_FIX)

    assert content.count("{review_comments}") == 1
    assert "Blocker" in content
    assert "Major / Minor は修正しない" in content


def test_continue_rule_two_line_marker() -> None:
    lines = _read(_COPILOT_INSTRUCTIONS).splitlines()

    start = lines.index(_CONTINUE_RULE[0])
    section: list[str] = []
    for line in lines[start:]:
        if section and line.startswith("## "):
            break
        if line.strip():
            section.append(line)

    assert section == _CONTINUE_RULE
