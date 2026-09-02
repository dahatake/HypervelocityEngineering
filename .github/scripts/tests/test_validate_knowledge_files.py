"""FR-WF-AKM-01 contracts for knowledge document validation."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[3]
_VALIDATOR = _REPO_ROOT / ".github" / "scripts" / "validate-knowledge-files.py"
_SPEC = importlib.util.spec_from_file_location("validate_knowledge_files", _VALIDATOR)
assert _SPEC is not None and _SPEC.loader is not None
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)

_MAIN = """# D01: 事業意図・成功条件定義書

**D クラス**: D01
**文書名**: 事業意図・成功条件定義書
**必須度**: Core
**総合状態**: ❓ Unknown
**Prompt投入可否**: No（Draft）
**関連 ADR / 未解決論点**: TBD

## 1. 目的と背景
text
## 2. 要求項目（Confirmed）
text
## 3. 要求項目（Tentative — 推論・仮定を含む）
text
## 4. 未確定事項（Unknown）
text
## 5. 最低内容カバー状況
text
## 6. 不足判定・推奨アクション
text
## 7. 状態サマリー
text
## 8. 関連文書
text
"""

_CHANGELOG = """<!-- sources: [] -->
<!-- generated_at: 2026-08-28T00:00:00Z -->
<!-- generator: KnowledgeManager -->

# D01 変更ログ: 事業意図・成功条件定義書

**対象ファイル**: `knowledge/D01-事業意図-成功条件定義書.md`
**カバー率（REQ単位）**: 0%
**最終更新**: 2026-08-28
**更新エージェント**: KnowledgeManager
**入力ソース**: なし

## 全体更新履歴
text
## 要求項目別ログ
text
## 付録 A: マッピング詳細（原文保全）
text
"""


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


def test_main_document_uses_main_schema_only(tmp_path: Path) -> None:
    path = _write(tmp_path / "D01-事業意図-成功条件定義書.md", _MAIN)
    assert mod.validate_file(path) == []


def test_changelog_uses_changelog_schema_only(tmp_path: Path) -> None:
    path = _write(tmp_path / "D01-事業意図-成功条件定義書-ChangeLog.md", _CHANGELOG)
    assert mod.validate_file(path) == []


@pytest.mark.parametrize(
    ("filename", "content", "missing"),
    (
        ("D01-main.md", _MAIN.replace("## 8. 関連文書", "## 関連文書"), "§8 関連文書"),
        (
            "D01-main-ChangeLog.md",
            _CHANGELOG.replace("## 付録 A: マッピング詳細（原文保全）", "## マッピング詳細"),
            "付録 A",
        ),
        (
            "D01-main-ChangeLog.md",
            _CHANGELOG.replace("<!-- sources: [] -->\n", ""),
            "sources",
        ),
        (
            "D01-main-ChangeLog.md",
            "# prefixed\n" + _CHANGELOG,
            "sources",
        ),
    ),
)
def test_each_schema_rejects_missing_required_content(
    tmp_path: Path, filename: str, content: str, missing: str
) -> None:
    errors = mod.validate_file(_write(tmp_path / filename, content))
    assert any(missing in error for error in errors)


def test_size_limit_applies_to_main_document_only(tmp_path: Path) -> None:
    oversized_main = _write(tmp_path / "D01-main.md", _MAIN + "x" * 20_000)
    oversized_log = _write(
        tmp_path / "D01-main-ChangeLog.md", _CHANGELOG + "x" * 20_000
    )
    assert any("[SIZE]" in error for error in mod.validate_file(oversized_main))
    assert not any("[SIZE]" in error for error in mod.validate_file(oversized_log))


def test_required_sections_must_follow_the_canonical_order(tmp_path: Path) -> None:
    out_of_order = _MAIN.replace(
        "## 6. 不足判定・推奨アクション\ntext\n## 7. 状態サマリー\ntext",
        "## 7. 状態サマリー\ntext\n## 6. 不足判定・推奨アクション\ntext",
    )
    errors = mod.validate_file(_write(tmp_path / "D01-main.md", out_of_order))
    assert any("より後に配置" in error for error in errors)


def test_main_and_changelog_must_exist_as_a_pair(tmp_path: Path) -> None:
    main = _write(tmp_path / "D01-main.md", _MAIN)
    changelog = tmp_path / "D01-main-ChangeLog.md"
    validate_pairs = getattr(mod, "validate_pairs", None)
    assert validate_pairs is not None
    assert validate_pairs([main])
    _write(changelog, _CHANGELOG)
    assert validate_pairs([main, changelog]) == []


def test_current_knowledge_documents_all_pass() -> None:
    paths = sorted((_REPO_ROOT / "knowledge").glob("D[0-9][0-9]-*.md"))
    assert len(paths) == 42
    assert sum(path.name.endswith("-ChangeLog.md") for path in paths) == 21
    assert all(mod.validate_file(path) == [] for path in paths)
    assert mod.validate_pairs(paths) == []
