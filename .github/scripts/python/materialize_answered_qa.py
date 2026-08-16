"""materialize_answered_qa.py — FR-QA-03 / FR-CLOUD-24 回答済み QA 生成

構造化質問票と手動回答テキストから回答済み Markdown を生成する。
hve.qa_merger を再利用し、外部依存なし。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from hve.qa_merger import QAMerger  # noqa: E402


@dataclass
class MaterializeResult:
    """回答済み QA 生成結果。"""

    filename: str
    content: str
    appendix: str


def _normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n")


def _quote_block(text: str) -> str:
    """原文を Markdown 引用へ変換し、QA 構造としての再パースを防ぐ。"""
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def _detect_duplicate_answer_numbers(answer_text: str) -> None:
    seen: Set[int] = set()
    for line in answer_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = re.match(r"^(\d+)\s*:", stripped)
        if m:
            no = int(m.group(1))
            if no in seen:
                raise ValueError(f"回答番号 {no} が重複しています")
            seen.add(no)


def _resolve_label_defaults(merged_doc) -> None:  # type: ignore[no-untyped-def]
    """単一ラベルのみの user_answer を選択肢テキストに展開する。"""
    for q in merged_doc.questions:
        if q.user_answer and q.choices:
            label = q.user_answer.strip()
            if len(label) == 1 and label.isalpha():
                matched = next(
                    (c for c in q.choices if c.label.upper() == label.upper()),
                    None,
                )
                if matched:
                    q.user_answer = f"{matched.label}) {matched.text}"


def materialize(
    questionnaire_md: str,
    answer_text: str,
    issue_number: int,
    *,
    use_defaults: bool = False,
) -> Optional[MaterializeResult]:
    """構造化質問票と回答テキストから回答済み Markdown を生成する。

    Returns:
        MaterializeResult または None（質問 0 件時）。

    Raises:
        ValueError: 入力不正・未回答かつ既定値なし等。
    """
    if isinstance(issue_number, bool) or not isinstance(issue_number, int):
        raise ValueError(f"issue_number は正の整数が必要です: {issue_number!r}")
    if issue_number < 1:
        raise ValueError(f"issue_number は正の整数が必要です: {issue_number}")

    questionnaire_md = _normalize_line_endings(questionnaire_md)
    answer_text = _normalize_line_endings(answer_text)

    doc = QAMerger.parse_qa_content(questionnaire_md)

    if not doc.questions:
        return None

    # 回答パース・検証
    if answer_text.strip():
        _detect_duplicate_answer_numbers(answer_text)
        answers: Dict[int, str] = QAMerger.parse_answers(answer_text)
    else:
        answers = {}

    valid_nos = {q.no for q in doc.questions}
    unknown = set(answers) - valid_nos
    if unknown:
        raise ValueError(f"未知の質問番号です: {sorted(unknown)}")

    for no, val in answers.items():
        q_match = next(q for q in doc.questions if q.no == no)
        if len(val) == 1 and val.isalpha() and q_match.choices:
            if not any(c.label.upper() == val.upper() for c in q_match.choices):
                raise ValueError(
                    f"Q{no:02d} の選択肢に {val} がありません"
                )

    merged = QAMerger.merge_answers(doc, answers, use_defaults=use_defaults)
    _resolve_label_defaults(merged)

    for q in merged.questions:
        if not q.user_answer:
            raise ValueError(
                f"Q{q.no:02d} に回答がなく、既定値候補もありません"
            )

    body = QAMerger.render_merged(merged)

    appendix_lines = [
        "## 付録: 原質問票",
        "",
        _quote_block(questionnaire_md.rstrip()),
        "",
        "## 付録: 回答コメント",
        "",
        _quote_block(answer_text.rstrip()),
        "",
    ]
    appendix = "\n".join(appendix_lines)

    content = body.rstrip("\n") + "\n\n" + appendix

    # 最終再パース検証
    reparsed = QAMerger.parse_qa_content(content)
    if len(reparsed.questions) != len(doc.questions):
        raise ValueError(
            f"再パース検証失敗: 質問数不一致 "
            f"({len(reparsed.questions)} != {len(doc.questions)})"
        )
    for q in reparsed.questions:
        if not q.user_answer:
            raise ValueError(
                f"再パース検証失敗: Q{q.no:02d} の user_answer が空です"
            )

    sha8 = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
    filename = f"Issue-{issue_number}-questionnaire-answered-{sha8}.md"

    return MaterializeResult(filename=filename, content=content, appendix=appendix)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli_main() -> None:
    parser = argparse.ArgumentParser(
        description="構造化質問票＋手動回答 → 回答済み Markdown 生成",
    )
    parser.add_argument("--questionnaire-file", required=True, help="質問票 Markdown")
    parser.add_argument("--answer-file", required=True, help="回答テキスト")
    parser.add_argument("--issue-number", type=int, required=True)
    parser.add_argument("--output-dir", required=True, help="出力ディレクトリ")
    parser.add_argument("--use-defaults", action="store_true")
    args = parser.parse_args()

    q_md = Path(args.questionnaire_file).read_text(encoding="utf-8-sig")
    a_txt = Path(args.answer_file).read_text(encoding="utf-8-sig")

    result = materialize(
        q_md, a_txt, args.issue_number, use_defaults=args.use_defaults
    )

    if result is None:
        print(json.dumps({"skipped": True}))
        sys.exit(0)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / result.filename
    if not QAMerger.save_merged(result.content, out_path):
        raise RuntimeError(f"回答済み QA を保存できませんでした: {out_path}")
    errors = QAMerger.validate_answered_file(
        out_path,
        expected_content=result.content,
        expected_questions=len(QAMerger.parse_qa_content(result.content).questions),
    )
    if errors:
        raise RuntimeError("回答済み QA の保存検証に失敗しました: " + " / ".join(errors))

    full_sha = hashlib.sha256(result.content.encode("utf-8")).hexdigest()
    print(json.dumps({"filename": result.filename, "path": str(out_path), "sha256": full_sha}))


if __name__ == "__main__":
    _cli_main()
