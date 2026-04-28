"""artifact_validation.py — AQOD 成果物検証モジュール

AQOD 本体成果物（qa/QA-DocConsistency-*.md）の検証を行う。
HVE 実行補助 QA の execution-qa-merged.md は AQOD 本体成果物ではないため、
このモジュールの検証対象ではない。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional


# AQOD 成果物として認められるファイル名パターン
_AQOD_FILENAME_PATTERNS = [
    re.compile(r"QA-DocConsistency-Issue-\d+\.md$"),
    re.compile(r"QA-DocConsistency-\d{8}-\d{6}\.md$"),
    re.compile(r"QA-DocConsistency-.+\.md$"),
]

# AQOD 成果物の必須本文マーカー
_REQUIRED_HEADER = "# Original ドキュメント質問票"
_REQUIRED_SCOPE = "対象スコープ: original-docs/"
_REQUIRED_SUMMARY_SECTION = "## サマリー"

# 各質問の必須項目
_REQUIRED_QUESTION_FIELDS = [
    "対象ドキュメント",
    "該当箇所",
    "問題種別",
    "重大度",
    "質問内容",
]

# 内容系カテゴリ（少なくとも1件必要）
_CONTENT_CATEGORIES = [
    "矛盾",
    "不明瞭",
    "重大な欠落",
    "一貫性欠落",
    "データ整合性",
    "ベストプラクティス逸脱",
    "運用設計未定義",
]


def is_aqod_artifact_filename(path: "Path | str") -> bool:
    """ファイル名が AQOD 本体成果物の命名規則に合致するか判定する。"""
    name = Path(path).name
    return any(p.search(name) for p in _AQOD_FILENAME_PATTERNS)


def _looks_like_auto_qa_helper_content(content: str) -> bool:
    """AQOD 本体ではなく Auto-QA 補助質問票（[Q01]形式）らしい本文か判定する。"""
    has_bracket_q = re.search(r"^\[Q\d+\]\s*$", content, re.MULTILINE) is not None
    has_body_q = re.search(r"^### Q\d+", content, re.MULTILINE) is not None
    return has_bracket_q and not has_body_q


def is_aqod_helper_artifact(path: "Path | str") -> bool:
    """QA-DocConsistency 名の Auto-QA 補助成果物か判定する。

    旧実装では補助質問票が QA-DocConsistency-*.md で保存されることがあり、
    本体成果物検証で誤って FAIL 扱いされていたため、本文形式で分類する。
    """
    path = Path(path)
    if not is_aqod_artifact_filename(path) or not path.exists() or not path.is_file():
        return False
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return _looks_like_auto_qa_helper_content(content)


def validate_aqod_artifact(path: "Path | str") -> Dict[str, object]:
    """AQOD 本体成果物の検証を行い、結果 dict を返す。

    Returns:
        {
            "path": str,
            "passed": bool,
            "warnings": list[str],
            "errors": list[str],
        }
    """
    path = Path(path)
    result: Dict[str, object] = {
        "path": str(path),
        "passed": False,
        "skipped": False,
        "warnings": [],
        "errors": [],
    }
    warnings: List[str] = []
    errors: List[str] = []

    # ファイル名チェック
    if not is_aqod_artifact_filename(path):
        errors.append(
            f"ファイル名 '{path.name}' は AQOD 本体成果物の命名規則（QA-DocConsistency-*.md）に合致しません。"
        )

    # ファイル読み込み
    if not path.exists():
        errors.append(f"ファイルが存在しません: {path}")
        result["passed"] = False
        result["warnings"] = warnings
        result["errors"] = errors
        return result

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        errors.append(f"ファイルの読み込みに失敗しました: {e}")
        result["passed"] = False
        result["skipped"] = False
        result["warnings"] = warnings
        result["errors"] = errors
        return result

    if not errors and _looks_like_auto_qa_helper_content(content):
        warnings.append(
            "AQOD Auto-QA 補助質問票（[Qxx]形式）のため、AQOD 本体成果物検証をスキップします。"
        )
        result["passed"] = True
        result["skipped"] = True
        result["warnings"] = warnings
        result["errors"] = errors
        return result

    # 必須ヘッダーチェック
    if _REQUIRED_HEADER not in content:
        errors.append(
            f"必須ヘッダー '{_REQUIRED_HEADER}' が見つかりません。"
            " AQOD 本体成果物ではない可能性があります。"
        )

    # 対象スコープチェック
    if _REQUIRED_SCOPE not in content:
        warnings.append(
            f"'{_REQUIRED_SCOPE}' が見つかりません。"
            " AQOD 分析対象が original-docs/ であることの明示が推奨されます。"
        )

    # サマリーセクションチェック
    if _REQUIRED_SUMMARY_SECTION not in content:
        warnings.append(
            f"'{_REQUIRED_SUMMARY_SECTION}' セクションが見つかりません。"
        )

    # 質問件数チェック（### Q パターン）
    question_blocks = re.findall(r"^### Q\d+", content, re.MULTILINE)
    if not question_blocks:
        errors.append(
            "質問ブロック（### Q01 等）が1件も見つかりません。"
            " AQOD 本体成果物ではない可能性があります。"
        )
    else:
        # 必須項目チェック
        for field in _REQUIRED_QUESTION_FIELDS:
            if field not in content:
                errors.append(
                    f"必須項目 '{field}' が本文に含まれていません。"
                )

        # 内容系カテゴリチェック
        found_categories = [cat for cat in _CONTENT_CATEGORIES if cat in content]
        if not found_categories:
            errors.append(
                "内容系カテゴリ（矛盾/不明瞭/重大な欠落/一貫性欠落/データ整合性/ベストプラクティス逸脱/運用設計未定義）が"
                "1件も含まれていません。"
            )

    result["passed"] = len(errors) == 0
    result["warnings"] = warnings
    result["errors"] = errors
    return result


def find_aqod_artifacts(qa_dir: "Path | str" = "qa") -> List[Path]:
    """qa/ ディレクトリ内の AQOD 本体成果物ファイルを検索する。"""
    return [
        f for f in _find_aqod_artifact_candidates(qa_dir)
        if not is_aqod_helper_artifact(f)
    ]


def _find_aqod_artifact_candidates(qa_dir: "Path | str" = "qa") -> List[Path]:
    """qa/ ディレクトリ内の QA-DocConsistency-* 候補ファイルを検索する。"""
    qa_path = Path(qa_dir)
    if not qa_path.is_dir():
        return []
    return sorted(
        f for f in qa_path.iterdir()
        if f.is_file() and is_aqod_artifact_filename(f)
    )


def validate_aqod_run(
    qa_dir: "Path | str" = "qa",
    run_id: Optional[str] = None,
) -> Dict[str, object]:
    """AQOD 実行後の成果物検証を行い、サマリー dict を返す。

    AQOD 本体成果物（QA-DocConsistency-*.md）を対象とする。
    execution-qa-merged.md は HVE 実行補助 QA であり、AQOD 本体成果物ではない。

    Args:
        qa_dir: qa/ ディレクトリのパス
        run_id: 実行 ID（将来の拡張用、現在は未使用）

    Returns:
        {
            "artifacts_found": int,
            "passed": int,
            "failed": int,
            "validation_results": list[dict],
            "overall": "PASS" | "WARN" | "FAIL",
            "aqod_validation": bool,  # True = 少なくとも1件の有効な成果物あり
        }
    """
    artifacts = _find_aqod_artifact_candidates(qa_dir)
    validation_results = [validate_aqod_artifact(a) for a in artifacts]
    evaluated_results = [r for r in validation_results if not r.get("skipped")]
    skipped = len(validation_results) - len(evaluated_results)

    passed = sum(1 for r in evaluated_results if r["passed"])
    failed = len(evaluated_results) - passed

    if not evaluated_results:
        overall = "FAIL"
        aqod_validation = False
    elif passed > 0:
        overall = "PASS" if failed == 0 else "WARN"
        aqod_validation = True
    else:
        overall = "FAIL"
        aqod_validation = False

    return {
        "artifacts_found": len(evaluated_results),
        "candidate_artifacts_found": len(artifacts),
        "skipped": skipped,
        "passed": passed,
        "failed": failed,
        "validation_results": validation_results,
        "overall": overall,
        "aqod_validation": aqod_validation,
    }
