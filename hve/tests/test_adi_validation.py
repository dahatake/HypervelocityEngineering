"""test_adi_validation.py — ADI 成果物（Doc Card / トリアージカタログ）の検証テスト。

対応要件:
- FR-WF-ADI-09: Doc Card の front matter 必須キー
- FR-WF-ADI-10: トリアージ結果の `out` に理由を必須化
- FR-WF-ADI-11: `purpose` が空のとき `must` を付与しない

タスクプランでは T20 / T22 を別ファイルに分ける計画だったが、
2 つの検証関数は同一モジュール（`hve/artifact_validation.py`）に属し
fixture も共通のため 1 ファイルに統合した。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.abspath(_repo_root))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from hve.artifact_validation import (  # noqa: E402
    validate_design_doc_card,
    validate_design_doc_catalog,
    validate_downstream_seed_section,
)

_VALID_CARD = """---
doc_id: DOC-0009
slug: doc-0009-agelas10209
source_path: docs-original/AGELAS10209.md
source_sha256: 3f9a
converted_by: passthrough
d_classes: [D04, D08]
confidence: high
---

## 文脈

本書は在庫情報を取り込むバッチ処理の詳細設計である。
"""

_VALID_CATALOG = """# 設計書カタログ

- purpose: EC 倉庫の取り置き算出バッチを再構築する

## 採用（must）

| doc_id | 文書 | 判定理由 |
| --- | --- | --- |
| DOC-0028 | AGELAS30201 | 目的の対象処理そのもの |

## 対象外（out）

| doc_id | 文書 | 除外理由 |
| --- | --- | --- |
| DOC-0026 | AGELAS30101 | GCP 側の処理であり Azure 再構築の対象外 |
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Doc Card
# ---------------------------------------------------------------------------


def test_valid_card_has_no_errors(tmp_path: Path) -> None:
    assert validate_design_doc_card(_write(tmp_path, "card.md", _VALID_CARD)) == []


def test_missing_file_is_reported(tmp_path: Path) -> None:
    errors = validate_design_doc_card(tmp_path / "absent.md")
    assert errors and any("存在しません" in e for e in errors)


def test_missing_front_matter_is_reported(tmp_path: Path) -> None:
    errors = validate_design_doc_card(_write(tmp_path, "card.md", "## 文脈\n\n本文\n"))
    assert errors and any("front matter" in e for e in errors)


def test_missing_required_key_is_reported(tmp_path: Path) -> None:
    text = _VALID_CARD.replace("source_sha256: 3f9a\n", "")
    errors = validate_design_doc_card(_write(tmp_path, "card.md", text))
    assert any("source_sha256" in e for e in errors)


def test_invalid_confidence_is_reported(tmp_path: Path) -> None:
    text = _VALID_CARD.replace("confidence: high", "confidence: とても高い")
    errors = validate_design_doc_card(_write(tmp_path, "card.md", text))
    assert any("confidence" in e for e in errors)


def test_missing_context_section_is_reported(tmp_path: Path) -> None:
    text = _VALID_CARD.split("## 文脈")[0]
    errors = validate_design_doc_card(_write(tmp_path, "card.md", text))
    assert any("文脈" in e for e in errors)


# ---------------------------------------------------------------------------
# トリアージカタログ
# ---------------------------------------------------------------------------


def test_valid_catalog_has_no_errors(tmp_path: Path) -> None:
    assert validate_design_doc_catalog(_write(tmp_path, "catalog.md", _VALID_CATALOG)) == []


def test_catalog_missing_file_is_reported(tmp_path: Path) -> None:
    errors = validate_design_doc_catalog(tmp_path / "absent.md")
    assert errors and any("存在しません" in e for e in errors)


def test_out_row_without_reason_is_reported(tmp_path: Path) -> None:
    text = _VALID_CATALOG.replace(
        "| DOC-0026 | AGELAS30101 | GCP 側の処理であり Azure 再構築の対象外 |",
        "| DOC-0026 | AGELAS30101 |  |",
    )
    errors = validate_design_doc_catalog(_write(tmp_path, "catalog.md", text))
    assert any("DOC-0026" in e and "理由" in e for e in errors)


def test_missing_out_section_is_reported(tmp_path: Path) -> None:
    text = _VALID_CATALOG.split("## 対象外（out）")[0]
    errors = validate_design_doc_catalog(_write(tmp_path, "catalog.md", text))
    assert any("対象外" in e for e in errors)


def test_must_without_purpose_is_reported(tmp_path: Path) -> None:
    """FR-WF-ADI-11: purpose が空のとき must を付与してはならない。"""
    text = _VALID_CATALOG.replace(
        "- purpose: EC 倉庫の取り置き算出バッチを再構築する", "- purpose: "
    )
    errors = validate_design_doc_catalog(_write(tmp_path, "catalog.md", text))
    assert any("must" in e for e in errors)


def test_must_section_is_not_confused_with_should(tmp_path: Path) -> None:
    """「準採用（should）」が先にあっても must 判定を誤らない。"""
    text = (
        "# 設計書カタログ\n\n- purpose: \n\n"
        "## 準採用（should）\n\n"
        "| doc_id | 文書 | 理由 |\n| --- | --- | --- |\n"
        "| DOC-0002 | B | 代替可能 |\n\n"
        "## 採用（must）\n\nなし\n\n"
        "## 対象外（out）\n\n"
        "| doc_id | 文書 | 除外理由 |\n| --- | --- | --- |\n"
        "| DOC-0026 | C | 対象外の事業領域 |\n"
    )
    assert validate_design_doc_catalog(_write(tmp_path, "catalog.md", text)) == []


def test_empty_purpose_without_must_is_allowed(tmp_path: Path) -> None:
    text = (
        "# 設計書カタログ\n\n- purpose: \n\n"
        "## 採用（must）\n\nなし\n\n"
        "## 対象外（out）\n\n"
        "| doc_id | 文書 | 除外理由 |\n| --- | --- | --- |\n"
        "| DOC-0026 | AGELAS30101 | 対象外の事業領域 |\n"
    )
    assert validate_design_doc_catalog(_write(tmp_path, "catalog.md", text)) == []


# ---------------------------------------------------------------------------
# 下流成果物の候補セクション（FR-WF-ADI-13〜15）
# ---------------------------------------------------------------------------

_SEED_HEADING = "## 設計書由来の候補（ADI）"

_VALID_SEED = f"""# アプリケーションカタログ

| APP-ID | 名称 |
| --- | --- |
| APP-001 | 在庫管理 |

{_SEED_HEADING}

> 下流ワークフローが正式 ID を採番して本表へ統合する。ADI は ID を採番しない。

| 候補 | 根拠 | 出典 doc_id | 出典パス |
| --- | --- | --- | --- |
| EC 倉庫取り置き算出 | 取り置き必要数の算出処理が独立して記述されている | DOC-0028 | docs/original-design-doc-ingest/doc-0028-x/content.md |
"""


def test_valid_seed_section_has_no_errors(tmp_path: Path) -> None:
    path = _write(tmp_path, "app-catalog.md", _VALID_SEED)
    assert validate_downstream_seed_section(path) == []


def test_file_without_seed_section_is_allowed(tmp_path: Path) -> None:
    """候補が 1 件も無い成果物は正常。セクション自体が無くてもよい。"""
    text = "# アプリケーションカタログ\n\n| APP-ID | 名称 |\n| --- | --- |\n"
    assert validate_downstream_seed_section(_write(tmp_path, "app-catalog.md", text)) == []


def test_missing_file_is_reported(tmp_path: Path) -> None:
    errors = validate_downstream_seed_section(tmp_path / "absent.md")
    assert errors and "存在しません" in errors[0]


def test_row_without_doc_id_is_reported(tmp_path: Path) -> None:
    text = _VALID_SEED.replace("| DOC-0028 |", "|  |")
    errors = validate_downstream_seed_section(_write(tmp_path, "app-catalog.md", text))
    assert errors and any("出典" in e for e in errors)


def test_invalid_doc_id_format_is_reported(tmp_path: Path) -> None:
    text = _VALID_SEED.replace("DOC-0028", "設計書 28")
    errors = validate_downstream_seed_section(_write(tmp_path, "app-catalog.md", text))
    assert errors and any("出典" in e for e in errors)


def test_seed_section_with_no_rows_is_allowed(tmp_path: Path) -> None:
    """候補 0 件を「なし」と明記するのは許容する（無言の省略ではない）。"""
    text = f"# アプリケーションカタログ\n\n{_SEED_HEADING}\n\nなし\n"
    assert validate_downstream_seed_section(_write(tmp_path, "app-catalog.md", text)) == []


def test_numbered_id_in_candidate_column_is_reported(tmp_path: Path) -> None:
    """ID 採番は下流の責務。ADI が APP-/UC-/SVC- を振ってはならない。"""
    text = _VALID_SEED.replace("| EC 倉庫取り置き算出 |", "| APP-042 EC 倉庫取り置き算出 |")
    errors = validate_downstream_seed_section(_write(tmp_path, "app-catalog.md", text))
    assert errors and any("採番" in e for e in errors)


# ---------------------------------------------------------------------------
# 原本質問票（FR-WF-ADI-17 / 18）
# ---------------------------------------------------------------------------

_VALID_QUESTIONNAIRE = """# Original ドキュメント質問票

対象スコープ: docs-original/

## サマリー

- 総質問数: 1

### Q01. 入力仕様の確認
- **対象ドキュメント**: `docs-original/spec.md`
- **該当箇所**: > 入力値を受け取る
- **問題種別**: 不明瞭
- **重大度**: major
- **質問内容**: 入力値の許容範囲は何ですか。
- **回答欄**:
"""

_VALID_EMPTY_QUESTIONNAIRE = """# Original ドキュメント質問票

対象スコープ: docs-original/

## サマリー

- 総質問数: 0
- 質問なし
"""


def test_questionnaire_filenames_are_recognized() -> None:
    from hve.artifact_validation import is_original_docs_questionnaire_filename

    assert is_original_docs_questionnaire_filename("D01-original-docs-questionnaire.md")
    assert is_original_docs_questionnaire_filename("original-docs-cross-questionnaire.md")
    assert is_original_docs_questionnaire_filename("QA-DocConsistency-Issue-123.md")
    assert not is_original_docs_questionnaire_filename("run-1-execution-qa-merged.md")


def test_questionnaire_with_questions_is_valid(tmp_path: Path) -> None:
    from hve.artifact_validation import validate_original_docs_questionnaire_artifact

    result = validate_original_docs_questionnaire_artifact(
        _write(tmp_path, "D01-original-docs-questionnaire.md", _VALID_QUESTIONNAIRE)
    )
    assert result["passed"] is True
    assert "aq" + "od" not in str(result).lower()


def test_explicit_zero_questionnaire_is_valid(tmp_path: Path) -> None:
    from hve.artifact_validation import validate_original_docs_questionnaire_artifact

    result = validate_original_docs_questionnaire_artifact(
        _write(tmp_path, "D01-original-docs-questionnaire.md", _VALID_EMPTY_QUESTIONNAIRE)
    )
    assert result["passed"] is True


def test_silent_zero_questionnaire_is_invalid(tmp_path: Path) -> None:
    from hve.artifact_validation import validate_original_docs_questionnaire_artifact

    silent = _VALID_EMPTY_QUESTIONNAIRE.replace("- 総質問数: 0\n- 質問なし\n", "")
    result = validate_original_docs_questionnaire_artifact(
        _write(tmp_path, "D01-original-docs-questionnaire.md", silent)
    )
    assert result["passed"] is False


def test_questionnaire_run_detects_step_outputs(tmp_path: Path) -> None:
    from hve.artifact_validation import validate_original_docs_questionnaire_run

    _write(tmp_path, "D01-original-docs-questionnaire.md", _VALID_EMPTY_QUESTIONNAIRE)
    _write(tmp_path, "original-docs-cross-questionnaire.md", _VALID_EMPTY_QUESTIONNAIRE)
    result = validate_original_docs_questionnaire_run(qa_dir=tmp_path)
    assert result["overall"] == "PASS"
    assert result["artifacts_found"] == 2
    assert "aq" + "od" not in result
