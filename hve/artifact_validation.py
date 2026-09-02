"""artifact_validation.py — 原本質問票成果物検証モジュール

原本質問票成果物（`qa/D01`〜`D21` / 横断 join / 単独 Agent fallback）の
検証を行う。HVE 実行補助 QA の `execution-qa-merged.md` は対象外とする。
"""

from __future__ import annotations

import ast
import base64
import glob
import hashlib
import json
import re
import shlex
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from urllib.parse import urlparse


# 原本質問票成果物として認められるファイル名パターン
_ORIGINAL_DOCS_QUESTIONNAIRE_FILENAME_PATTERNS = [
    re.compile(r"D(?:0[1-9]|1\d|2[0-1])-original-docs-questionnaire\.md$"),
    re.compile(r"original-docs-cross-questionnaire\.md$"),
    re.compile(r"QA-DocConsistency-Issue-\d+\.md$"),
    re.compile(r"QA-DocConsistency-\d{8}-\d{6}\.md$"),
    re.compile(r"QA-DocConsistency-.+\.md$"),
]

# 原本質問票成果物の必須本文マーカー
_REQUIRED_HEADER = "# Original ドキュメント質問票"
_REQUIRED_SCOPE = "対象スコープ: docs-original/"
_REQUIRED_SUMMARY_SECTION = "## サマリー"
_ZERO_QUESTION_SUMMARY_PATTERN = re.compile(r"総質問数\s*:\s*0\b")
_ZERO_QUESTION_MARKER = "質問なし"

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


def find_missing_output_paths(
    repo_root: "Path | str",
    declared_paths: Iterable[str],
    prefix_gates: Iterable[str] = (),
) -> List[str]:
    """宣言された成果物の欠落を副作用なしで返す。

    確定 path はそのまま、prefix gate は前方一致する file / directory が無い
    場合だけ末尾 ``*`` 付きで返す。入力順と欠落表示は Runner の既存契約を
    維持し、filesystem や入力 iterable は変更しない。
    """
    root = Path(repo_root)
    missing = [path for path in declared_paths if not (root / path).exists()]
    for prefix in prefix_gates:
        target = root / prefix
        parent = target.parent
        if parent.is_dir() and any(parent.glob(f"{glob.escape(target.name)}*")):
            continue
        missing.append(f"{prefix}*")
    return missing


def is_original_docs_questionnaire_filename(path: "Path | str") -> bool:
    """ファイル名が原本質問票成果物の命名規則に合致するか判定する。"""
    name = Path(path).name
    return any(p.search(name) for p in _ORIGINAL_DOCS_QUESTIONNAIRE_FILENAME_PATTERNS)


def _looks_like_auto_qa_helper_content(content: str) -> bool:
    """本体ではなく Auto-QA 補助質問票（[Q01]形式）らしい本文か判定する。"""
    has_bracket_q = re.search(r"^\[Q\d+\]\s*$", content, re.MULTILINE) is not None
    has_body_q = re.search(r"^### Q\d+", content, re.MULTILINE) is not None
    return has_bracket_q and not has_body_q


def _has_explicit_zero_questions(summary_section: str | None) -> bool:
    """質問 0 件を summary 内で明示しているか判定する。"""
    if not summary_section:
        return False
    return bool(
        _ZERO_QUESTION_SUMMARY_PATTERN.search(summary_section)
        and _ZERO_QUESTION_MARKER in summary_section
    )


# ---------------------------------------------------------------------------
# ADI（Auto Design-doc Ingestion）成果物の検証
# ---------------------------------------------------------------------------

# Doc Card の front matter 必須キー（FR-WF-ADI-09）
_DESIGN_DOC_CARD_REQUIRED_KEYS = (
    "doc_id",
    "source_path",
    "source_sha256",
    "d_classes",
    "confidence",
)
_DESIGN_DOC_CONFIDENCE_VALUES = frozenset({"high", "medium", "low"})


def _parse_front_matter(text: str) -> "Dict[str, str] | None":
    """先頭の ``---`` 区切り YAML front matter を ``key: value`` の辞書として返す。

    ネストや複数行値は扱わない（Doc Card はフラットな key-value のみを持つ）。
    front matter が無い場合は None。
    """
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    try:
        end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return None
    result: Dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        result[key.strip()] = value.strip()
    return result


def _section_body(text: str, heading_marker: str) -> "str | None":
    """``## …<heading_marker>…`` 見出しの本文を返す。見つからない場合は None。

    marker には `must` / `out` のような一意な英字ラベルを渡すこと。
    和文の部分一致（例: 「採用」）は「準採用」にも当たるため使わない。
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and heading_marker in line:
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    return "\n".join(lines[start:end])


def _table_rows(section: str) -> List[List[str]]:
    """Markdown テーブルのデータ行（ヘッダ・区切り行を除く）をセル配列で返す。"""
    rows: List[List[str]] = []
    seen_header = False
    for line in section.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        if re.match(r"^\|\s*[-:\s|]+\s*\|?$", s):
            seen_header = True
            continue
        if not seen_header:
            continue
        rows.append([c.strip() for c in s.strip("|").split("|")])
    return rows


def validate_design_doc_card(path: "Path | str") -> List[str]:
    """ADI Step 2 が生成する Doc Card を検証する（FR-WF-ADI-09）。"""
    p = Path(path)
    if not p.is_file():
        return [f"Doc Card が存在しません: {p}"]

    text = p.read_text(encoding="utf-8")
    front_matter = _parse_front_matter(text)
    if front_matter is None:
        return [f"{p}: YAML front matter が見つかりません"]

    errors: List[str] = []
    for key in _DESIGN_DOC_CARD_REQUIRED_KEYS:
        if key not in front_matter:
            errors.append(f"{p}: front matter に必須キー '{key}' がありません")

    confidence = front_matter.get("confidence")
    if confidence is not None and confidence not in _DESIGN_DOC_CONFIDENCE_VALUES:
        errors.append(
            f"{p}: confidence の値が不正です: '{confidence}'（high / medium / low のいずれか）"
        )

    if _section_body(text, "文脈") is None:
        errors.append(f"{p}: '## 文脈' セクションがありません")

    return errors


def validate_design_doc_catalog(path: "Path | str") -> List[str]:
    """ADI Step 3 が生成するトリアージカタログを検証する。

    - `out` 判定の各行に除外理由があること（FR-WF-ADI-10）
    - `purpose` が空のとき `must` を付与していないこと（FR-WF-ADI-11）
    """
    p = Path(path)
    if not p.is_file():
        return [f"設計書カタログが存在しません: {p}"]

    text = p.read_text(encoding="utf-8")
    errors: List[str] = []

    # `\s*` は改行も食うため、値の抽出は水平空白のみに限定する（空値を空行の次行と誤認しない）。
    purpose_match = re.search(r"^-[ \t]*purpose:[ \t]*(.*)$", text, re.MULTILINE)
    purpose = (purpose_match.group(1).strip() if purpose_match else "")

    must_section = _section_body(text, "must")
    must_rows = _table_rows(must_section) if must_section else []
    if not purpose and must_rows:
        errors.append(
            f"{p}: purpose が空のため must を付与できません"
            f"（{len(must_rows)} 行。should / may / out のいずれかへ変更してください）"
        )

    out_section = _section_body(text, "out")
    if out_section is None:
        errors.append(f"{p}: '## 対象外（out）' セクションがありません")
    else:
        for row in _table_rows(out_section):
            if not row:
                continue
            if not row[-1]:
                errors.append(f"{p}: out 判定 '{row[0]}' に除外理由がありません")

    return errors


# 下流成果物へ ADI が追記する候補セクションの見出しマーカー。
# `_section_body` は一意な ASCII ラベルでの一致を前提とするため "ADI" を使う。
_SEED_SECTION_MARKER = "ADI"
_SEED_DOC_ID_PATTERN = re.compile(r"^DOC-\d{4}$")
# 下流ワークフローが採番する識別子。ADI がこれらを振ってはならない。
_DOWNSTREAM_ID_PATTERN = re.compile(r"\b(?:APP|UC|SVC|SCR|JOB)-\d+", re.IGNORECASE)


def validate_downstream_seed_section(path: "Path | str") -> List[str]:
    """ADI Step 5.x が下流成果物へ追記する候補セクションを検証する。

    - 候補行に `DOC-NNNN` 形式の出典があること（FR-WF-ADI-14）
    - 候補列に下流の採番 ID が含まれないこと（FR-WF-ADI-15）

    候補セクションが無いファイル、および候補 0 件の「なし」記載は正常とみなす。
    """
    p = Path(path)
    if not p.is_file():
        return [f"下流成果物が存在しません: {p}"]

    section = _section_body(p.read_text(encoding="utf-8"), _SEED_SECTION_MARKER)
    if section is None:
        return []

    errors: List[str] = []
    for row in _table_rows(section):
        if not row or not any(row):
            continue
        candidate = row[0]
        doc_ids = [c for c in row if _SEED_DOC_ID_PATTERN.match(c)]
        if not doc_ids:
            errors.append(f"{p}: 候補 '{candidate}' に出典 doc_id（DOC-NNNN）がありません")
        if _DOWNSTREAM_ID_PATTERN.search(candidate):
            errors.append(
                f"{p}: 候補 '{candidate}' に採番済み ID が含まれます"
                "（ID の採番は下流ワークフローの責務）"
            )
    return errors


def validate_original_docs_questionnaire_artifact(path: "Path | str") -> Dict[str, object]:
    """原本質問票成果物の検証を行い、結果 dict を返す。

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
    if not is_original_docs_questionnaire_filename(path):
        errors.append(
            f"ファイル名 '{path.name}' は原本質問票成果物の命名規則に合致しません。"
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
            "Auto-QA 補助質問票（[Qxx]形式）のため、原本質問票本体の検証をスキップします。"
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
            " 原本質問票本体ではない可能性があります。"
        )

    # 対象スコープチェック
    if _REQUIRED_SCOPE not in content:
        warnings.append(
            f"'{_REQUIRED_SCOPE}' が見つかりません。"
            " 原本分析対象が docs-original/ であることの明示が推奨されます。"
        )

    # サマリーセクションチェック
    if _REQUIRED_SUMMARY_SECTION not in content:
        warnings.append(
            f"'{_REQUIRED_SUMMARY_SECTION}' セクションが見つかりません。"
        )
    summary_section = _section_body(content, "サマリー")
    has_explicit_zero_questions = _has_explicit_zero_questions(summary_section)

    # 質問件数チェック（### Q パターン）
    question_blocks = re.findall(r"^### Q\d+", content, re.MULTILINE)
    if not question_blocks:
        if not has_explicit_zero_questions:
            errors.append(
                "質問ブロック（### Q01 等）が1件も見つかりません。"
                " 質問 0 件の場合はサマリーに『総質問数: 0』と『質問なし』の両方を明記してください。"
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


def _find_original_docs_questionnaire_candidates(qa_dir: "Path | str" = "qa") -> List[Path]:
    """qa/ ディレクトリ内の原本質問票候補ファイルを検索する。"""
    qa_path = Path(qa_dir)
    if not qa_path.is_dir():
        return []
    return sorted(
        f for f in qa_path.iterdir()
        if f.is_file() and is_original_docs_questionnaire_filename(f)
    )


def validate_original_docs_questionnaire_run(
    qa_dir: "Path | str" = "qa",
    run_id: Optional[str] = None,
) -> Dict[str, object]:
    """原本質問票実行後の成果物検証を行い、サマリー dict を返す。

    D01〜D21 fan-out、横断 join、単独 Agent fallback を対象とする。
    execution-qa-merged.md は HVE 実行補助 QA であり、本体成果物ではない。

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
            "original_docs_questionnaire_validation": bool,
        }
    """
    artifacts = _find_original_docs_questionnaire_candidates(qa_dir)
    validation_results = [validate_original_docs_questionnaire_artifact(a) for a in artifacts]
    evaluated_results = [r for r in validation_results if not r.get("skipped")]
    skipped = len(validation_results) - len(evaluated_results)

    passed = sum(1 for r in evaluated_results if r["passed"])
    failed = len(evaluated_results) - passed

    if not evaluated_results:
        overall = "FAIL"
        original_docs_questionnaire_validation = False
    elif passed > 0:
        overall = "PASS" if failed == 0 else "WARN"
        original_docs_questionnaire_validation = True
    else:
        overall = "FAIL"
        original_docs_questionnaire_validation = False

    return {
        "artifacts_found": len(evaluated_results),
        "candidate_artifacts_found": len(artifacts),
        "skipped": skipped,
        "passed": passed,
        "failed": failed,
        "validation_results": validation_results,
        "overall": overall,
        "original_docs_questionnaire_validation": original_docs_questionnaire_validation,
    }

# ---------------------------------------------------------------------------
# Deploy 系 Agent 向け AC 検証 gate (T4)
# ---------------------------------------------------------------------------
# 対象 Agent の `ac-verification.md` を読み、実在系 AC（リソース存在/deploy成功/
# verify GREEN 系）が ❌ または ⏳/NEEDS-VERIFICATION のままになっていないかを
# 検査する。Orchestrator (hve/runner.py) が Step 完了直前に呼び出し、エラー
# 文字列が空でなければ Step を fail に降格させる。
#
# allowlist は Deploy 系 Agent 6 本を対象とする。
# - Dev-Microservice-Azure-ComputeDeploy-AzureFunctions: AC-3, AC-9
# - Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps: AC-1, AC-6, AC-8
# - Dev-Microservice-Azure-AddServiceDeploy: AC-1
# - Dev-Microservice-Azure-AgenticRetrievalDeploy: AC4B-1, AC4B-14, AC4B-15, AC4B-18
# - Dev-Microservice-Azure-AgentDeploy: AC-1, AC-2, AC-3 + Provider Pre-flight
# - Dev-Microservice-Azure-DataDeploy: AC-1
#
# `ac-verification.md` は 1 行 1 AC のテーブル行で記録される前提
# （対応 prompt に「table 形式必須」を明記済み）。

_DEPLOY_AGENT_REALITY_AC: Dict[str, List[str]] = {
    "Dev-Microservice-Azure-ComputeDeploy-AzureFunctions": ["AC-3", "AC-9"],
    "Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps": ["AC-1", "AC-6", "AC-8"],
    "Dev-Microservice-Azure-AddServiceDeploy": ["AC-1"],
    "Dev-Microservice-Azure-AgenticRetrievalDeploy": [
        "AC4B-1",
        # 設計値と live knowledge base 設定の一致、および実 retrieve での
        # Knowledge Source 横断を実在で判定する。
        "AC4B-14",
        "AC4B-15",
        "AC4B-18",
    ],
    "Dev-Microservice-Azure-AgentDeploy": ["AC-1", "AC-2", "AC-3"],
    "Dev-Microservice-Azure-DataDeploy": ["AC-1"],
}


def is_deploy_step(
    custom_agent: Optional[str],
    reality_gate_acs: Optional[List[str]] = None,
) -> bool:
    """Step が Deploy 系（実在系 AC を強制する Azure デプロイ Agent）か判定する。

    ``runner._run_deploy_ac_gate`` も本関数を使用する（判定ロジックの単一の源）:
    ``StepDef.reality_gate_acs`` の宣言があるか、``custom_agent`` が後方互換辞書
    ``_DEPLOY_AGENT_REALITY_AC`` のメンバーであれば Deploy 系とみなす。
    ``Dev-Microservice-Azure-ComputePostDeployTest`` 等の Deploy 後テスト Agent は
    辞書に含まれないため False を返す。

    Args:
        custom_agent: ``StepDef.custom_agent``（コンテナ等は None）。
        reality_gate_acs: ``StepDef.reality_gate_acs``（宣言があれば優先）。

    Returns:
        Deploy 系なら True。
    """
    if reality_gate_acs:
        return True
    return bool(custom_agent) and custom_agent in _DEPLOY_AGENT_REALITY_AC


def wave_has_deploy_step(steps: Iterable[Any]) -> bool:
    """wave に Deploy 系 Step が 1 つでも含まれれば True。

    各要素は ``custom_agent`` / ``reality_gate_acs`` 属性を持つ Step 様
    オブジェクト（StepDef / fan-out 子）。案 P の Deploy 境界 commit/push
    判定に使う。
    """
    return any(
        is_deploy_step(
            getattr(s, "custom_agent", None),
            getattr(s, "reality_gate_acs", None),
        )
        for s in steps
    )


def _extract_first_az_container_create_command(text: str) -> str:
    """Extract the first logical `az container create` command from shell text.

    The validator needs to inspect flags on the command itself, not comments in
    the surrounding PostgreSQL section.  This helper follows simple bash line
    continuations (trailing backslash) which matches the generated scripts.
    """
    lines = text.splitlines()
    start_index = -1
    start_offset = 0
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        offset = line.find("az container create")
        if offset != -1:
            start_index = index
            start_offset = offset
            break
    if start_index == -1:
        return ""

    logical_lines: List[str] = []
    for line in lines[start_index:]:
        if not logical_lines:
            logical_lines.append(line[start_offset:].strip())
        else:
            logical_lines.append(line.strip())
        if not line.rstrip().endswith("\\"):
            break
    return "\n".join(logical_lines)


def _extract_shell_logical_commands(text: str) -> List[str]:
    r"""コメント行を除外し、bash の継続行を論理コマンドへ結合する。

    ASDW が生成する Azure CLI スクリプトの静的契約確認に限定した最小実装で、
    shell 全体を解析する parser ではない。末尾 ``\`` に加え、生成される
    ``aci_command="..."`` のような複数行 quoted assignment だけを扱う。
    """
    commands: List[str] = []
    current = ""
    quote = ""
    escaped = False
    separator = ""
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not current and (not stripped or stripped.startswith("#")):
            continue
        continuing_quoted_value = bool(current and quote)
        continued = raw_line.rstrip().endswith("\\")
        if continuing_quoted_value:
            segment = raw_line.rstrip()
        else:
            segment = stripped
        if continued:
            segment = segment[:-1].rstrip()
        current += separator + segment
        for char in segment:
            if escaped:
                escaped = False
                continue
            if char == "\\" and quote != "'":
                escaped = True
                continue
            if quote:
                if char == quote:
                    quote = ""
                continue
            if char in ("'", '"'):
                quote = char
        if continued:
            separator = " "
        elif quote:
            separator = "\n"
        else:
            commands.append(current)
            current = ""
            separator = ""
            escaped = False
    if current:
        commands.append(current)
    return commands


def _strip_shell_inline_comment(command: str) -> str:
    """Strip one unquoted inline shell comment from a logical command.

    This deliberately handles only single/double quotes and backslash escapes,
    which is sufficient for generated Azure CLI lines. Payload strings remain
    intact because their ``#`` characters are inside the outer shell quotes.
    """
    quote = ""
    escaped = False
    for index, char in enumerate(command):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote != "'":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in ("'", '"'):
            quote = char
            continue
        if char == "#" and (
            index == 0 or command[index - 1].isspace() or command[index - 1] in ";|&()"
        ):
            return command[:index].rstrip()
    return command


_FOUNDRY_ADOPTION_MARKER = "Microsoft Foundry (Foundry Agent Service)"
_AZ_COMMAND_PREFIX = (
    r"(?:^|\b(?:if|elif|then)\s+|=\s*[\"']?\$\(\s*)(?:!\s*)?"
)
_FOUNDRY_PROJECT_SHOW_RE = re.compile(
    _AZ_COMMAND_PREFIX + r"az\s+cognitiveservices\s+account\s+project\s+show\b"
)
_FOUNDRY_PROJECT_CREATE_RE = re.compile(
    _AZ_COMMAND_PREFIX + r"az\s+cognitiveservices\s+account\s+project\s+create\b"
)
_LEGACY_AI_PROJECT_RE = re.compile(
    _AZ_COMMAND_PREFIX + r"az\s+ai\s+project\b"
)


def validate_asdw_foundry_deploy_artifacts(
    design_doc_path: "Path | str",
    services_dir: "Path | str",
    verify_script_path: "Path | str",
) -> List[str]:
    """ASDW Step.2.2 の Foundry Project 生成契約を静的検証する。

    Design が Foundry を採用していない場合は no-op。採用時のみ、create 側で
    Project の show -> create -> show が実行コマンドとして存在し、verify 側が
    read-only の project show を持つことを確認する。
    """
    design_path = Path(design_doc_path)
    if not design_path.is_file():
        return [f"Foundry design document not found: {design_path}"]
    try:
        design_text = design_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"Foundry design document read error: {exc}"]
    if _FOUNDRY_ADOPTION_MARKER not in design_text:
        return []

    errors: List[str] = []
    service_root = Path(services_dir)
    service_scripts = sorted(service_root.glob("*.sh")) if service_root.is_dir() else []
    if not service_scripts:
        errors.append(f"Foundry service scripts not found under: {service_root}")
    create_commands: List[str] = []
    for script in service_scripts:
        try:
            create_commands.extend(
                _extract_shell_logical_commands(
                    script.read_text(encoding="utf-8", errors="replace")
                )
            )
        except OSError as exc:
            errors.append(f"Foundry service script read error ({script}): {exc}")

    if any(_LEGACY_AI_PROJECT_RE.search(command) for command in create_commands):
        errors.append("Foundry service scripts must not use legacy `az ai project` commands")
    show_count = sum(
        1 for command in create_commands if _FOUNDRY_PROJECT_SHOW_RE.search(command)
    )
    create_count = sum(
        1 for command in create_commands if _FOUNDRY_PROJECT_CREATE_RE.search(command)
    )
    if show_count < 2:
        errors.append(
            "Foundry service scripts must execute project show before and after create"
        )
    if create_count < 1:
        errors.append("Foundry service scripts must execute project create when absent")

    verify_path = Path(verify_script_path)
    if not verify_path.is_file():
        errors.append(f"Foundry verify script not found: {verify_path}")
        return errors
    try:
        verify_commands = _extract_shell_logical_commands(
            verify_path.read_text(encoding="utf-8", errors="replace")
        )
    except OSError as exc:
        errors.append(f"Foundry verify script read error: {exc}")
        return errors

    if any(_LEGACY_AI_PROJECT_RE.search(command) for command in verify_commands):
        errors.append("Foundry verify script must not use legacy `az ai project` commands")
    if not any(_FOUNDRY_PROJECT_SHOW_RE.search(command) for command in verify_commands):
        errors.append("Foundry verify script must execute project show")
    if any(_FOUNDRY_PROJECT_CREATE_RE.search(command) for command in verify_commands):
        errors.append("Foundry verify script must be read-only and must not create projects")
    return errors


def _extract_shell_function(text: str, function_name: str) -> str:
    """単純な bash 関数ブロックを、次の関数定義直前まで抽出する。

    `verify-data-resources.sh` の生成パターン（`name() { ... }`）に限定した
    静的検査用の最小実装。汎用 bash parser ではない。
    """
    lines = text.splitlines()
    target = re.compile(
        rf"^\s*(?:function\s+)?{re.escape(function_name)}\s*(?:\(\))?\s*\{{"
    )
    any_function = re.compile(
        r"^\s*(?:function\s+)?[A-Za-z_][A-Za-z0-9_]*\s*(?:\(\))?\s*\{"
    )
    start = -1
    for index, line in enumerate(lines):
        if target.match(line):
            start = index
            break
    if start == -1:
        return ""

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if any_function.match(lines[index]):
            end = index
            break
    return "\n".join(lines[start:end])


def _has_az_tsv_wrapper(text: str) -> bool:
    """`az_tsv` が `az "$@" -o tsv` の薄い wrapper として定義されているか判定する。"""
    block = _extract_shell_function(text, "az_tsv")
    return bool(block and re.search(r"\baz\s+\"\$@\"", block) and "-o tsv" in block)


def _has_postgresql_flexible_show(text: str) -> bool:
    """PostgreSQL Flexible Server の show 呼び出しが存在するか判定する。"""
    if "az postgres flexible-server show" in text:
        return True
    return _has_az_tsv_wrapper(text) and "az_tsv postgres flexible-server show" in text


def _extract_postgresql_section(text: str) -> str:
    """PostgreSQL 検証ブロックだけを抽出する。

    既存の `section "PostgreSQL Flexible Server` 形式に加え、今回の生成物で
    使われた `verify_postgres()` 関数形式を扱う。抽出不能時は空文字を返し、
    ファイル全体の Cosmos/Storage/Synapse `provisioningState` を PostgreSQL
    違反として誤検出しない。
    """
    pg_start = text.find('section "PostgreSQL Flexible Server')
    if pg_start != -1:
        pg_end = text.find('section "Cosmos DB', pg_start)
        if pg_end == -1:
            pg_end = text.find("# -----------------------------------------------------------------------------", pg_start + 1)
        return text[pg_start:pg_end if pg_end != -1 else len(text)]

    function_block = _extract_shell_function(text, "verify_postgres")
    if function_block:
        return function_block

    positions = [
        pos for pos in (
            text.find("az postgres flexible-server show"),
            text.find("az_tsv postgres flexible-server show") if _has_az_tsv_wrapper(text) else -1,
        )
        if pos != -1
    ]
    if not positions:
        return ""
    pg_start = min(positions)
    pg_start = text.rfind("\n", 0, pg_start) + 1
    pg_end = text.find('section "Cosmos DB', pg_start)
    if pg_end == -1:
        pg_end = text.find("# -----------------------------------------------------------------------------", pg_start + 1)
    return text[pg_start:pg_end if pg_end != -1 else len(text)]


def _design_requires_postgresql(
    design_doc_path: "Path | str | None",
    design_doc_text: Optional[str] = None,
) -> bool:
    """設計ドキュメント（azure-services-data.md）が PostgreSQL Flexible Server を
    「選定サービス（Chosen Azure service）」として採用しているか判定する。

    エンティティ選定テーブルの「Chosen Azure service」列だけを対象とし、
    「Alternatives（代替案）」列に PostgreSQL が登場するだけのケースは False を
    返す。DataDesign はデータストアを要件に応じて動的に選定するため、
    PostgreSQL 検証を要求してよいのは実際に選定された場合に限る。

    ドキュメントを読めない / テーブルを特定できない場合は False（PostgreSQL 検証を
    強制しない）を返し、偽陽性を避ける。スクリプト側に PostgreSQL ブロックが
    実在する場合の正当性検査は呼び出し側が別途行う。
    """
    if design_doc_path is None:
        return False
    doc_path = Path(design_doc_path)
    if design_doc_text is None:
        try:
            if not doc_path.exists():
                return False
            text = doc_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
    else:
        text = design_doc_text

    chosen_idx = -1
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if chosen_idx == -1:
            for idx, cell in enumerate(cells):
                if "Chosen Azure service" in cell:
                    chosen_idx = idx
                    break
            continue
        if 0 <= chosen_idx < len(cells) and re.search(
            r"PostgreSQL", cells[chosen_idx], re.IGNORECASE
        ):
            return True
    return False


_ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST = "sql-ledger-digest"
_ASDW_AUDIT_MODE_ACL_DIRECT = "acl-direct"
_ASDW_AUDIT_SQL_LEDGER_DIGEST_CANONICAL = (
    "Azure SQL Database の append-only ledger table（SVC-12 の監査証拠 SoT）+ "
    "Azure confidential ledger（信頼済み database digest 保管先、条件付き）"
)
_ASDW_AUDIT_ACL_DIRECT_CANONICAL = (
    "Azure confidential ledger（AuditRecord を直接格納）"
)
_ASDW_SQL_AUDIT_REGISTRATION_SOURCE = '''from contextlib import ExitStack, closing
from mssql_python import connect
import json, os, re

resources = ExitStack()
try:
    svc12_connection = resources.enter_context(closing(connect("Server=$SQL_HOST;Database=$SQL_DB_SVC12;UID=$DATA_DEPLOY_IDENTITY_CLIENT_ID;Authentication=ActiveDirectoryMSI;Encrypt=yes;TrustServerCertificate=no")))
    svc12_cursor = resources.enter_context(closing(svc12_connection.cursor()))
    audit_table = os.environ["SQL_AUDIT_TABLE"]
    next(filter(None, [re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", audit_table)]))
    audit = json.loads(os.environ["AUDIT_RECORD_JSON"])
    next(filter(None, [isinstance(audit, dict)]))
    next(filter(None, [isinstance(audit["auditEventId"], str)]))
    audit_id = audit["auditEventId"].strip()
    next(filter(None, [audit_id]))
    next(filter(None, [audit["auditEventId"] == audit_id]))
    payload = json.dumps(audit, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    svc12_cursor.execute(f"IF NOT EXISTS (SELECT 1 FROM [dbo].[{audit_table}] WITH (UPDLOCK, HOLDLOCK) WHERE id = ?) BEGIN INSERT INTO [dbo].[{audit_table}] (id, payload) VALUES (?, ?); END; SELECT COUNT_BIG(*), COALESCE(SUM(CASE WHEN payload = ? THEN 1 ELSE 0 END), 0) FROM [dbo].[{audit_table}] WITH (HOLDLOCK) WHERE id = ?;", (audit_id, audit_id, payload, payload, audit_id))
    stored_summary = svc12_cursor.fetchone()
    next(filter(None, [stored_summary == (1, 1)]))
    svc12_connection.commit()
    print("HVE_AUDIT_REGISTRATION_OK")
finally:
    resources.close()
'''
_ASDW_ACL_AUDIT_REGISTRATION_SOURCE = '''from collections.abc import Mapping
from contextlib import ExitStack, closing
from itertools import islice
from azure.confidentialledger import ConfidentialLedgerClient
from azure.identity import DefaultAzureCredential
from tempfile import TemporaryDirectory
import json, os

client_id = "$DATA_DEPLOY_IDENTITY_CLIENT_ID"
resources = ExitStack()
try:
    ledger_certificate_directory = resources.enter_context(TemporaryDirectory())
    ledger_certificate_path = ledger_certificate_directory + "/ledger_certificate.pem"
    credential = resources.enter_context(closing(DefaultAzureCredential(managed_identity_client_id=client_id)))
    ledger_client = resources.enter_context(closing(ConfidentialLedgerClient(endpoint=os.environ["CONFIDENTIAL_LEDGER_ENDPOINT"], credential=credential, ledger_certificate_path=ledger_certificate_path)))
    audit = json.loads(os.environ["AUDIT_RECORD_JSON"])
    next(filter(None, [isinstance(audit, dict)]))
    next(filter(None, [isinstance(audit["auditEventId"], str)]))
    audit_id = audit["auditEventId"].strip()
    next(filter(None, [audit_id]))
    next(filter(None, [audit["auditEventId"] == audit_id]))
    collection = os.environ["CONFIDENTIAL_LEDGER_COLLECTION"]
    payload = json.dumps(audit, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    raw_entries = list(islice(ledger_client.list_ledger_entries(collection_id=collection), 1001))
    next(filter(None, [len(raw_entries) <= 1000]))
    next(filter(None, [all(isinstance(entry, Mapping) and isinstance(entry.get("contents"), str) for entry in raw_entries)]))
    decoded_entries = [json.loads(entry["contents"]) for entry in raw_entries]
    next(filter(None, [all(isinstance(entry, dict) for entry in decoded_entries)]))
    matching_payloads = [entry["contents"] for entry, decoded in zip(raw_entries, decoded_entries) if decoded.get("auditEventId") == audit_id]
    next(filter(None, [len(matching_payloads) <= 1]))
    if matching_payloads:
        next(filter(None, [matching_payloads[0] == payload]))
    else:
        ledger_client.begin_create_ledger_entry({"contents": payload}, collection_id=collection).result()
    print("HVE_AUDIT_REGISTRATION_OK")
finally:
    resources.close()
'''
_ASDW_DATA_DESIGN_HEADERS = (
    "Entity",
    "Data characteristics（構造/更新頻度/サイズ）",
    "Access patterns（主要クエリ/ホットパス）",
    "Consistency（強/最終/要件根拠）",
    "Chosen Azure service（正式名称）",
    "Partition/Key/Index（要点）",
    "Rationale（3〜6行）",
    "Alternatives（最大2つ）",
    "Evidence（根拠リンク）",
)
def _normalize_asdw_design_cell(value: str) -> str:
    """ASDW設計表の1セルを限定的な比較用テキストへ正規化する。"""
    without_markdown = value.strip()
    decoration_patterns = (
        r"(?<!\*)\*\*([^*`]+)\*\*(?!\*)",
        r"(?<!`)`([^*`]+)`(?!`)",
        r"(?<!\*)\*([^*`]+)\*(?!\*)",
    )
    for pattern in decoration_patterns:
        without_markdown = re.sub(pattern, r"\1", without_markdown)
    normalized = without_markdown.strip()
    if normalized.endswith(("。", ".")):
        normalized = normalized[:-1].rstrip()
    return normalized


def _normalize_asdw_entity_cell(value: str) -> Optional[str]:
    """Entityセルの平文またはbalancedな単一装飾だけを受理する。"""
    stripped = value.strip()
    for pattern in (r"(?P<value>[^*`]+)", r"\*\*(?P<value>[^*`]+)\*\*", r"`(?P<value>[^*`]+)`"):
        match = re.fullmatch(pattern, stripped)
        if match:
            return match.group("value").strip()
    return None


def _asdw_markdown_indent_width(line: str) -> int:
    """Markdown行頭のspace/tabを表示列へ換算する。"""
    width = 0
    for character in line:
        if character == " ":
            width += 1
        elif character == "\t":
            width += 4 - (width % 4)
        else:
            break
    return width


def _asdw_fence_opening(line: str) -> Optional[Tuple[str, int]]:
    """Parse one CommonMark-style fenced-code opener used by HVE reports."""
    opening = re.fullmatch(
        r" {0,3}(?P<marker>`{3,}|~{3,})(?P<info>[^\r\n]*)",
        line,
    )
    if opening is None:
        return None
    marker = opening.group("marker")
    info = opening.group("info")
    if marker[0] == "`" and "`" in info:
        return None
    return marker[0], len(marker)


def _asdw_raw_html_block_start(line: str) -> bool:
    """Return whether a visible line starts a raw HTML block candidate."""
    return re.match(
        r"^ {0,3}<(?:/?[A-Za-z][A-Za-z0-9-]*(?=[\s/>]|$)|"
        r"![A-Za-z]|!\[CDATA\[|\?)",
        line,
        re.IGNORECASE,
    ) is not None


def _visible_asdw_design_lines(text: str) -> Tuple[List[str], Optional[str]]:
    """HTML comment・fence・indented codeを除き、raw HTMLは拒否する。"""
    visible: List[str] = []
    in_comment = False
    fence_character = ""
    fence_length = 0

    for raw_line in text.splitlines():
        if fence_character:
            closing = re.fullmatch(
                rf" {{0,3}}{re.escape(fence_character)}"
                rf"{{{fence_length},}}[ \t]*",
                raw_line,
            )
            if closing:
                fence_character = ""
                fence_length = 0
            continue

        line = raw_line
        started_inside_hidden_region = in_comment
        retained = ""
        discard_line = False
        while True:
            if in_comment:
                comment_end = line.find("-->")
                if comment_end == -1:
                    line = ""
                    break
                in_comment = False
                line = line[comment_end + 3 :]
                continue

            candidate = retained + line
            if not retained.strip():
                if _asdw_raw_html_block_start(candidate):
                    return [], (
                        "AuditRecord storage mode design document contains a "
                        "raw HTML block, which is not permitted."
                    )

                opening = _asdw_fence_opening(candidate)
                if opening is not None:
                    fence_character, fence_length = opening
                    retained = ""
                    discard_line = True
                    line = ""
                    break

            comment_start = line.find("<!--")
            if comment_start == -1:
                retained += line
                line = ""
                break
            retained += line[:comment_start]
            comment_end = line.find("-->", comment_start + 4)
            if comment_end == -1:
                line = ""
                in_comment = True
                break
            line = line[comment_end + 3 :]
        if discard_line:
            continue
        if started_inside_hidden_region:
            continue
        line = retained
        if not line and in_comment:
            continue
        if _asdw_markdown_indent_width(line) >= 4:
            continue
        visible.append(line)

    if in_comment:
        return [], "AuditRecord storage mode design document has an unclosed HTML comment."
    if fence_character:
        return [], "AuditRecord storage mode design document has an unclosed fenced block."
    return visible, None


def _split_asdw_pipe_row(line: str) -> Optional[List[str]]:
    """固定DataDesign表の両端pipe付き1行だけをcellへ分割する。"""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    body = stripped[1:-1]
    if body.startswith("|") or body.endswith("|"):
        return None
    return [cell.strip() for cell in body.split("|")]


def _looks_like_asdw_table_separator(line: str) -> bool:
    """両端pipe省略も含むMarkdown table separatorか判定する。"""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    cells = [cell.strip() for cell in stripped.split("|")]
    return len(cells) >= 2 and all(
        re.fullmatch(r":?-{3,}:?", cell) for cell in cells
    )


def _resolve_asdw_audit_storage_mode(
    design_doc_path: "Path | str | None",
    design_doc_text: Optional[str] = None,
) -> Tuple[Optional[str], List[str]]:
    """AuditRecordのChosen列から既知2方式のどちらかを解決する。

    汎用Markdown parserではなく、DataDesignの固定出力スキーマに限定する。
    Alternativesや後続の整合性戦略表は参照しない。
    """
    if design_doc_path is None:
        return None, [
            "AuditRecord storage mode requires the Azure data design document."
        ]
    design_path = Path(design_doc_path)
    if design_doc_text is None:
        if not design_path.is_file():
            return None, [f"AuditRecord storage mode design document not found: {design_path}"]
        try:
            text = design_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return None, [f"AuditRecord storage mode design document read error: {exc}"]
    else:
        text = design_doc_text

    lines, visibility_error = _visible_asdw_design_lines(text)
    if visibility_error:
        return None, [visibility_error]

    heading = re.compile(r"^##\s+1\.\s+エンティティ別ストア選定\s*$")
    heading_indexes = [
        index for index, line in enumerate(lines) if heading.match(line.strip())
    ]
    if len(heading_indexes) != 1:
        return None, [
            "AuditRecord storage mode requires exactly one "
            "`## 1. エンティティ別ストア選定` section."
        ]

    section_start = heading_indexes[0] + 1
    section_end = len(lines)
    for index in range(section_start, len(lines)):
        if re.match(r"^##\s+", lines[index].strip()):
            section_end = index
            break

    first_content = section_start
    while first_content < section_end and not lines[first_content].strip():
        first_content += 1
    if first_content >= section_end or not lines[first_content].strip().startswith("|"):
        return None, [
            "AuditRecord storage mode requires the entity selection table "
            "immediately after its section heading."
        ]
    table_lines: List[str] = []
    cursor = first_content
    while cursor < section_end and _split_asdw_pipe_row(lines[cursor]) is not None:
        table_lines.append(lines[cursor].strip())
        cursor += 1
    remaining = lines[cursor:section_end]
    has_additional_table = any(
        "|" in remaining[index - 1]
        and _looks_like_asdw_table_separator(remaining[index])
        for index in range(1, len(remaining))
    )
    if any("|" in line for line in remaining if line.strip()) or has_additional_table:
        return None, [
            "AuditRecord storage mode requires exactly one Markdown table "
            "under the entity selection section."
        ]
    if len(table_lines) < 3:
        return None, [
            "AuditRecord storage mode entity selection table requires a header, "
            "separator, and data row."
        ]

    rows = [_split_asdw_pipe_row(row) for row in table_lines]
    if any(row is None for row in rows):
        return None, [
            "AuditRecord storage mode entity selection table uses an invalid pipe boundary."
        ]
    typed_rows = [row for row in rows if row is not None]
    header = typed_rows[0]
    if header != list(_ASDW_DATA_DESIGN_HEADERS):
        return None, [
            "AuditRecord storage mode entity selection table header must match "
            "the fixed nine-column DataDesign schema, including exactly one "
            "`Entity` and `Chosen Azure service` column."
        ]
    if any(len(row) != len(_ASDW_DATA_DESIGN_HEADERS) for row in typed_rows):
        return None, [
            "AuditRecord storage mode entity selection table must use exactly nine columns."
        ]
    if not all(
        re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in typed_rows[1]
    ):
        return None, [
            "AuditRecord storage mode entity selection table separator is invalid."
        ]

    entity_index = _ASDW_DATA_DESIGN_HEADERS.index("Entity")
    chosen_index = _ASDW_DATA_DESIGN_HEADERS.index(
        "Chosen Azure service（正式名称）"
    )
    audit_rows = [
        row
        for row in typed_rows[2:]
        if _normalize_asdw_entity_cell(row[entity_index]) == "AuditRecord"
    ]
    if len(audit_rows) != 1:
        return None, [
            "AuditRecord storage mode requires exactly one `AuditRecord` entity row."
        ]

    chosen = _normalize_asdw_design_cell(audit_rows[0][chosen_index])
    if chosen == _ASDW_AUDIT_SQL_LEDGER_DIGEST_CANONICAL:
        return _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST, []
    if chosen == _ASDW_AUDIT_ACL_DIRECT_CANONICAL:
        return _ASDW_AUDIT_MODE_ACL_DIRECT, []
    return None, [
        "AuditRecord Chosen Azure service uses an unknown storage mode."
    ]


_ASDW_PRIVATE_ENV_KEYS = (
    "DATA_VNET_NAME",
    "DATA_PRIVATE_ENDPOINT_SUBNET_ID",
    "DATA_ACI_SUBNET_ID",
    "DATA_NAT_GATEWAY_NAME",
    "DATA_DEPLOY_IDENTITY_ID",
    "DATA_DEPLOY_IDENTITY_CLIENT_ID",
    "SQL_PRIVATE_ENDPOINT_NAME",
    "COSMOS_PRIVATE_ENDPOINT_NAME",
    "SQL_PRIVATE_DNS_ZONE",
    "COSMOS_PRIVATE_DNS_ZONE",
    "DATA_VERIFY_ACI_IMAGE",
    "DATA_VERIFY_RUN_ID",
)


def _shell_variable_pattern(name: str) -> str:
    """Return a regex fragment for ``$NAME`` or ``${NAME...}`` references."""
    escaped = re.escape(name)
    return rf"\$(?:{escaped}\b|\{{{escaped}(?::[^}}]*)?\}})"


def _extract_shell_case_branch(text: str, selector: str, branch: str) -> str:
    """Extract one plain branch from a generated bash ``case`` statement.

    This is intentionally a narrow static parser for the generated
    ``case "$DATA_NETWORK_MODE" in`` shape.  It rejects quoted prose and
    comment-only lookalikes instead of attempting to parse arbitrary shell.
    """
    lines = text.splitlines()
    selector_pattern = re.compile(_shell_variable_pattern(selector))
    case_start = -1
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.match(r"^\s*case\b.*\bin\s*(?:#.*)?$", line) and selector_pattern.search(line):
            case_start = index
            break
    if case_start == -1:
        return ""

    branch_pattern = re.compile(
        rf"^\s*[\"']?{re.escape(branch)}[\"']?\s*\)(?P<body>.*)$"
    )
    branch_start = -1
    branch_lines: List[str] = []
    for index in range(case_start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("#"):
            continue
        match = branch_pattern.match(lines[index])
        if match:
            branch_start = index
            inline_body = match.group("body")
            if ";;" in inline_body:
                branch_lines.append(inline_body.split(";;", 1)[0])
                return "\n".join(branch_lines)
            branch_lines.append(inline_body)
            break
        if re.match(r"^\s*esac\b", lines[index]):
            return ""
    if branch_start == -1:
        return ""

    for line in lines[branch_start + 1:]:
        if re.match(r"^\s*esac\b", line):
            return ""
        if ";;" in line:
            branch_lines.append(line.split(";;", 1)[0])
            return "\n".join(branch_lines)
        branch_lines.append(line)
    return ""


def _find_az_commands(text: str, command_group: str) -> List[str]:
    """Find executable Azure CLI commands, excluding comments and echo prose."""
    command_pattern = re.compile(
        rf"(?:^|[;&|]\s*|\(\s*|\b(?:if|elif|then|do)\s+)"
        rf"(?:timeout\s+600\s+)?(?:command\s+)?az\s+{re.escape(command_group)}\b"
    )
    commands: List[str] = []
    for raw_command in _extract_shell_logical_commands(text):
        command = _strip_shell_inline_comment(raw_command)
        if command_pattern.search(command):
            commands.append(command)
    return commands


def _cleanup_body_has_only_expected_delete(body: str) -> bool:
    """Require the generated conditional, resource-scoped cleanup delete.

    ``aci_created`` is set only after create succeeds. The guarded cleanup
    avoids deleting an existing colliding ACI on create failure, while ``||
    true`` preserves the primary failure status if Azure cleanup itself fails.
    """
    normalized = "\n".join(
        _strip_shell_inline_comment(line).strip()
        for line in body.splitlines()
        if _strip_shell_inline_comment(line).strip()
    )
    return re.fullmatch(
        r'if \[\[ "\$aci_created" == "1" \]\]; then\n'
        r'aci_owner="\$\(az[ \t]+container[ \t]+show[ \t]+'
        r'--resource-group[ \t]+"\$RESOURCE_GROUP"[ \t]+'
        r'--name[ \t]+"\$aci_name"[ \t]+--query[ \t]+'
        r'"tags\.hveVerifyRunId"[ \t]+--output[ \t]+tsv[ \t]+'
        r'2>/dev/null[ \t]+\|\|[ \t]+true\)"\n'
        r'if \[\[ "\$aci_owner" == "\$DATA_VERIFY_RUN_ID" \]\]; then\n'
        r'az[ \t]+container[ \t]+delete[ \t]+'
        r'--resource-group[ \t]+"\$RESOURCE_GROUP"[ \t]+'
        r'--name[ \t]+"\$aci_name"[ \t]+--yes[ \t]+\|\|[ \t]+true\nfi\nfi',
        normalized,
    ) is not None

def _private_branch_has_disallowed_function_or_nested_az(text: str) -> bool:
    """Enforce the generated private branch's direct Azure CLI sequence.

    The verifier grammar allows only ``cleanup_aci`` as a function. Required
    Azure CLI commands must be direct case-branch statements, not hidden in
    functions or conditional/loop bodies. This is intentionally narrower than
    a general shell parser.
    """
    function_def = re.compile(
        r"^\s*(?:function\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?:\(\))?\s*\{"
    )
    control_start = re.compile(r"^\s*(?:if|for|while|until|case)\b")
    control_end = re.compile(r"^\s*(?:fi|done|esac)\b")
    az_command = re.compile(r"\b(?:command\s+)?az\b")
    depth = 0
    in_cleanup = False
    for raw_line in text.splitlines():
        line = _strip_shell_inline_comment(raw_line)
        stripped = line.strip()
        if not stripped:
            continue
        function_match = function_def.match(line)
        if function_match:
            if function_match.group("name") != "cleanup_aci":
                return True
            in_cleanup = "}" not in line[function_match.end():]
            continue
        if in_cleanup:
            if "}" in stripped:
                in_cleanup = False
            continue
        if control_start.match(line):
            if az_command.search(line):
                if re.fullmatch(
                    r'\s*if az container show --resource-group "\$RESOURCE_GROUP" '
                    r'--name "\$aci_name" --only-show-errors; then\s*',
                    line,
                ) is None:
                    return True
            depth += 1
            continue
        if depth > 0 and az_command.search(line):
            return True
        if control_end.match(line):
            depth = max(0, depth - 1)
    return False


def _command_option_references_variable(command: str, option: str, name: str) -> bool:
    """Return whether an option value references the required shell variable."""
    return re.search(
        rf"{re.escape(option)}(?:\s+|=)[\"']?{_shell_variable_pattern(name)}",
        command,
    ) is not None


def _shell_reference_pattern(name: str) -> str:
    """Return a shell variable pattern that tolerates surrounding quotes."""
    return rf"[\"']?{_shell_variable_pattern(name)}[\"']?"


def _has_reference_comparison(text: str, left: str, right: str) -> bool:
    """Return whether two narrow shell references are compared on one line."""
    operator = r"(?:==|!=|=)"
    return bool(
        re.search(rf"{left}[ \t]*{operator}[ \t]*{right}", text)
        or re.search(rf"{right}[ \t]*{operator}[ \t]*{left}", text)
    )


def _count_shell_variable_comparisons(text: str, name: str) -> int:
    """Count equality/inequality checks that consume one contract variable."""
    reference = _shell_reference_pattern(name)
    operator = r"(?:==|!=|=)"
    return len(re.findall(rf"{reference}[ \t]*{operator}", text)) + len(
        re.findall(rf"{operator}[ \t]*{reference}", text)
    )


def _find_executable_az_command_offset(text: str, command_group: str) -> Optional[int]:
    """Return the first non-comment ``az <command_group>`` character offset."""
    command = re.compile(rf"\baz\s+{re.escape(command_group)}\b")
    offset = 0
    for line in text.splitlines(keepends=True):
        if not line.lstrip().startswith("#"):
            match = command.search(line)
            if match:
                return offset + match.start()
        offset += len(line)
    return None


def _find_first_executable_az_command_offset(text: str) -> Optional[int]:
    """Return the first non-comment direct Azure CLI command offset."""
    command = re.compile(
        r"(?:^|[;&|]\s*|\(\s*|\b(?:if|elif|then|do)\s+)"
        r"[ \t]*(?:(?:[A-Za-z_][A-Za-z0-9_]*=\S+|env|timeout\s+600|command)\s+)*"
        r"(?P<az>az)\b"
    )
    offset = 0
    for line in text.splitlines(keepends=True):
        if not line.lstrip().startswith("#"):
            match = command.search(line)
            if match:
                return offset + match.start("az")
        offset += len(line)
    return None


def _find_assigned_az_command(
    text: str,
    command_group: str,
    required_variables: Tuple[str, ...],
    query_fragment: str = "",
) -> Optional[Tuple[str, str]]:
    """Find one ``name=$(az ...)`` command tied to its required inputs.

    The helper intentionally recognizes only the simple command-substitution
    form generated by the ASDW private verifier. It is not a general shell
    parser.
    """
    assignment = re.compile(
        r"^\s*(?:local\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)=[\"']?\$\("
    )
    command = re.compile(rf"\baz\s+{re.escape(command_group)}\b")
    for raw_command in _extract_shell_logical_commands(text):
        logical_command = _strip_shell_inline_comment(raw_command)
        match = assignment.match(logical_command)
        if match is None or command.search(logical_command) is None:
            continue
        if query_fragment and query_fragment not in logical_command:
            continue
        if all(
            re.search(_shell_variable_pattern(variable), logical_command)
            for variable in required_variables
        ):
            return match.group("name"), logical_command
    return None


def _has_shell_result_literal_check(text: str, name: str, literal: str) -> bool:
    """Return whether a shell result variable is checked against one literal."""
    reference = rf"[\"']?\${re.escape(name)}\b[\"']?"
    expected = rf"[\"']?{re.escape(literal)}[\"']?"
    return bool(
        re.search(rf"{reference}[ \t]*(?:==|!=|=)[ \t]*{expected}", text)
        or re.search(rf"{expected}[ \t]*(?:==|!=|=)[ \t]*{reference}", text)
    )


def _has_shell_result_nonempty_check(text: str, name: str) -> bool:
    """Return whether a shell result variable is checked for an empty value."""
    reference = rf"[\"']?\${re.escape(name)}\b[\"']?"
    return bool(re.search(rf"(?:-z|-n)[ \t]+{reference}", text))


def _is_unreassigned_shell_result(
    text: str,
    name: str,
    expected_variable: str,
) -> bool:
    """Require one result assignment before its comparison with an env value."""
    assignment = re.compile(rf"^\s*(?:local\s+)?{re.escape(name)}\s*=", re.MULTILINE)
    matches = list(assignment.finditer(text))
    if len(matches) != 1:
        return False
    tail = text[matches[0].end():]
    return _has_reference_comparison(
        tail,
        rf"[\"']?\${re.escape(name)}\b[\"']?",
        _shell_reference_pattern(expected_variable),
    )


def _contains_shell_command_token(text: str, *names: str) -> bool:
    """Detect a narrow executable shell command token, including ``cmd\"\"``.

    Adjacent empty quotes are valid shell token concatenation. Normalizing only
    those pairs lets the validator reject an evasive direct command without
    interpreting arbitrary shell syntax or matching an ``echo`` argument.
    """
    token = "|".join(re.escape(name) for name in names)
    prefix = (
        r"(?:^|[;&|][ \t]*|\$\([ \t]*|"
        r"\b(?:if|elif|then|do)[ \t]+)(?:command[ \t]+)?"
    )
    for command in _extract_shell_logical_commands(text):
        normalized = command.replace('\"\"', "").replace("''", "")
        if re.search(rf"{prefix}(?:{token})\b", normalized):
            return True
    return False


def _extract_shell_assignment_value(text: str, name: str) -> str:
    """Extract one simple shell assignment value with ``\\`` continuations.

    This intentionally supports only the generated ``name=value`` form. It
    avoids treating later setup lines or inline comments as ACI payload code.
    """
    assignment = re.compile(
        rf"^\s*(?:local\s+)?{re.escape(name)}\s*=(?P<value>.*)$"
    )
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = assignment.match(line)
        if match is None:
            continue
        values = [match.group("value")]
        cursor = index
        while lines[cursor].rstrip().endswith("\\") and cursor + 1 < len(lines):
            cursor += 1
            values.append(lines[cursor].strip())
        return "\n".join(values)
    return ""


def _is_generated_shell_assignment(command: str, name: str) -> bool:
    """Return whether one logical command starts a generated assignment."""
    return re.match(
        rf"^\s*(?:local\s+)?{re.escape(name)}\s*=", command
    ) is not None


def _split_generated_quoted_assignment(
    command: str, name: str
) -> Optional[Tuple[str, str]]:
    """Split one narrow generated quoted assignment word from its tail.

    This recognizes only the generated ACI payload's quoted assignment word
    after simple line-continuation joining. It permits adjacent quote segments
    around a shell variable expansion, but deliberately does not parse general
    shell syntax. Its sole purpose is to keep text after that assignment word
    subject to host-side safety checks.
    """
    header = re.match(
        rf"^\s*(?:local\s+)?{re.escape(name)}\s*=", command
    )
    if header is None or header.end() >= len(command):
        return None
    value_start = header.end()
    if command[value_start] not in ("'", '"'):
        return None

    quote = ""
    escaped = False
    for index in range(value_start, len(command)):
        char = command[index]
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote != "'":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in ("'", '"'):
            quote = char
            continue
        if char.isspace() or char in ";|&":
            tail = _strip_shell_inline_comment(command[index:]).strip()
            return command[value_start:index], "" if tail == ";" else tail
    if quote:
        return None
    return command[value_start:], ""


def _command_outside_generated_assignment(command: str, name: str) -> str:
    """Return host-side content, omitting only a pure generated assignment."""
    if not _is_generated_shell_assignment(command, name):
        return command
    assignment = _split_generated_quoted_assignment(command, name)
    if assignment is None:
        return command
    return assignment[1]


def _has_disallowed_generated_assignment_evaluation(assignment_word: str) -> bool:
    """Reject host-evaluated syntax from the generated ACI payload assignment.

    The generated grammar permits only simple ``$NAME`` and ``${NAME}``
    expansions. Command/process substitutions and indirect expansions run or
    resolve on the verifier host before the ACI exists, so they are forbidden.
    This is deliberately a narrow assignment-word check rather than a general
    shell parser.
    """
    if re.search(r"`|[<>]\(", assignment_word):
        return True

    index = 0
    while index < len(assignment_word):
        char = assignment_word[index]
        if char == "\\":
            index += 2
            continue
        if char != "$":
            index += 1
            continue
        if index + 1 >= len(assignment_word):
            return True
        next_char = assignment_word[index + 1]
        if next_char == "(":
            return True
        if next_char == "{":
            closing = assignment_word.find("}", index + 2)
            if closing == -1 or re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*", assignment_word[index + 2:closing]
            ) is None:
                return True
            index = closing + 1
            continue
        if re.match(r"[A-Za-z_]", next_char):
            index += 2
            while index < len(assignment_word) and re.match(
                r"[A-Za-z0-9_]", assignment_word[index]
            ):
                index += 1
            continue
        return True
    return False


_PRIVATE_HOST_AZ_COMMAND = re.compile(
    r"(?:^|[;&|][ \t]*|\$\([ \t]*|\([ \t]*|"
    r"\b(?:if|elif|then|do)[ \t]+)(?:timeout[ \t]+600[ \t]+)?(?P<az>az)\b"
)
_PRIVATE_HOST_AZ_TOKEN = re.compile(r"(?<![-A-Za-z0-9_])az(?![-A-Za-z0-9_])")
_PRIVATE_HOST_COMMAND_WRAPPER = re.compile(
    r"(?<![-A-Za-z0-9_])(?:command|env|builtin|exec|time|nice|nohup|xargs|"
    r"coproc|alias|unalias)(?![-A-Za-z0-9_])"
)
_PRIVATE_HOST_DYNAMIC_COMMAND = re.compile(
    r"(?:^|[;&|][ \t]*|\$\([ \t]*|\([ \t]*|"
    r"\b(?:if|elif|then|do)[ \t]+)(?:command[ \t]+)?"
    r"(?:[\"']?\$(?:[A-Za-z_][A-Za-z0-9_]*|\{[^}]*\})[\"']?[ \t]+"
    r"(?:network|identity|container|group)\b|(?:eval|source)\b|\.[ \t]+|"
    r"/(?:usr/)?bin/(?:bash|sh)\b)"
)
_PRIVATE_HOST_INDIRECT_COMMAND = re.compile(
    r"(?:^|[;&|][ \t]*|\b(?:then|do)[ \t]+)[\"']?(?:\$|`|[<>]\()"
)
_PRIVATE_HOST_OBFUSCATED_AZ_COMMAND = re.compile(
    r"(?:^|[;&|][ \t]*|\b(?:then|do)[ \t]+)a(?:\\|\$|['\"])"
)
_PRIVATE_HOST_AZ_COMMAND_PATTERNS = (
    re.compile(r"^az[ \t]+network[ \t]+vnet[ \t]+show\b"),
    re.compile(r"^az[ \t]+network[ \t]+vnet[ \t]+subnet[ \t]+show\b"),
    re.compile(r"^az[ \t]+network[ \t]+nat[ \t]+gateway[ \t]+show\b"),
    re.compile(r"^az[ \t]+network[ \t]+private-endpoint[ \t]+show\b"),
    re.compile(
        r"^az[ \t]+network[ \t]+private-endpoint[ \t]+dns-zone-group[ \t]+list\b"
    ),
    re.compile(r"^az[ \t]+network[ \t]+private-dns[ \t]+zone[ \t]+show\b"),
    re.compile(
        r"^az[ \t]+network[ \t]+private-dns[ \t]+link[ \t]+vnet[ \t]+list\b"
    ),
    re.compile(r"^az[ \t]+identity[ \t]+show\b"),
    re.compile(r"^az[ \t]+container[ \t]+(?:create|show|list|logs)\b"),
)


def _has_disallowed_private_host_azure_cli(commands: List[str]) -> bool:
    """Require host-side Azure CLI usage to follow the generated direct grammar."""
    for command in commands:
        if command.strip() == "if ! command -v timeout >/dev/null 2>&1; then":
            continue
        if _private_condition_has_disallowed_evaluation(command):
            return True
        if re.match(r"^\s*if\s+\[\[.*\]\];\s*then\s*$", command):
            continue
        normalized = command.replace('"', "").replace("'", "")
        if _PRIVATE_HOST_COMMAND_WRAPPER.search(normalized):
            return True
        if _PRIVATE_HOST_DYNAMIC_COMMAND.search(normalized):
            return True
        if _PRIVATE_HOST_INDIRECT_COMMAND.search(normalized):
            return True
        if _PRIVATE_HOST_OBFUSCATED_AZ_COMMAND.search(normalized):
            return True
        az_invocations = list(_PRIVATE_HOST_AZ_COMMAND.finditer(normalized))
        az_invocation_offsets = {
            match.start("az") for match in az_invocations
        }
        if any(
            match.start() not in az_invocation_offsets
            for match in _PRIVATE_HOST_AZ_TOKEN.finditer(normalized)
        ):
            return True
        for match in az_invocations:
            invocation = normalized[match.start("az"):]
            if not any(
                pattern.match(invocation)
                for pattern in _PRIVATE_HOST_AZ_COMMAND_PATTERNS
            ):
                return True
    return False


def _has_unquoted_shell_control_operator(text: str) -> bool:
    """Return whether a narrow host command separator appears outside quotes."""
    quote = ""
    escaped = False
    for char in text:
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote != "'":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in ("'", '"'):
            quote = char
            continue
        if char in ";|&":
            return True
    return False


def _mask_generated_query_argument(raw_line: str) -> str:
    """Mask the one quoted ``--query`` argument used by generated Azure CLI."""
    query = re.search(r"--query[ \t]+(?P<quote>['\"])", raw_line)
    if query is None:
        return raw_line
    quote = query.group("quote")
    start = query.end()
    end = raw_line.find(quote, start)
    if end == -1:
        return raw_line
    return raw_line[:start] + "QUERY" + raw_line[end + 1:]


def _generated_query_has_disallowed_host_evaluation(raw_line: str) -> bool:
    """Reject host-evaluated syntax inside one generated Azure CLI query."""
    query = re.search(r"--query[ \t]+(?P<quote>['\"])", raw_line)
    if query is None:
        unquoted = re.search(r"--query[ \t]+(?P<value>[^ \t]+)", raw_line)
        if unquoted is None:
            return True
        return re.search(r"`|\$\(|[<>]\(|\\", unquoted.group("value")) is not None
    start = query.end()
    end = raw_line.find(query.group("quote"), start)
    if end == -1:
        return True
    return re.search(r"`|\$\(|[<>]\(|\\", raw_line[start:end]) is not None


def _private_condition_has_disallowed_evaluation(command: str) -> bool:
    """Reject host evaluation syntax inside generated ``if [[...]]`` checks."""
    condition = re.fullmatch(r"\s*if\s+\[\[(?P<body>.*?)\]\];\s*then\s*", command)
    if condition is None:
        return False
    return re.search(r"`|\$\(|[<>]\(|\\", condition.group("body")) is not None


def _private_condition_is_fail_closed(command: str) -> bool:
    """Allow generated topology guards to use only explicit OR comparisons."""
    if command.strip() == 'if [[ ! "$DATA_VERIFY_RUN_ID" =~ ^[0-9a-f]{32}$ ]]; then':
        return True
    condition = re.fullmatch(r"\s*if\s+\[\[(?P<body>.*?)\]\];\s*then\s*", command)
    if condition is None:
        return True
    body = condition.group("body")
    if _private_condition_has_disallowed_evaluation(command) or re.search(
        r"&&|\b-(?:eq|ne|lt|le|gt|ge)\b|[()]", body
    ):
        return False
    if re.search(
        r'"\$(?P<name>[A-Za-z_][A-Za-z0-9_]*)"\s*(?:!=|==)\s*"\$(?P=name)"',
        body,
    ):
        return False
    predicates = [predicate.strip() for predicate in body.split("||")]
    variable = r'(?:\$[A-Za-z_][A-Za-z0-9_]*|\$\{[A-Za-z_][A-Za-z0-9_]*##\*/\})'
    return all(
        re.fullmatch(rf'-z\s+"{variable}"', predicate)
        or re.fullmatch(
            rf'"{variable}"\s*(?:!=|==)\s*'
            rf'(?:"{variable}"|"[A-Za-z0-9_.:/-]+")',
            predicate,
        )
        for predicate in predicates
    )


def _private_conditions_have_direct_exit(text: str) -> bool:
    """Require every generated private guard to abort directly on a true result."""
    lines = [
        _strip_shell_inline_comment(line).strip()
        for line in text.splitlines()
        if _strip_shell_inline_comment(line).strip()
    ]
    for index, line in enumerate(lines):
        if not (
            re.fullmatch(r"if\s+\[\[.*\]\];\s*then", line)
            or line == "if ! command -v timeout >/dev/null 2>&1; then"
        ):
            continue
        if index + 2 >= len(lines) or lines[index + 1] != "exit 1" or lines[index + 2] != "fi":
            return False
    return True


def _private_branch_without_cleanup(text: str) -> str:
    """Remove the one permitted cleanup function before host-grammar checks."""
    cleanup = re.search(
        r"(?ms)^\s*cleanup_aci\s*\(\)\s*\{.*?^\s*\}", text
    )
    return text if cleanup is None else text[:cleanup.start()] + text[cleanup.end():]


def _has_leading_fail_fast_shell_options(text: str) -> bool:
    """Require fail-fast options as the first executable verifier statement."""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("#!"):
            continue
        return stripped == "set -euo pipefail"
    return False


def _has_unapproved_pre_case_statement(text: str) -> bool:
    """Permit no host setup before the generated network-mode case statement."""
    case_start = re.search(r'(?m)^\s*case\s+.*\bDATA_NETWORK_MODE\b.*\bin\s*$', text)
    if case_start is None:
        return True
    for line in text[:case_start.start()].splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped == "set -euo pipefail":
            continue
        return True
    return False


def _has_canonical_private_topology_query(
    text: str, name: str, query: str
) -> bool:
    """Require a result assignment to use its exact generated JMESPath query."""
    assignments = re.findall(
        rf"(?m)^\s*{re.escape(name)}\s*=.*$", text
    )
    return len(assignments) == 1 and len(re.findall(
        rf'(?m)^\s*{re.escape(name)}="\$\(az\b.*?--query\s+'
        rf'(?:"{re.escape(query)}"|{re.escape(query)})\s+--output\s+tsv\)"\s*$',
        text,
    )) == 1


def _payload_has_unexecuted_python_string(payload: str) -> bool:
    """Reject standalone string expressions in the generated ``python -c`` code."""
    marker = "python -c '"
    start = payload.find(marker)
    end = payload.rfind("'")
    if start == -1 or end <= start + len(marker):
        return True
    try:
        program = ast.parse(payload[start + len(marker):end])
    except SyntaxError:
        return True
    return any(
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
        for statement in program.body
    )


def _private_assignment_has_command_tail(raw_line: str) -> bool:
    """Reject assignment prefixes before host commands in the private grammar."""
    match = re.match(
        r"^\s*(?:local\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=", raw_line
    )
    if match is None:
        return False
    assignment = _split_generated_quoted_assignment(raw_line, match.group("name"))
    return assignment is None or bool(assignment[1])


def _has_disallowed_generated_parameter_expansion(text: str) -> bool:
    """Permit only simple generated parameter expansions in host statements."""
    for expansion in re.findall(r"\$\{([^}]*)\}", text):
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:##\*/)?", expansion) is None:
            return True
    return False


def _private_assignment_is_allowed(raw_line: str) -> bool:
    """Accept only fixed-name or one direct Azure CLI result assignments."""
    if re.fullmatch(
        r'\s*(?:local\s+)?aci_name="verify-data-\$DATA_VERIFY_RUN_ID"\s*', raw_line
    ):
        return True
    if re.fullmatch(r"\s*aci_(?:created|wait_failed)=[01]\s*", raw_line):
        return True
    if re.fullmatch(
        r'\s*aci_logs="\$\(timeout[ \t]+600[ \t]+az[ \t]+container[ \t]+'
        r'logs[ \t]+--resource-group[ \t]+"\$RESOURCE_GROUP"[ \t]+'
        r'--name[ \t]+"\$aci_name"[ \t]+--follow\)"[ \t]+'
        r'\|\|[ \t]+aci_wait_failed=1\s*',
        raw_line,
    ):
        return True
    assignment = re.fullmatch(
        r'\s*(?:local\s+)?[A-Za-z_][A-Za-z0-9_]*="\$\((?P<command>.*)\)"\s*',
        raw_line,
    )
    if assignment is None:
        return False
    command = assignment.group("command")
    command_without_query = _mask_generated_query_argument(command)
    return (
        command.startswith("az ")
        and command.count("$(") == 0
        and re.search(r"`|[<>]\(|\\", command) is None
        and not _has_disallowed_generated_parameter_expansion(command)
        and not _has_unquoted_shell_control_operator(command_without_query)
    )


def _private_branch_has_unapproved_host_statement(text: str) -> bool:
    """Allow only the generated private verifier's fixed host-side grammar."""
    for raw_command in _extract_shell_logical_commands(text):
        if _is_generated_shell_assignment(raw_command, "aci_command"):
            outside = _command_outside_generated_assignment(
                raw_command, "aci_command"
            )
            if not outside:
                continue
            raw_command = outside
        line = _strip_shell_inline_comment(raw_command).strip()
        if not line:
            continue
        if re.fullmatch(r':\s+"\$\{[A-Za-z_][A-Za-z0-9_]*:\?\}"', line):
            continue
        if line in ("exit 1", "fi", "trap cleanup_aci EXIT INT TERM"):
            continue
        if line == "if ! command -v timeout >/dev/null 2>&1; then":
            continue
        if re.fullmatch(
            r'if az container show --resource-group "\$RESOURCE_GROUP" '
            r'--name "\$aci_name" --only-show-errors; then',
            line,
        ):
            continue
        if re.fullmatch(r"if\s+\[\[.*\]\];\s*then", line):
            if _private_condition_is_fail_closed(line) and not _has_disallowed_generated_parameter_expansion(line):
                continue
            return True
        if line.startswith("az "):
            line_without_query = _mask_generated_query_argument(line)
            if (
                not re.search(r"`|\$\(|[<>]\(|\\", line)
                and not _has_disallowed_generated_parameter_expansion(line)
                and not _has_unquoted_shell_control_operator(line_without_query)
            ):
                continue
            return True
        if "=" in line and _private_assignment_is_allowed(line):
            continue
        return True
    return False


def _has_obfuscated_private_host_command_source(text: str) -> bool:
    """Reject shell word reconstruction at private verifier host command positions.

    The generated private branch has no use for quoted, escaped, or expanded
    executable names outside the ACI payload and cleanup handler. Rejecting
    these source forms prevents Bash from reconstructing an unapproved command
    such as ``\\a\\z`` or ``com\\mand \\a\\z`` before the direct Azure CLI
    allowlist sees it. This is a narrow source grammar check, not a shell lexer.
    """
    lines: List[str] = []
    for raw_command in _extract_shell_logical_commands(text):
        if _is_generated_shell_assignment(raw_command, "aci_command"):
            outside = _command_outside_generated_assignment(
                raw_command, "aci_command"
            )
            if not outside:
                continue
            raw_command = outside
        raw_line = raw_command
        if _private_condition_has_disallowed_evaluation(raw_line):
            return True
        if "--query" in raw_line:
            if _generated_query_has_disallowed_host_evaluation(
                raw_line
            ) or raw_line.rstrip().endswith("\\") or _has_unquoted_shell_control_operator(
                _mask_generated_query_argument(raw_line)
            ):
                return True
            continue
        if _private_assignment_is_allowed(raw_line):
            lines.append(raw_line)
            continue
        if _private_assignment_has_command_tail(raw_line):
            return True
        if re.match(r"^\s*if\s+\[\[.*\]\];\s*then\s*$", raw_line):
            continue
        if re.match(
            r'^\s*if az container show --resource-group "\$RESOURCE_GROUP" '
            r'--name "\$aci_name" --only-show-errors; then\s*$',
            raw_line,
        ):
            continue
        lines.append(raw_line)
    source = "\n".join(lines)
    command_word = re.compile(
        r"(?:^|[;&|\n][ \t]*|\b(?:then|do)[ \t]+)(?P<word>[^\s;|&()]+)",
        re.MULTILINE,
    )
    for match in command_word.finditer(source):
        word = match.group("word")
        if "=" in word:
            continue
        if any(marker in word for marker in ("\\", "'", '"', "$", "`")):
            return True
    return False


def _payload_uses_variable(payload: str, name: str) -> bool:
    """Return whether an ACI payload actually consumes one runtime variable."""
    if re.search(_shell_variable_pattern(name), payload):
        return True
    return re.search(
        rf"\b(?:os\.)?(?:environ|getenv)\s*(?:\[\s*|\(\s*)[\"']"
        rf"{re.escape(name)}[\"']",
        payload,
    ) is not None


_ASDW_APP009_SQL_COVERAGE = (
    ("Member", "SQL_DB_SVC01", "members"),
    ("ConsentRecord", "SQL_DB_SVC01", "consent_records"),
    ("DataRightsRequest", "SQL_DB_SVC01", "data_rights_requests"),
    ("LoyaltyAccount", "SQL_DB_SVC02", "loyalty_accounts"),
    ("PointTransaction", "SQL_DB_SVC02", "point_transactions"),
    ("Reward", "SQL_DB_SVC03", "rewards"),
    ("RewardExchange", "SQL_DB_SVC03", "reward_exchanges"),
    ("PaidMembershipContract", "SQL_DB_SVC07", "paid_membership_contracts"),
    ("SupportCase", "SQL_DB_SVC09", "support_cases"),
    ("CaseResolution", "SQL_DB_SVC09", "case_resolutions"),
)


def _extract_asdw_private_aci_payload(text: str) -> str:
    """Extract the generated private ACI assignment word for coverage checks."""
    branch = _extract_shell_case_branch(text, "DATA_NETWORK_MODE", "private")
    assignments = [
        command
        for command in _extract_shell_logical_commands(branch)
        if _is_generated_shell_assignment(command, "aci_command")
    ]
    if len(assignments) != 1:
        return ""
    assignment = _split_generated_quoted_assignment(assignments[0], "aci_command")
    if assignment is None or assignment[1]:
        return ""
    return assignment[0].replace(r'\"', '"')


def _extract_asdw_known_mode_python_source(
    payload: str,
    audit_mode: str,
) -> Tuple[str, Optional[str]]:
    """Extract Python only from one fixed, fail-closed ACI shell envelope."""
    if len(payload) < 2 or payload[0] != '"' or payload[-1] != '"':
        return "", (
            "selected APP data coverage ACI command must use one direct "
            "double-quoted assignment."
        )
    command = payload[1:-1]
    packages = "mssql-python azure-identity azure-cosmos"
    if audit_mode == _ASDW_AUDIT_MODE_ACL_DIRECT:
        packages += " azure-confidentialledger"
    prefixes = (
        "python -c '",
        f"python -m pip install {packages} && python -c '",
    )
    matching_prefixes = [prefix for prefix in prefixes if command.startswith(prefix)]
    if len(matching_prefixes) != 1 or not command.endswith("'"):
        return "", (
            "selected APP data coverage ACI command must be exactly `python -c` "
            "or the fixed package install followed by `&& python -c`, without "
            "prefix, suffix, or status masking commands."
        )
    source = command[len(matching_prefixes[0]):-1]
    if not source or "'" in source:
        return "", (
            "selected APP data coverage ACI command must keep one unbroken "
            "single-quoted Python source argument."
        )
    return source, None


def _load_asdw_sample_counts(
    path: "Path | str | None",
    text: Optional[str] = None,
) -> Tuple[Dict[str, int], Optional[str]]:
    """Load selected sample-data counts and retain a precise parse error."""
    if path is None:
        return {}, None
    sample_path = Path(path)
    if text is None and not sample_path.is_file():
        return {}, f"selected APP data coverage sample-data not found: {sample_path}"
    try:
        data = json.loads(
            sample_path.read_text(encoding="utf-8") if text is None else text
        )
    except OSError as exc:
        return {}, f"selected APP data coverage sample-data read error: {exc}"
    except UnicodeDecodeError as exc:
        return {}, f"selected APP data coverage sample-data UTF-8 decode error: {exc}"
    except json.JSONDecodeError as exc:
        return {}, f"selected APP data coverage sample-data JSON error: {exc}"
    if not isinstance(data, dict):
        return {}, "selected APP data coverage sample-data root must be an object."
    entities = data.get("entities")
    if not isinstance(entities, dict):
        return {}, "selected APP data coverage sample-data `entities` must be an object."
    invalid_entities = sorted(
        name
        for name, values in entities.items()
        if not isinstance(name, str) or not isinstance(values, list)
    )
    if invalid_entities:
        return {}, (
            "selected APP data coverage sample-data entity values must be lists: "
            + ", ".join(str(name) for name in invalid_entities)
            + "."
        )
    return {
        name: len(values)
        for name, values in entities.items()
        if isinstance(name, str) and isinstance(values, list)
    }, None


def _extract_asdw_audit_python_source(command: str) -> str:
    """AuditRecord count commandから埋込みPythonを抽出する。"""
    heredoc = re.search(
        r"<<[ \t]*['\"]?PY['\"]?[ \t]*\n(?P<source>.*?)\nPY(?:\n|$)",
        command,
        re.DOTALL,
    )
    if heredoc is not None:
        return heredoc.group("source")
    inline = re.search(
        r"\bpython(?:3)?\b[^\n]*?[ \t]+-c[ \t]+'(?P<source>.*)'",
        command,
        re.DOTALL,
    )
    return inline.group("source") if inline is not None else ""


def _asdw_audit_python_counts_entries(source: str) -> bool:
    """Confidential Ledger entriesを実際に列挙・集計するPythonか確認する。"""
    try:
        program = ast.parse(source)
    except SyntaxError:
        return False
    has_client = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ConfidentialLedgerClient"
        for node in ast.walk(program)
    )
    has_list = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "list_ledger_entries"
        for node in ast.walk(program)
    )
    has_sum = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "sum"
        for node in ast.walk(program)
    )
    has_print = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
        and any(
            isinstance(argument, ast.Call)
            and isinstance(argument.func, ast.Name)
            and argument.func.id == "sum"
            for argument in node.args
        )
        for node in ast.walk(program)
    )
    return has_client and has_list and has_sum and has_print


def _asdw_has_executable_audit_count(
    text: str,
    expected: int,
) -> bool:
    """AuditRecordの取得値を定義済みcheck_countへ渡す契約を確認する。"""
    check_function = re.search(
        r"(?ms)^[ \t]*check_count[ \t]*\(\)[ \t]*\{[ \t]*\n"
        r"(?P<body>.*?)^[ \t]*\}[ \t]*$",
        text,
    )
    if check_function is None:
        return False
    check_body = check_function.group("body")
    if (
        re.search(r"(?m)^[ \t]*local[ \t]+actual=\$2[ \t]*$", check_body)
        is None
        or re.search(r"(?m)^[ \t]*local[ \t]+expected=\$3[ \t]*$", check_body)
        is None
        or re.search(r"\bactual[ \t]*(?:==|!=)[ \t]*expected\b", check_body)
        is None
    ):
        return False
    audit_check = re.search(
        r'(?m)^[ \t]*check_count[ \t]+AuditRecord[ \t]+"\$'
        r'(?P<variable>[A-Za-z_][A-Za-z0-9_]*)"[ \t]+'
        rf"{expected}[ \t]*$",
        text,
    )
    if audit_check is None:
        return False
    variable = audit_check.group("variable")
    assignment_pattern = re.compile(
        rf'(?ms)(?:^|\n)[ \t]*(?:if[ \t]+)?{re.escape(variable)}="\$\('
        r'(?P<command>.*?)\)"(?:;[ \t]*then)?',
    )
    assignments = list(assignment_pattern.finditer(text, 0, audit_check.start()))
    if not assignments:
        return False
    python_source = _extract_asdw_audit_python_source(
        assignments[-1].group("command")
    )
    return bool(python_source) and _asdw_audit_python_counts_entries(
        python_source
    )


def _validate_asdw_acl_direct_count(
    source: str,
    expected: Optional[int],
) -> List[str]:
    """private ACI Python内のAzure confidential ledger直接件数を検査する。"""
    try:
        program = ast.parse(source)
    except SyntaxError:
        return ["ACL-direct AuditRecord count Python source is not parseable."]
    if expected is not None and (
        not isinstance(expected, int)
        or isinstance(expected, bool)
        or expected <= 0
    ):
        return ["ACL-direct AuditRecord expected count must be a positive integer."]

    imports = [
        statement
        for statement in program.body
        if isinstance(statement, ast.ImportFrom)
        and statement.module == "azure.confidentialledger"
        and len(statement.names) == 1
        and statement.names[0].name == "ConfidentialLedgerClient"
        and statement.names[0].asname is None
    ]
    if len(imports) != 1:
        return [
            "ACL-direct AuditRecord count must import ConfidentialLedgerClient exactly once."
        ]

    exit_stack_imports = [
        statement
        for statement in program.body
        if isinstance(statement, ast.ImportFrom)
        and statement.module == "contextlib"
        and len(statement.names) == 1
        and statement.names[0].name == "ExitStack"
        and statement.names[0].asname is None
    ]
    if len(exit_stack_imports) != 1:
        return [
            "ACL-direct AuditRecord count must import ExitStack exactly once."
        ]

    temporary_directory_imports = [
        statement
        for statement in program.body
        if isinstance(statement, ast.ImportFrom)
        and statement.module == "tempfile"
        and len(statement.names) == 1
        and statement.names[0].name == "TemporaryDirectory"
        and statement.names[0].asname is None
    ]
    if len(temporary_directory_imports) != 1:
        return [
            "ACL-direct AuditRecord count must import TemporaryDirectory exactly once."
        ]

    protected_names = {
        "ConfidentialLedgerClient",
        "DefaultAzureCredential",
        "CosmosClient",
        "ExitStack",
        "TemporaryDirectory",
        "os",
        "sys",
        "sum",
        "print",
        "int",
    }
    protected_bindings = [
        node.id
        for node in ast.walk(program)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, (ast.Store, ast.Del))
        and node.id in protected_names
    ] + [
        node.name
        for node in ast.walk(program)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name in protected_names
    ] + [
        node.arg
        for node in ast.walk(program)
        if isinstance(node, ast.arg) and node.arg in protected_names
    ]
    if protected_bindings:
        return [
            "ACL-direct AuditRecord count must not rebind its protected runtime symbols."
        ]

    candidates: List[Tuple[ast.Try, int, str, str, str, str]] = []
    for statement in program.body:
        if not isinstance(statement, ast.Try) or statement.handlers or statement.orelse:
            continue
        for index, child in enumerate(statement.body):
            if not (
                isinstance(child, ast.Assign)
                and len(child.targets) == 1
                and isinstance(child.targets[0], ast.Name)
                and isinstance(child.value, ast.Call)
                and isinstance(child.value.func, ast.Name)
                and child.value.func.id == "ConfidentialLedgerClient"
                and not child.value.args
            ):
                continue
            keyword_values = {keyword.arg: keyword.value for keyword in child.value.keywords}
            endpoint = keyword_values.get("endpoint")
            credential = keyword_values.get("credential")
            certificate_path = keyword_values.get("ledger_certificate_path")
            if not (
                set(keyword_values)
                == {"endpoint", "credential", "ledger_certificate_path"}
                and isinstance(endpoint, ast.Subscript)
                and isinstance(endpoint.value, ast.Attribute)
                and isinstance(endpoint.value.value, ast.Name)
                and endpoint.value.value.id == "os"
                and endpoint.value.attr == "environ"
                and isinstance(endpoint.slice, ast.Constant)
                and endpoint.slice.value == "CONFIDENTIAL_LEDGER_ENDPOINT"
                and isinstance(credential, ast.Name)
                and isinstance(certificate_path, ast.Name)
            ):
                continue
            certificate_path_name = certificate_path.id
            if index < 2:
                continue
            certificate_directory_statement = statement.body[index - 2]
            certificate_path_statement = statement.body[index - 1]
            if not (
                isinstance(certificate_directory_statement, ast.Assign)
                and len(certificate_directory_statement.targets) == 1
                and isinstance(certificate_directory_statement.targets[0], ast.Name)
                and isinstance(certificate_directory_statement.value, ast.Call)
                and isinstance(certificate_directory_statement.value.func, ast.Name)
                and certificate_directory_statement.value.func.id == "TemporaryDirectory"
                and not certificate_directory_statement.value.args
                and not certificate_directory_statement.value.keywords
                and isinstance(certificate_path_statement, ast.Assign)
                and len(certificate_path_statement.targets) == 1
                and isinstance(certificate_path_statement.targets[0], ast.Name)
                and certificate_path_statement.targets[0].id == certificate_path_name
                and isinstance(certificate_path_statement.value, ast.BinOp)
                and isinstance(certificate_path_statement.value.op, ast.Add)
                and isinstance(certificate_path_statement.value.left, ast.Attribute)
                and isinstance(certificate_path_statement.value.left.value, ast.Name)
                and certificate_path_statement.value.left.attr == "name"
                and isinstance(certificate_path_statement.value.right, ast.Constant)
                and certificate_path_statement.value.right.value
                == "/ledger_certificate.pem"
            ):
                continue
            certificate_directory_name = (
                certificate_directory_statement.targets[0].id
            )
            assert isinstance(certificate_path_statement.value.left, ast.Attribute)
            assert isinstance(certificate_path_statement.value.left.value, ast.Name)
            if (
                certificate_path_statement.value.left.value.id
                != certificate_directory_name
            ):
                continue
            candidates.append(
                (
                    statement,
                    index,
                    child.targets[0].id,
                    credential.id,
                    certificate_directory_name,
                    certificate_path_name,
                )
            )
    if len(candidates) != 1:
        return [
            "ACL-direct AuditRecord count requires exactly one reachable top-level "
            "ConfidentialLedgerClient bound to CONFIDENTIAL_LEDGER_ENDPOINT and "
            "a fresh ledger TLS certificate path."
        ]
    (
        audit_try,
        client_index,
        client_name,
        credential_name,
        certificate_directory_name,
        certificate_path_name,
    ) = candidates[0]
    audit_try_index = program.body.index(audit_try)
    before_try = program.body[:audit_try_index]
    if any(
        not isinstance(statement, (ast.Import, ast.ImportFrom, ast.Assign))
        for statement in before_try
    ):
        return [
            "ACL-direct AuditRecord count permits only imports and direct "
            "initializations before its top-level try."
        ]
    if any(
        isinstance(node, ast.Raise)
        or (
            isinstance(node, ast.Assert)
            and isinstance(node.test, ast.Constant)
            and not bool(node.test.value)
        )
        or (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "sys"
            and node.func.attr == "exit"
        )
        for statement in before_try
        for node in ast.walk(statement)
    ):
        return [
            "ACL-direct AuditRecord count must not terminate before its reachable top-level try."
        ]
    if program.body[audit_try_index + 1 :]:
        return [
            "ACL-direct AuditRecord count must end with its reachable top-level try/finally."
        ]
    body = audit_try.body
    if any(not isinstance(statement, (ast.Assign, ast.Expr)) for statement in body):
        return [
            "ACL-direct AuditRecord count must use direct straight-line statements "
            "inside its top-level try."
        ]

    def _exit_stack_initializations(name: str) -> int:
        return sum(
            1
            for statement in program.body[:audit_try_index]
            if isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == name
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "ExitStack"
            and not statement.value.args
            and not statement.value.keywords
        )

    if (
        _exit_stack_initializations(client_name) != 1
        or _exit_stack_initializations(credential_name) != 1
        or _exit_stack_initializations(certificate_directory_name) != 1
    ):
        return [
            "ACL-direct AuditRecord count must initialize its ledger client and "
            "credential/TLS certificate directory with ExitStack before the top-level try."
        ]

    client_calls = [
        node
        for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ConfidentialLedgerClient"
    ]
    if len(client_calls) != 1:
        return [
            "ACL-direct AuditRecord count requires exactly one ConfidentialLedgerClient call."
        ]

    temporary_directory_calls = [
        node
        for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "TemporaryDirectory"
    ]
    if len(temporary_directory_calls) != 1:
        return [
            "ACL-direct AuditRecord count requires exactly one fresh ledger TLS "
            "certificate directory."
        ]

    credential_calls = [
        node
        for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "DefaultAzureCredential"
    ]
    cosmos_calls = [
        node
        for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CosmosClient"
    ]
    if len(credential_calls) != 1 or len(cosmos_calls) != 1:
        return [
            "ACL-direct AuditRecord count requires exactly one managed-identity "
            "credential and one CosmosClient, without decoys."
        ]

    def _stored_count(name: str) -> int:
        return sum(
            1
            for statement in body
            for node in ast.walk(statement)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and node.id == name
        )

    if (
        _stored_count(client_name) != 1
        or _stored_count(certificate_directory_name) != 1
        or _stored_count(certificate_path_name) != 1
    ):
        return ["ACL-direct AuditRecord count must not reassign its ledger client."]

    credential_assignments = [
        statement
        for statement in body[:client_index]
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and statement.targets[0].id == credential_name
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
        and statement.value.func.id == "DefaultAzureCredential"
        and len(statement.value.args) == 0
        and len(statement.value.keywords) == 1
        and statement.value.keywords[0].arg == "managed_identity_client_id"
        and isinstance(statement.value.keywords[0].value, ast.Name)
    ]
    if len(credential_assignments) != 1:
        return [
            "ACL-direct AuditRecord count must reuse the managed-identity "
            "DefaultAzureCredential created in the same try."
        ]
    credential_assignment = credential_assignments[0]
    assert isinstance(credential_assignment.value, ast.Call)
    credential_client_id = credential_assignment.value.keywords[0].value
    assert isinstance(credential_client_id, ast.Name)
    client_id_name = credential_client_id.id
    client_id_assignments = [
        statement
        for statement in program.body[:audit_try_index]
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and statement.targets[0].id == client_id_name
        and isinstance(statement.value, ast.Constant)
        and statement.value.value == "$DATA_DEPLOY_IDENTITY_CLIENT_ID"
    ]
    if len(client_id_assignments) != 1 or _stored_count(credential_name) != 1:
        return [
            "ACL-direct AuditRecord count must bind its credential to "
            "DATA_DEPLOY_IDENTITY_CLIENT_ID without reassignment."
        ]
    client_id_stores = sum(
        1
        for node in ast.walk(program)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, (ast.Store, ast.Del))
        and node.id == client_id_name
    )
    if client_id_stores != 1:
        return [
            "ACL-direct AuditRecord count must bind DATA_DEPLOY_IDENTITY_CLIENT_ID "
            "to one immutable client-id name."
        ]
    cosmos_credential_uses = [
        keyword
        for statement in body
        for node in ast.walk(statement)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CosmosClient"
        for keyword in node.keywords
        if keyword.arg == "credential"
        and isinstance(keyword.value, ast.Name)
        and keyword.value.id == credential_name
    ]
    if len(cosmos_credential_uses) != 1:
        return [
            "ACL-direct AuditRecord count must reuse the same managed-identity "
            "credential for CosmosClient and ConfidentialLedgerClient."
        ]

    entries_candidates: List[Tuple[int, str]] = []
    for index, statement in enumerate(body):
        if not (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Attribute)
            and statement.value.func.attr == "list_ledger_entries"
            and isinstance(statement.value.func.value, ast.Name)
            and statement.value.func.value.id == client_name
            and not statement.value.args
        ):
            continue
        keywords = {keyword.arg: keyword.value for keyword in statement.value.keywords}
        collection = keywords.get("collection_id")
        if not (
            isinstance(collection, ast.Subscript)
            and isinstance(collection.value, ast.Attribute)
            and isinstance(collection.value.value, ast.Name)
            and collection.value.value.id == "os"
            and collection.value.attr == "environ"
            and isinstance(collection.slice, ast.Constant)
            and collection.slice.value == "CONFIDENTIAL_LEDGER_COLLECTION"
        ):
            continue
        entries_candidates.append((index, statement.targets[0].id))
    entries_index, entries_name = (
        entries_candidates[0] if len(entries_candidates) == 1 else (-1, "")
    )
    if not entries_name or entries_index <= client_index:
        return [
            "ACL-direct AuditRecord count must list application entries from "
            "CONFIDENTIAL_LEDGER_COLLECTION."
        ]
    list_entry_calls = [
        node
        for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "list_ledger_entries"
    ]
    if len(list_entry_calls) != 1:
        return [
            "ACL-direct AuditRecord count requires exactly one executable "
            "list_ledger_entries call."
        ]
    if _stored_count(entries_name) != 1:
        return [
            "ACL-direct AuditRecord count must not reassign its listed entries."
        ]

    count_candidates: List[Tuple[int, str]] = []
    for index, statement in enumerate(body):
        if not (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "sum"
            and len(statement.value.args) == 1
            and not statement.value.keywords
            and isinstance(statement.value.args[0], ast.GeneratorExp)
            and len(statement.value.args[0].generators) == 1
        ):
            continue
        generator = statement.value.args[0].generators[0]
        if not (
            isinstance(statement.value.args[0].elt, ast.Constant)
            and statement.value.args[0].elt.value == 1
            and isinstance(generator.iter, ast.Name)
            and generator.iter.id == entries_name
            and not generator.ifs
            and not generator.is_async
        ):
            continue
        count_candidates.append((index, statement.targets[0].id))
    count_index, count_name = (
        count_candidates[0] if len(count_candidates) == 1 else (-1, "")
    )
    if not count_name or count_index != entries_index + 1:
        return [
            "ACL-direct AuditRecord count must sum the listed entries immediately."
        ]
    if _stored_count(count_name) != 1:
        return [
            "ACL-direct AuditRecord count must not reassign the executed entry count."
        ]

    emit_indexes: List[int] = []
    guard_indexes: List[int] = []
    for index, statement in enumerate(body):
        if not isinstance(statement, ast.Expr):
            continue
        value = statement.value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "print"
            and len(value.args) == 1
            and isinstance(value.args[0], ast.Call)
            and isinstance(value.args[0].func, ast.Name)
            and value.args[0].func.id == "int"
            and len(value.args[0].args) == 1
            and isinstance(value.args[0].args[0], ast.Name)
            and value.args[0].args[0].id == count_name
        ):
            emit_indexes.append(index)
        if (
            isinstance(value, ast.BoolOp)
            and isinstance(value.op, ast.Or)
            and len(value.values) == 2
            and isinstance(value.values[0], ast.Compare)
            and isinstance(value.values[0].left, ast.Name)
            and value.values[0].left.id == count_name
            and len(value.values[0].ops) == 1
            and isinstance(value.values[0].ops[0], ast.Eq)
            and len(value.values[0].comparators) == 1
            and isinstance(value.values[0].comparators[0], ast.Constant)
            and isinstance(value.values[0].comparators[0].value, int)
            and not isinstance(value.values[0].comparators[0].value, bool)
            and value.values[0].comparators[0].value > 0
            and (
                expected is None
                or value.values[0].comparators[0].value == expected
            )
            and isinstance(value.values[1], ast.Call)
            and isinstance(value.values[1].func, ast.Attribute)
            and isinstance(value.values[1].func.value, ast.Name)
            and value.values[1].func.value.id == "sys"
            and value.values[1].func.attr == "exit"
            and len(value.values[1].args) == 1
            and isinstance(value.values[1].args[0], ast.Constant)
            and value.values[1].args[0].value == 1
        ):
            guard_indexes.append(index)
    if len(emit_indexes) != 1 or emit_indexes[0] <= count_index:
        return ["ACL-direct AuditRecord count must emit the executed entry count."]
    if len(guard_indexes) != 1 or guard_indexes[0] <= emit_indexes[0]:
        expected_description = (
            str(expected) if expected is not None else "a positive embedded value"
        )
        return [
            "ACL-direct AuditRecord count must compare with expected count "
            f"{expected_description} "
            "and fail on mismatch."
        ]

    allowed_exit_calls = {
        id(statement.value.values[1])
        for statement in body
        if isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.BoolOp)
        and isinstance(statement.value.op, ast.Or)
        and len(statement.value.values) == 2
        and isinstance(statement.value.values[0], ast.Compare)
        and len(statement.value.values[0].ops) == 1
        and isinstance(statement.value.values[0].ops[0], ast.Eq)
        and len(statement.value.values[0].comparators) == 1
        and isinstance(statement.value.values[0].comparators[0], ast.Constant)
        and isinstance(statement.value.values[0].comparators[0].value, int)
        and statement.value.values[0].comparators[0].value > 0
        and isinstance(statement.value.values[1], ast.Call)
        and isinstance(statement.value.values[1].func, ast.Attribute)
        and isinstance(statement.value.values[1].func.value, ast.Name)
        and statement.value.values[1].func.value.id == "sys"
        and statement.value.values[1].func.attr == "exit"
        and len(statement.value.values[1].args) == 1
        and isinstance(statement.value.values[1].args[0], ast.Constant)
        and statement.value.values[1].args[0].value == 1
    }
    all_exit_calls = [
        node
        for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "sys"
        and node.func.attr == "exit"
    ]
    if any(id(call) not in allowed_exit_calls for call in all_exit_calls) or any(
        isinstance(node, ast.Raise) for node in ast.walk(program)
    ):
        return [
            "ACL-direct AuditRecord count must not add an unconditional exit or raise path."
        ]

    direct_finalizers = [
        (statement.value.func.value.id, statement.value.func.attr)
        for statement in audit_try.finalbody
        if isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Attribute)
        and statement.value.func.attr in {"close", "cleanup"}
        and isinstance(statement.value.func.value, ast.Name)
        and not statement.value.args
        and not statement.value.keywords
    ]
    if (
        direct_finalizers.count((client_name, "close")) != 1
        or direct_finalizers.count((credential_name, "close")) != 1
        or direct_finalizers.count((certificate_directory_name, "cleanup")) != 1
        or direct_finalizers[-3:]
        != [
            (client_name, "close"),
            (credential_name, "close"),
            (certificate_directory_name, "cleanup"),
        ]
    ):
        return [
            "ACL-direct AuditRecord count must close its ledger client and "
            "managed-identity credential, then clean its ledger TLS certificate "
            "directory in the same finally block."
        ]
    if len(direct_finalizers) != len(audit_try.finalbody):
        return [
            "ACL-direct AuditRecord count finally block must contain direct "
            "close/cleanup calls only."
        ]
    return []


def _validate_asdw_sql_audit_count(
    source: str,
    expected: Optional[int],
) -> List[str]:
    """private ACI Python内のSVC-12 AuditRecord件数契約を検査する。"""
    try:
        program = ast.parse(source)
    except SyntaxError:
        return ["SQL AuditRecord count Python source is not parseable."]
    if expected is not None and (
        not isinstance(expected, int)
        or isinstance(expected, bool)
        or expected <= 0
    ):
        return ["SQL AuditRecord count expected value must be a positive integer."]

    connect_imports = [
        statement
        for statement in program.body
        if isinstance(statement, ast.ImportFrom)
        and statement.module == "mssql_python"
        and len(statement.names) == 1
        and statement.names[0].name == "connect"
        and statement.names[0].asname is None
    ]
    exit_stack_imports = [
        statement
        for statement in program.body
        if isinstance(statement, ast.ImportFrom)
        and statement.module == "contextlib"
        and len(statement.names) == 1
        and statement.names[0].name == "ExitStack"
        and statement.names[0].asname is None
    ]
    if len(connect_imports) != 1:
        return [
            "SQL AuditRecord count must import `connect` from `mssql_python` exactly once."
        ]
    if len(exit_stack_imports) != 1:
        return [
            "SQL AuditRecord count must import `ExitStack` from `contextlib` exactly once."
        ]

    protected_names = {"connect", "ExitStack", "os", "re", "sys", "print", "int"}
    protected_rebindings = [
        node.id
        for node in ast.walk(program)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, (ast.Store, ast.Del))
        and node.id in protected_names
    ]
    protected_arguments = [
        node.arg
        for node in ast.walk(program)
        if isinstance(node, ast.arg) and node.arg in protected_names
    ]
    protected_attributes = [
        f"{node.value.id}.{node.attr}"
        for node in ast.walk(program)
        if isinstance(node, ast.Attribute)
        and isinstance(node.ctx, (ast.Store, ast.Del))
        and isinstance(node.value, ast.Name)
        and (node.value.id, node.attr) in {("sys", "exit"), ("re", "fullmatch")}
    ]
    protected_definitions = [
        node.name
        for node in ast.walk(program)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name in protected_names
    ]
    protected_import_bindings: List[str] = []
    simple_import_counts = {"os": 0, "re": 0, "sys": 0}
    for node in ast.walk(program):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".", 1)[0]
                if bound in simple_import_counts and alias.asname is None and alias.name == bound:
                    simple_import_counts[bound] += 1
                elif bound in protected_names:
                    protected_import_bindings.append(bound)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound = alias.asname or alias.name
                allowed = (
                    node in connect_imports and bound == "connect"
                ) or (
                    node in exit_stack_imports and bound == "ExitStack"
                )
                if bound in protected_names and not allowed:
                    protected_import_bindings.append(bound)
    if (
        protected_rebindings
        or protected_arguments
        or protected_attributes
        or protected_definitions
        or protected_import_bindings
        or any(count != 1 for count in simple_import_counts.values())
    ):
        return [
            "SQL AuditRecord count must not rebind its protected runtime symbols."
        ]

    def _svc12_connection_assignment(statement: ast.AST) -> bool:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            return False
        target = statement.targets[0]
        value = statement.value
        if not (
            isinstance(target, ast.Name)
            and isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "connect"
            and len(value.args) == 1
            and not value.keywords
            and isinstance(value.args[0], ast.Constant)
            and isinstance(value.args[0].value, str)
        ):
            return False
        properties = [
            item.strip()
            for item in value.args[0].value.split(";")
            if item.strip()
        ]
        parsed_properties = [
            (item.split("=", 1)[0].strip().casefold(), item.split("=", 1)[1].strip())
            for item in properties
            if "=" in item
        ]
        required_properties = {
            "server": "$SQL_HOST",
            "database": "$SQL_DB_SVC12",
            "uid": "$DATA_DEPLOY_IDENTITY_CLIENT_ID",
            "authentication": "ActiveDirectoryMSI",
            "encrypt": "yes",
            "trustservercertificate": "no",
        }
        return (
            len(parsed_properties) == len(required_properties)
            and len(properties) == len(required_properties)
            and all(
                sum(1 for key, item_value in parsed_properties if key == expected_key and item_value == expected_value) == 1
                for expected_key, expected_value in required_properties.items()
            )
        )

    all_svc12_connections = [
        node for node in ast.walk(program) if _svc12_connection_assignment(node)
    ]
    direct_candidates = [
        (statement, index, child)
        for statement in program.body
        if isinstance(statement, ast.Try) and statement.finalbody
        for index, child in enumerate(statement.body)
        if _svc12_connection_assignment(child)
    ]
    if len(all_svc12_connections) != 1 or len(direct_candidates) != 1:
        return [
            "SQL AuditRecord count must open exactly one reachable top-level "
            "mssql-python connection bound to $SQL_DB_SVC12."
        ]
    matching_try, connection_index, connection_assignment = direct_candidates[0]
    assert isinstance(connection_assignment, ast.Assign)
    if matching_try.handlers or matching_try.orelse:
        return [
            "SQL AuditRecord count must use a top-level try/finally without "
            "except or else branches."
        ]
    connection_target = connection_assignment.targets[0]
    assert isinstance(connection_target, ast.Name)
    connection_name = connection_target.id

    body = matching_try.body
    errors: List[str] = []

    top_level_try_index = program.body.index(matching_try)
    before_try = program.body[:top_level_try_index]

    def _is_exit_stack_initialization(statement: ast.stmt, name: str) -> bool:
        return bool(
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == name
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "ExitStack"
            and not statement.value.args
            and not statement.value.keywords
        )

    if sum(_is_exit_stack_initialization(statement, connection_name) for statement in before_try) != 1:
        errors.append(
            "SQL AuditRecord count must initialize its SVC-12 connection with "
            "ExitStack before the top-level try."
        )

    def _direct_sys_exit(statement: ast.stmt) -> bool:
        return bool(
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Attribute)
            and isinstance(statement.value.func.value, ast.Name)
            and statement.value.func.value.id == "sys"
            and statement.value.func.attr == "exit"
        )

    if any(_direct_sys_exit(statement) or isinstance(statement, ast.Raise) for statement in before_try):
        errors.append(
            "SQL AuditRecord count must not terminate before its reachable top-level try."
        )

    cursor_name = ""
    cursor_index = -1
    for index, statement in enumerate(body):
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        value = statement.value
        if (
            isinstance(target, ast.Name)
            and isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "cursor"
            and isinstance(value.func.value, ast.Name)
            and value.func.value.id == connection_name
            and not value.args
            and not value.keywords
        ):
            cursor_name = target.id
            cursor_index = index
            break
    if not cursor_name or cursor_index <= connection_index:
        errors.append(
            "SQL AuditRecord count must create a cursor from the $SQL_DB_SVC12 connection."
        )
    elif sum(_is_exit_stack_initialization(statement, cursor_name) for statement in before_try) != 1:
        errors.append(
            "SQL AuditRecord count must initialize its SVC-12 cursor with "
            "ExitStack before the top-level try."
        )

    def _stored_name_count(name: str) -> int:
        return sum(
            1
            for statement in body
            for node in ast.walk(statement)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and node.id == name
        )

    if connection_name and _stored_name_count(connection_name) != 1:
        errors.append(
            "SQL AuditRecord count must not reassign its SVC-12 connection inside the try."
        )
    if cursor_name and _stored_name_count(cursor_name) != 1:
        errors.append(
            "SQL AuditRecord count must not reassign its SVC-12 cursor inside the try."
        )

    table_index = -1
    for index, statement in enumerate(body):
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        value = statement.value
        if not (isinstance(target, ast.Name) and target.id == "audit_table"):
            continue
        if (
            isinstance(value, ast.Subscript)
            and isinstance(value.value, ast.Attribute)
            and isinstance(value.value.value, ast.Name)
            and value.value.value.id == "os"
            and value.value.attr == "environ"
            and isinstance(value.slice, ast.Constant)
            and value.slice.value == "SQL_AUDIT_TABLE"
        ):
            table_index = index
            break
    if table_index <= cursor_index:
        errors.append(
            "SQL AuditRecord count must read `audit_table` from `SQL_AUDIT_TABLE`."
        )
    elif _stored_name_count("audit_table") != 1:
        errors.append(
            "SQL AuditRecord count must assign `audit_table` exactly once inside the try."
        )

    identifier_index = -1
    for index, statement in enumerate(body):
        if not (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "next"
            and len(statement.value.args) == 1
            and not statement.value.keywords
            and isinstance(statement.value.args[0], ast.Call)
            and isinstance(statement.value.args[0].func, ast.Name)
            and statement.value.args[0].func.id == "filter"
            and len(statement.value.args[0].args) == 2
            and isinstance(statement.value.args[0].args[0], ast.Constant)
            and statement.value.args[0].args[0].value is None
            and isinstance(statement.value.args[0].args[1], ast.List)
            and len(statement.value.args[0].args[1].elts) == 1
        ):
            continue
        call = statement.value.args[0].args[1].elts[0]
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "re"
            and call.func.attr == "fullmatch"
            and len(call.args) == 2
            and not call.keywords
            and isinstance(call.args[0], ast.Constant)
            and call.args[0].value == r"[A-Za-z_][A-Za-z0-9_]*"
            and isinstance(call.args[1], ast.Name)
            and call.args[1].id == "audit_table"
        ):
            continue
        identifier_index = index
        break
    if identifier_index <= table_index:
        errors.append(
            "SQL AuditRecord count must validate SQL_AUDIT_TABLE as a safe SQL identifier."
        )

    query_indexes: List[int] = []
    unknown_cursor_queries: List[int] = []
    for index, statement in enumerate(body):
        if not (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Attribute)
            and statement.value.func.attr == "execute"
            and isinstance(statement.value.func.value, ast.Name)
            and statement.value.func.value.id == cursor_name
            and len(statement.value.args) == 1
            and not statement.value.keywords
        ):
            continue
        query = statement.value.args[0]
        is_count_query = bool(
            isinstance(query, ast.JoinedStr)
            and len(query.values) == 3
            and isinstance(query.values[0], ast.Constant)
            and query.values[0].value == "SELECT COUNT_BIG(*) FROM [dbo].["
            and isinstance(query.values[1], ast.FormattedValue)
            and isinstance(query.values[1].value, ast.Name)
            and query.values[1].value.id == "audit_table"
            and isinstance(query.values[2], ast.Constant)
            and query.values[2].value == "]"
        )
        approved_metadata_queries = {
            "SELECT SCHEMA_NAME(schema_id), name, ledger_type_desc FROM sys.tables",
            "SELECT path, last_digest_block_id FROM sys.database_ledger_digest_locations WHERE is_current = 1",
        }
        is_approved_metadata_query = bool(
            isinstance(query, ast.Constant)
            and isinstance(query.value, str)
            and query.value in approved_metadata_queries
        )
        if is_count_query:
            query_indexes.append(index)
        elif not is_approved_metadata_query:
            unknown_cursor_queries.append(index)
    query_index = query_indexes[0] if len(query_indexes) == 1 else -1
    if query_index <= identifier_index:
        errors.append(
            "SQL AuditRecord count must execute one unfiltered "
            "COUNT_BIG query against [dbo].[SQL_AUDIT_TABLE]."
        )
    if unknown_cursor_queries:
        errors.append(
            "SQL AuditRecord count must not execute unapproved SQL through its SVC-12 cursor."
        )

    count_candidates: List[Tuple[int, str]] = []
    for index, statement in enumerate(body):
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        value = statement.value
        if not (
            isinstance(target, ast.Name)
            and isinstance(value, ast.Subscript)
            and isinstance(value.value, ast.Call)
            and isinstance(value.value.func, ast.Attribute)
            and value.value.func.attr == "fetchone"
            and isinstance(value.value.func.value, ast.Name)
            and value.value.func.value.id == cursor_name
            and not value.value.args
            and not value.value.keywords
            and isinstance(value.slice, ast.Constant)
            and value.slice.value == 0
        ):
            continue
        count_candidates.append((index, target.id))
    count_index, count_name = count_candidates[0] if len(count_candidates) == 1 else (-1, "")
    if not count_name or count_index <= query_index:
        errors.append(
            "SQL AuditRecord count must read the executed COUNT_BIG result through fetchone()[0]."
        )
    elif count_index != query_index + 1:
        errors.append(
            "SQL AuditRecord count must fetch the COUNT_BIG result immediately "
            "after the matching execute call."
        )
    elif _stored_name_count(count_name) != 1:
        errors.append(
            "SQL AuditRecord count must not reassign the executed COUNT_BIG result."
        )

    if any(_direct_sys_exit(statement) for statement in body):
        errors.append(
            "SQL AuditRecord count must not use an unconditional sys.exit statement."
        )

    emit_indexes: List[int] = []
    guard_indexes: List[int] = []
    guard_exit_call: Optional[ast.Call] = None
    for index, statement in enumerate(body):
        if not isinstance(statement, ast.Expr):
            continue
        value = statement.value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "print"
            and len(value.args) == 1
            and isinstance(value.args[0], ast.Call)
            and isinstance(value.args[0].func, ast.Name)
            and value.args[0].func.id == "int"
            and len(value.args[0].args) == 1
            and isinstance(value.args[0].args[0], ast.Name)
            and value.args[0].args[0].id == count_name
        ):
            emit_indexes.append(index)
        if not (
            isinstance(value, ast.BoolOp)
            and isinstance(value.op, ast.Or)
            and len(value.values) == 2
            and isinstance(value.values[0], ast.Compare)
            and isinstance(value.values[0].left, ast.Name)
            and value.values[0].left.id == count_name
            and len(value.values[0].ops) == 1
            and isinstance(value.values[0].ops[0], ast.Eq)
            and len(value.values[0].comparators) == 1
            and isinstance(value.values[0].comparators[0], ast.Constant)
            and isinstance(value.values[0].comparators[0].value, int)
            and not isinstance(value.values[0].comparators[0].value, bool)
            and value.values[0].comparators[0].value > 0
            and (
                expected is None
                or value.values[0].comparators[0].value == expected
            )
            and isinstance(value.values[1], ast.Call)
            and isinstance(value.values[1].func, ast.Attribute)
            and isinstance(value.values[1].func.value, ast.Name)
            and value.values[1].func.value.id == "sys"
            and value.values[1].func.attr == "exit"
            and len(value.values[1].args) == 1
            and isinstance(value.values[1].args[0], ast.Constant)
            and value.values[1].args[0].value == 1
        ):
            continue
        guard_indexes.append(index)
        assert isinstance(value.values[1], ast.Call)
        guard_exit_call = value.values[1]
    emit_index = emit_indexes[0] if len(emit_indexes) == 1 else -1
    guard_index = guard_indexes[0] if len(guard_indexes) == 1 else -1
    if emit_index <= count_index:
        errors.append("SQL AuditRecord count must emit the executed count result.")
    if guard_index <= emit_index:
        expected_description = (
            str(expected) if expected is not None else "a positive embedded value"
        )
        errors.append(
            "SQL AuditRecord count must compare the result with expected count "
            f"{expected_description} "
            "after emitting it and call sys.exit(1) on mismatch."
        )

    all_exit_calls = [
        call
        for call in ast.walk(program)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "sys"
        and call.func.attr == "exit"
    ]
    if any(
        len(call.args) != 1
        or not isinstance(call.args[0], ast.Constant)
        or call.args[0].value != 1
        for call in all_exit_calls
    ):
        errors.append(
            "SQL AuditRecord count must not use a success or dynamic sys.exit path."
        )
    if any(isinstance(node, ast.Raise) for node in ast.walk(matching_try)):
        errors.append("SQL AuditRecord count must not add a separate raise path.")

    direct_close_names = [
        statement.value.func.value.id
        for statement in matching_try.finalbody
        if isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Attribute)
        and statement.value.func.attr == "close"
        and isinstance(statement.value.func.value, ast.Name)
        and not statement.value.args
        and not statement.value.keywords
    ]
    if direct_close_names.count(cursor_name) != 1 or direct_close_names.count(connection_name) != 1:
        errors.append(
            "SQL AuditRecord count must close its SVC-12 cursor and connection "
            "as direct calls in the same finally block."
        )
    if len(direct_close_names) != len(matching_try.finalbody):
        errors.append(
            "SQL AuditRecord count finally block must contain direct close calls only."
        )
    return errors


def _validate_asdw_sql_audit_metadata(source: str) -> List[str]:
    """private ACI Python内のSQL ledger種別とACL digest保管を検査する。"""
    try:
        program = ast.parse(source)
    except SyntaxError:
        return ["SQL AuditRecord metadata Python source is not parseable."]

    urlparse_imports = [
        statement
        for statement in program.body
        if isinstance(statement, ast.ImportFrom)
        and statement.module == "urllib.parse"
        and len(statement.names) == 1
        and statement.names[0].name == "urlparse"
        and statement.names[0].asname is None
    ]
    if len(urlparse_imports) != 1:
        return [
            "SQL AuditRecord metadata must import `urlparse` from `urllib.parse` exactly once."
        ]

    protected_names = {"urlparse", "os", "str", "any", "next", "filter"}
    protected_bindings = [
        node.id
        for node in ast.walk(program)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, (ast.Store, ast.Del))
        and node.id in protected_names
    ] + [
        node.name
        for node in ast.walk(program)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name in protected_names
    ] + [
        node.arg
        for node in ast.walk(program)
        if isinstance(node, ast.arg) and node.arg in protected_names
    ]
    protected_import_bindings: List[str] = []
    plain_os_imports = 0
    for node in ast.walk(program):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".", 1)[0]
                if alias.name == "os" and alias.asname is None:
                    plain_os_imports += 1
                elif bound in protected_names:
                    protected_import_bindings.append(bound)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound = alias.asname or alias.name
                if bound in protected_names and node not in urlparse_imports:
                    protected_import_bindings.append(bound)
    os_environ_mutations = [
        node
        for node in ast.walk(program)
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr == "environ"
        )
        or (
            isinstance(node, ast.Subscript)
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "os"
            and node.value.attr == "environ"
        )
    ]
    os_environment_mutator_calls = [
        node
        for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and (
            (
                isinstance(node.func.value, ast.Attribute)
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "os"
                and node.func.value.attr == "environ"
                and node.func.attr
                in {"update", "clear", "pop", "popitem", "setdefault"}
            )
            or (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr in {"putenv", "unsetenv"}
            )
        )
    ]
    if (
        protected_bindings
        or protected_import_bindings
        or plain_os_imports != 1
        or os_environ_mutations
        or os_environment_mutator_calls
    ):
        return [
            "SQL AuditRecord metadata must not rebind its protected runtime symbols."
        ]

    def _svc12_connection(statement: ast.AST) -> Optional[str]:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            return None
        target = statement.targets[0]
        value = statement.value
        if not (
            isinstance(target, ast.Name)
            and isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "connect"
            and len(value.args) == 1
            and not value.keywords
            and isinstance(value.args[0], ast.Constant)
            and isinstance(value.args[0].value, str)
            and "Database=$SQL_DB_SVC12;" in value.args[0].value
        ):
            return None
        return target.id

    candidates: List[Tuple[ast.Try, str]] = []
    for statement in program.body:
        if not isinstance(statement, ast.Try) or statement.handlers or statement.orelse:
            continue
        connection_names = [
            name
            for child in statement.body
            for name in [_svc12_connection(child)]
            if name
        ]
        if len(connection_names) == 1:
            candidates.append((statement, connection_names[0]))
    if len(candidates) != 1:
        return [
            "SQL AuditRecord metadata requires exactly one reachable top-level SVC-12 try block."
        ]
    audit_try, connection_name = candidates[0]
    audit_try_index = program.body.index(audit_try)
    if any(
        isinstance(node, ast.Assert)
        and isinstance(node.test, ast.Constant)
        and not bool(node.test.value)
        for statement in program.body[:audit_try_index]
        for node in ast.walk(statement)
    ):
        return [
            "SQL AuditRecord metadata must not place its top-level try after `assert False`."
        ]
    body = audit_try.body
    if any(
        isinstance(node, ast.Assert)
        and isinstance(node.test, ast.Constant)
        and not bool(node.test.value)
        for node in ast.walk(audit_try)
    ):
        return [
            "SQL AuditRecord metadata must not place its checks after `assert False`."
        ]

    cursor_names = [
        target.id
        for statement in body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        for target in [statement.targets[0]]
        if isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Attribute)
        and statement.value.func.attr == "cursor"
        and isinstance(statement.value.func.value, ast.Name)
        and statement.value.func.value.id == connection_name
        and not statement.value.args
        and not statement.value.keywords
    ]
    if len(cursor_names) != 1:
        return [
            "SQL AuditRecord metadata must use exactly one cursor from the SVC-12 connection."
        ]
    cursor_name = cursor_names[0]
    cursor_aliases = [
        statement.targets[0].id
        for statement in body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and isinstance(statement.value, ast.Name)
        and statement.value.id == cursor_name
    ]
    if cursor_aliases:
        return [
            "SQL AuditRecord metadata must not alias its SVC-12 cursor."
        ]

    table_names = [
        statement.targets[0].id
        for statement in body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and isinstance(statement.value, ast.Subscript)
        and isinstance(statement.value.value, ast.Attribute)
        and isinstance(statement.value.value.value, ast.Name)
        and statement.value.value.value.id == "os"
        and statement.value.value.attr == "environ"
        and isinstance(statement.value.slice, ast.Constant)
        and statement.value.slice.value == "SQL_AUDIT_TABLE"
    ]
    if len(table_names) != 1:
        return [
            "SQL AuditRecord metadata must read exactly one table name from SQL_AUDIT_TABLE."
        ]
    table_name = table_names[0]

    indexed_body = list(enumerate(body))

    count_query_kind = "count"
    table_query_kind = "table-metadata"
    digest_query_kind = "digest-metadata"
    table_query = (
        "SELECT SCHEMA_NAME(schema_id), name, ledger_type_desc FROM sys.tables"
    )
    digest_query = (
        "SELECT path, last_digest_block_id FROM "
        "sys.database_ledger_digest_locations WHERE is_current = 1"
    )

    def _execute_kind(call: ast.Call) -> str:
        query = call.args[0] if len(call.args) == 1 and not call.keywords else None
        if (
            isinstance(query, ast.JoinedStr)
            and len(query.values) == 3
            and isinstance(query.values[0], ast.Constant)
            and query.values[0].value == "SELECT COUNT_BIG(*) FROM [dbo].["
            and isinstance(query.values[1], ast.FormattedValue)
            and isinstance(query.values[1].value, ast.Name)
            and query.values[1].value.id == table_name
            and isinstance(query.values[2], ast.Constant)
            and query.values[2].value == "]"
        ):
            return count_query_kind
        if isinstance(query, ast.Constant) and query.value == table_query:
            return table_query_kind
        if isinstance(query, ast.Constant) and query.value == digest_query:
            return digest_query_kind
        return ""

    execute_inventory: List[Tuple[int, str, bool]] = []
    for index, statement in indexed_body:
        for call in (
            node
            for node in ast.walk(statement)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == cursor_name
        ):
            execute_inventory.append(
                (
                    index,
                    _execute_kind(call),
                    isinstance(statement, ast.Expr) and statement.value is call,
                )
            )
    if (
        len(execute_inventory) != 3
        or any(not kind or not direct for _index, kind, direct in execute_inventory)
        or sorted(kind for _index, kind, _direct in execute_inventory)
        != sorted((count_query_kind, table_query_kind, digest_query_kind))
    ):
        return [
            "SQL AuditRecord metadata allows only direct SVC-12 cursor execute "
            "calls for count, sys.tables, and current digest metadata with "
            "`is_current = 1`."
        ]

    def _execute_indexes(query_text: str) -> List[int]:
        return [
            index for index, kind, _direct in execute_inventory
            if (
                (query_text == table_query and kind == table_query_kind)
                or (query_text == digest_query and kind == digest_query_kind)
            )
        ]

    table_query_indexes = _execute_indexes(table_query)
    if len(table_query_indexes) != 1:
        return [
            "SQL AuditRecord metadata must query schema, name, and ledger_type_desc from sys.tables."
        ]
    table_query_index = table_query_indexes[0]

    table_map_name = ""
    table_map_index = -1
    row_name = ""
    for index, statement in indexed_body:
        if not (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.DictComp)
            and len(statement.value.generators) == 1
        ):
            continue
        generator = statement.value.generators[0]
        if not (
            isinstance(generator.target, ast.Name)
            and isinstance(generator.iter, ast.Call)
            and isinstance(generator.iter.func, ast.Attribute)
            and generator.iter.func.attr == "fetchall"
            and isinstance(generator.iter.func.value, ast.Name)
            and generator.iter.func.value.id == cursor_name
            and not generator.iter.args
            and not generator.iter.keywords
            and not generator.ifs
            and not generator.is_async
        ):
            continue
        candidate_row = generator.target.id

        def _str_row_index(node: ast.AST, expected_index: int) -> bool:
            return bool(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "str"
                and len(node.args) == 1
                and not node.keywords
                and isinstance(node.args[0], ast.Subscript)
                and isinstance(node.args[0].value, ast.Name)
                and node.args[0].value.id == candidate_row
                and isinstance(node.args[0].slice, ast.Constant)
                and node.args[0].slice.value == expected_index
            )

        if not (
            isinstance(statement.value.key, ast.Tuple)
            and len(statement.value.key.elts) == 2
            and _str_row_index(statement.value.key.elts[0], 0)
            and _str_row_index(statement.value.key.elts[1], 1)
            and _str_row_index(statement.value.value, 2)
        ):
            continue
        table_map_name = statement.targets[0].id
        table_map_index = index
        row_name = candidate_row
        break
    if not table_map_name or table_map_index != table_query_index + 1:
        return [
            "SQL AuditRecord metadata must fetch the sys.tables result immediately "
            "and map schema/name to ledger_type_desc."
        ]

    ledger_type_name = ""
    ledger_type_index = -1
    for index, statement in indexed_body:
        if not (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Attribute)
            and isinstance(statement.value.func.value, ast.Name)
            and statement.value.func.value.id == table_map_name
            and statement.value.func.attr == "get"
            and len(statement.value.args) == 2
            and not statement.value.keywords
            and isinstance(statement.value.args[0], ast.Tuple)
            and len(statement.value.args[0].elts) == 2
            and isinstance(statement.value.args[0].elts[0], ast.Constant)
            and statement.value.args[0].elts[0].value == "dbo"
            and isinstance(statement.value.args[0].elts[1], ast.Name)
            and statement.value.args[0].elts[1].id == table_name
            and isinstance(statement.value.args[1], ast.Constant)
            and statement.value.args[1].value == ""
        ):
            continue
        ledger_type_name = statement.targets[0].id
        ledger_type_index = index
        break
    if not ledger_type_name or ledger_type_index != table_map_index + 1:
        return [
            "SQL AuditRecord metadata must resolve the dbo audit table ledger type."
        ]

    ledger_ok_name = ""
    ledger_ok_index = -1
    for index, statement in indexed_body:
        if not (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.Compare)
            and isinstance(statement.value.left, ast.Name)
            and statement.value.left.id == ledger_type_name
            and len(statement.value.ops) == 1
            and isinstance(statement.value.ops[0], ast.Eq)
            and len(statement.value.comparators) == 1
            and isinstance(statement.value.comparators[0], ast.Constant)
            and statement.value.comparators[0].value == "APPEND_ONLY_LEDGER_TABLE"
        ):
            continue
        ledger_ok_name = statement.targets[0].id
        ledger_ok_index = index
        break
    if not ledger_ok_name or ledger_ok_index != ledger_type_index + 1:
        return [
            "SQL AuditRecord metadata must compare ledger_type_desc with "
            "APPEND_ONLY_LEDGER_TABLE."
        ]

    def _is_fail_closed_guard(statement: ast.stmt, name: str) -> bool:
        return bool(
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "next"
            and len(statement.value.args) == 1
            and not statement.value.keywords
            and isinstance(statement.value.args[0], ast.Call)
            and isinstance(statement.value.args[0].func, ast.Name)
            and statement.value.args[0].func.id == "filter"
            and len(statement.value.args[0].args) == 2
            and isinstance(statement.value.args[0].args[0], ast.Constant)
            and statement.value.args[0].args[0].value is None
            and isinstance(statement.value.args[0].args[1], ast.List)
            and len(statement.value.args[0].args[1].elts) == 1
            and isinstance(statement.value.args[0].args[1].elts[0], ast.Name)
            and statement.value.args[0].args[1].elts[0].id == name
        )

    ledger_guard_indexes = [
        index
        for index, statement in indexed_body
        if _is_fail_closed_guard(statement, ledger_ok_name)
    ]
    ledger_ok_reassignments = sum(
        1
        for statement in body[ledger_ok_index + 1 :]
        for node in ast.walk(statement)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, (ast.Store, ast.Del))
        and node.id == ledger_ok_name
    )
    if (
        len(ledger_guard_indexes) != 1
        or ledger_guard_indexes[0] <= ledger_ok_index
        or ledger_ok_reassignments
    ):
        return [
            "SQL AuditRecord metadata must fail closed when the audit table is not append-only."
        ]

    ledger_host_name = ""
    ledger_host_index = -1
    for index, statement in indexed_body:
        if not (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.Attribute)
            and statement.value.attr == "hostname"
            and isinstance(statement.value.value, ast.Call)
            and isinstance(statement.value.value.func, ast.Name)
            and statement.value.value.func.id == "urlparse"
            and len(statement.value.value.args) == 1
            and not statement.value.value.keywords
            and isinstance(statement.value.value.args[0], ast.Subscript)
            and isinstance(statement.value.value.args[0].value, ast.Attribute)
            and isinstance(statement.value.value.args[0].value.value, ast.Name)
            and statement.value.value.args[0].value.value.id == "os"
            and statement.value.value.args[0].value.attr == "environ"
            and isinstance(statement.value.value.args[0].slice, ast.Constant)
            and statement.value.value.args[0].slice.value
            == "CONFIDENTIAL_LEDGER_ENDPOINT"
        ):
            continue
        ledger_host_name = statement.targets[0].id
        ledger_host_index = index
        break
    ledger_host_reassignments = sum(
        1
        for statement in body[ledger_host_index + 1 :]
        for node in ast.walk(statement)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, (ast.Store, ast.Del))
        and node.id == ledger_host_name
    ) if ledger_host_name else 0
    if (
        not ledger_host_name
        or ledger_host_index <= ledger_ok_index
        or ledger_host_reassignments
    ):
        return [
            "SQL AuditRecord metadata must derive the trusted digest host from "
            "CONFIDENTIAL_LEDGER_ENDPOINT."
        ]
    host_guard_indexes = [
        index
        for index, statement in indexed_body
        if _is_fail_closed_guard(statement, ledger_host_name)
    ]
    if host_guard_indexes != [ledger_host_index + 1]:
        return [
            "SQL AuditRecord metadata must fail closed when the trusted digest host is empty."
        ]

    digest_query_indexes = _execute_indexes(digest_query)
    if digest_query_indexes != [host_guard_indexes[0] + 1]:
        return [
            "SQL AuditRecord metadata must query current digest locations with "
            "`is_current = 1` through the SVC-12 cursor."
        ]
    digest_query_index = digest_query_indexes[0]

    digest_rows_name = ""
    digest_rows_index = -1
    for index, statement in indexed_body:
        if not (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Attribute)
            and statement.value.func.attr == "fetchall"
            and isinstance(statement.value.func.value, ast.Name)
            and statement.value.func.value.id == cursor_name
            and not statement.value.args
            and not statement.value.keywords
        ):
            continue
        if index == table_map_index:
            continue
        digest_rows_name = statement.targets[0].id
        digest_rows_index = index
        break
    if not digest_rows_name or digest_rows_index != digest_query_index + 1:
        return [
            "SQL AuditRecord metadata must fetchall current digest location rows "
            "immediately after the digest query."
        ]

    digest_ok_name = ""
    digest_ok_index = -1
    for index, statement in indexed_body:
        if not (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "any"
            and len(statement.value.args) == 1
            and not statement.value.keywords
            and isinstance(statement.value.args[0], ast.GeneratorExp)
            and len(statement.value.args[0].generators) == 1
        ):
            continue
        generator = statement.value.args[0].generators[0]
        element = statement.value.args[0].elt
        if not (
            isinstance(generator.target, ast.Name)
            and isinstance(generator.iter, ast.Name)
            and generator.iter.id == digest_rows_name
            and not generator.ifs
            and not generator.is_async
            and isinstance(element, ast.Compare)
            and isinstance(element.left, ast.Tuple)
            and len(element.left.elts) == 2
            and len(element.ops) == 1
            and isinstance(element.ops[0], ast.Eq)
            and len(element.comparators) == 1
            and isinstance(element.comparators[0], ast.Tuple)
            and all(
                isinstance(value, ast.Constant) and value.value is True
                for value in element.comparators[0].elts
            )
        ):
            continue
        row_variable = generator.target.id
        host_comparison, block_comparison = element.left.elts
        same_host = bool(
            isinstance(host_comparison, ast.Compare)
            and isinstance(host_comparison.left, ast.Attribute)
            and host_comparison.left.attr == "hostname"
            and isinstance(host_comparison.left.value, ast.Call)
            and isinstance(host_comparison.left.value.func, ast.Name)
            and host_comparison.left.value.func.id == "urlparse"
            and len(host_comparison.left.value.args) == 1
            and isinstance(host_comparison.left.value.args[0], ast.Call)
            and isinstance(host_comparison.left.value.args[0].func, ast.Name)
            and host_comparison.left.value.args[0].func.id == "str"
            and len(host_comparison.left.value.args[0].args) == 1
            and isinstance(host_comparison.left.value.args[0].args[0], ast.Subscript)
            and isinstance(host_comparison.left.value.args[0].args[0].value, ast.Name)
            and host_comparison.left.value.args[0].args[0].value.id == row_variable
            and isinstance(host_comparison.left.value.args[0].args[0].slice, ast.Constant)
            and host_comparison.left.value.args[0].args[0].slice.value == 0
            and len(host_comparison.ops) == 1
            and isinstance(host_comparison.ops[0], ast.Eq)
            and len(host_comparison.comparators) == 1
            and isinstance(host_comparison.comparators[0], ast.Name)
            and host_comparison.comparators[0].id == ledger_host_name
        )
        uploaded_block = bool(
            isinstance(block_comparison, ast.Compare)
            and isinstance(block_comparison.left, ast.Subscript)
            and isinstance(block_comparison.left.value, ast.Name)
            and block_comparison.left.value.id == row_variable
            and isinstance(block_comparison.left.slice, ast.Constant)
            and block_comparison.left.slice.value == 1
            and len(block_comparison.ops) == 1
            and isinstance(block_comparison.ops[0], ast.IsNot)
            and len(block_comparison.comparators) == 1
            and isinstance(block_comparison.comparators[0], ast.Constant)
            and block_comparison.comparators[0].value is None
        )
        if not same_host or not uploaded_block:
            continue
        digest_ok_name = statement.targets[0].id
        digest_ok_index = index
        break
    if not digest_ok_name or digest_ok_index != digest_rows_index + 1:
        return [
            "SQL AuditRecord metadata must require a current digest row with the "
            "same host and a non-null last_digest_block_id."
        ]

    digest_guard_indexes = [
        index
        for index, statement in indexed_body
        if _is_fail_closed_guard(statement, digest_ok_name)
    ]
    digest_ok_reassignments = sum(
        1
        for statement in body[digest_ok_index + 1 :]
        for node in ast.walk(statement)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, (ast.Store, ast.Del))
        and node.id == digest_ok_name
    )
    if (
        len(digest_guard_indexes) != 1
        or digest_guard_indexes[0] <= digest_ok_index
        or digest_ok_reassignments
    ):
        return [
            "SQL AuditRecord metadata must fail closed when no uploaded ACL digest matches."
        ]
    if ledger_guard_indexes[0] >= digest_guard_indexes[0]:
        return [
            "SQL AuditRecord metadata must enforce the append-only table guard "
            "before the uploaded digest guard."
        ]
    return []


def _asdw_python_env_value(node: Optional[ast.AST], key: str) -> bool:
    """Return whether a Python AST node is exactly ``os.environ[KEY]``."""
    return bool(
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "os"
        and node.value.attr == "environ"
        and isinstance(node.slice, ast.Constant)
        and node.slice.value == key
    )


def _asdw_direct_count_guard(
    statement: ast.stmt,
    count_name: str,
) -> Optional[Tuple[int, ast.Call]]:
    """Parse one direct ``count == N or sys.exit(1)`` guard."""
    if not (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.BoolOp)
        and isinstance(statement.value.op, ast.Or)
        and len(statement.value.values) == 2
    ):
        return None
    comparison, failure = statement.value.values
    if not (
        isinstance(comparison, ast.Compare)
        and isinstance(comparison.left, ast.Name)
        and comparison.left.id == count_name
        and len(comparison.ops) == 1
        and isinstance(comparison.ops[0], ast.Eq)
        and len(comparison.comparators) == 1
        and isinstance(comparison.comparators[0], ast.Constant)
        and isinstance(comparison.comparators[0].value, int)
        and not isinstance(comparison.comparators[0].value, bool)
        and comparison.comparators[0].value > 0
        and isinstance(failure, ast.Call)
        and isinstance(failure.func, ast.Attribute)
        and isinstance(failure.func.value, ast.Name)
        and failure.func.value.id == "sys"
        and failure.func.attr == "exit"
        and len(failure.args) == 1
        and isinstance(failure.args[0], ast.Constant)
        and failure.args[0].value == 1
        and not failure.keywords
    ):
        return None
    return comparison.comparators[0].value, failure


def _validate_asdw_known_mode_selected_data(
    text: str,
    sample_data_path: "Path | str | None",
    audit_mode: str,
    sample_data_text: Optional[str] = None,
) -> List[str]:
    """Validate the design-selected private payload with one bounded grammar."""
    counts, sample_error = _load_asdw_sample_counts(
        sample_data_path,
        sample_data_text,
    )
    if sample_error is not None:
        return [sample_error]
    required_entities = {
        entity for entity, _database, _table in _ASDW_APP009_SQL_COVERAGE
    } | {"VocRecord", "AuditRecord"}
    if sample_data_path is not None:
        missing_entities = sorted(required_entities - counts.keys())
        if missing_entities:
            return [
                "selected APP data coverage sample-data must contain list values for: "
                + ", ".join(missing_entities)
                + "."
            ]
        empty_entities = sorted(
            entity for entity in required_entities if counts[entity] <= 0
        )
        if empty_entities:
            return [
                "selected APP data coverage sample-data must contain at least one "
                "record for: "
                + ", ".join(empty_entities)
                + "."
            ]

    payload = _extract_asdw_private_aci_payload(text)
    source, envelope_error = _extract_asdw_known_mode_python_source(
        payload,
        audit_mode,
    )
    if envelope_error is not None:
        return [envelope_error]
    try:
        program = ast.parse(source)
    except SyntaxError:
        return ["selected APP data coverage private Python payload is not parseable."]

    errors: List[str] = []
    uses_socket_lookup = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "socket"
        and node.func.attr == "getaddrinfo"
        for node in ast.walk(program)
    )
    canonical_imports = {
        "ExitStack": ("from", "contextlib"),
        "connect": ("from", "mssql_python"),
        "DefaultAzureCredential": ("from", "azure.identity"),
        "CosmosClient": ("from", "azure.cosmos"),
        "os": ("import", "os"),
        "sys": ("import", "sys"),
    }
    if audit_mode == _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST:
        canonical_imports.update(
            {
                "re": ("import", "re"),
                "urlparse": ("from", "urllib.parse"),
            }
        )
        if uses_socket_lookup:
            canonical_imports["socket"] = ("import", "socket")
    else:
        canonical_imports["ConfidentialLedgerClient"] = (
            "from",
            "azure.confidentialledger",
        )
        canonical_imports["TemporaryDirectory"] = (
            "from",
            "tempfile",
        )
    protected_names = set(canonical_imports) | {
        "print",
        "int",
        "sum",
        "list",
        "next",
        "filter",
        "str",
        "any",
        "set",
        "iter",
        "exit",
        "quit",
    }
    observed_imports: Dict[str, List[Tuple[str, str]]] = {
        name: [] for name in protected_names
    }
    observed_import_specs: List[Tuple[str, str, str]] = []
    invalid_protected_import = False
    for node in ast.walk(program):
        if isinstance(node, ast.Import):
            for alias in node.names:
                observed_import_specs.append(
                    ("import", alias.name, alias.asname or "")
                )
                bound = alias.asname or alias.name.split(".", 1)[0]
                if bound not in protected_names:
                    continue
                observed_imports[bound].append(("import", alias.name))
                if (
                    alias.asname is not None
                    or canonical_imports.get(bound) != ("import", alias.name)
                ):
                    invalid_protected_import = True
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                observed_import_specs.append(
                    ("from", node.module or "", alias.name)
                    if alias.asname is None
                    else ("from-alias", node.module or "", alias.asname)
                )
                bound = alias.asname or alias.name
                if bound not in protected_names:
                    continue
                observed_imports[bound].append(("from", node.module or ""))
                if (
                    alias.asname is not None
                    or alias.name != bound
                    or canonical_imports.get(bound)
                    != ("from", node.module or "")
                ):
                    invalid_protected_import = True
    protected_rebindings = [
        node.id
        for node in ast.walk(program)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, (ast.Store, ast.Del))
        and node.id in protected_names
    ] + [
        node.arg
        for node in ast.walk(program)
        if isinstance(node, ast.arg) and node.arg in protected_names
    ] + [
        node.name
        for node in ast.walk(program)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name in protected_names
    ]
    protected_attribute_rebindings = [
        f"{node.value.id}.{node.attr}"
        for node in ast.walk(program)
        if isinstance(node, ast.Attribute)
        and isinstance(node.ctx, (ast.Store, ast.Del))
        and isinstance(node.value, ast.Name)
        and (node.value.id, node.attr) in {
            ("sys", "exit"),
            ("os", "_exit"),
        }
    ]
    allowed_import_specs = {
        ("from", "contextlib", "ExitStack"),
        ("from", "mssql_python", "connect"),
        ("from", "azure.identity", "DefaultAzureCredential"),
        ("from", "azure.cosmos", "CosmosClient"),
        ("import", "os", ""),
        ("import", "sys", ""),
        ("import", "re", ""),
    }
    if audit_mode == _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST:
        allowed_import_specs.update(
            {
                ("from", "urllib.parse", "urlparse"),
            }
        )
        if uses_socket_lookup:
            allowed_import_specs.add(("import", "socket", ""))
    else:
        allowed_import_specs.add(
            ("from", "azure.confidentialledger", "ConfidentialLedgerClient")
        )
        allowed_import_specs.add(("from", "tempfile", "TemporaryDirectory"))
    if (
        invalid_protected_import
        or protected_rebindings
        or protected_attribute_rebindings
        or len(observed_import_specs) != len(set(observed_import_specs))
        or any(spec not in allowed_import_specs for spec in observed_import_specs)
        or any(
            observed_imports[name] != [expected]
            for name, expected in canonical_imports.items()
        )
        or any(
            observed_imports[name]
            for name in protected_names - set(canonical_imports)
        )
    ):
        errors.append(
            "selected APP data coverage must use each canonical SDK/runtime "
            "import exactly once without protected-name rebinding."
        )

    top_level_tries = [
        statement
        for statement in program.body
        if isinstance(statement, ast.Try) and statement.finalbody
    ]
    if len(top_level_tries) != 1:
        return [
            "selected APP data coverage requires exactly one reachable top-level try/finally."
        ]
    main_try = top_level_tries[0]
    try_index = program.body.index(main_try)
    before_try = program.body[:try_index]
    after_try = program.body[try_index + 1 :]
    if main_try.handlers or main_try.orelse:
        errors.append(
            "selected APP data coverage top-level try must not use except or else branches."
        )
    def _safe_literal(node: ast.AST) -> bool:
        if isinstance(node, ast.Constant):
            return True
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            return all(_safe_literal(element) for element in node.elts)
        if isinstance(node, ast.Dict):
            return all(
                key is not None
                and _safe_literal(key)
                and _safe_literal(value)
                for key, value in zip(node.keys, node.values)
            )
        return False

    def _safe_pre_try_statement(statement: ast.stmt) -> bool:
        if isinstance(statement, (ast.Import, ast.ImportFrom)):
            return True
        if not (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
        ):
            return False
        value = statement.value
        return _safe_literal(value) or bool(
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "ExitStack"
            and not value.args
            and not value.keywords
        )

    if after_try or any(
        not _safe_pre_try_statement(statement)
        for statement in before_try
    ):
        errors.append(
            "selected APP data coverage permits only imports and direct "
            "initializations before its final top-level try/finally."
        )
    forbidden_termination_calls = [
        node
        for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and (
            (
                isinstance(node.func, ast.Name)
                and node.func.id in {"exit", "quit"}
            )
            or (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr == "_exit"
            )
        )
    ]
    if forbidden_termination_calls:
        errors.append(
            "selected APP data coverage must not use exit, quit, or os._exit "
            "success-termination paths."
        )
    process_replacement_calls = [
        node
        for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "os"
        and node.func.attr in {
            "execl",
            "execle",
            "execlp",
            "execlpe",
            "execv",
            "execve",
            "execvp",
            "execvpe",
        }
    ]
    if process_replacement_calls:
        errors.append(
            "selected APP data coverage must not replace its verifier process "
            "with an os.exec* call."
        )
    if any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda))
        for node in ast.walk(program)
    ) or len([node for node in ast.walk(program) if isinstance(node, ast.Try)]) != 1:
        errors.append(
            "selected APP data coverage must not hide validation in a dead scope "
            "or nested try."
        )
    body = main_try.body
    if any(not isinstance(statement, (ast.Assign, ast.Expr)) for statement in body):
        errors.append(
            "selected APP data coverage must use direct straight-line statements "
            "inside its top-level try."
        )

    def _name_store_count(name: str) -> int:
        return sum(
            1
            for node in ast.walk(program)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and node.id == name
        )

    def _exit_stack_placeholder(name: str) -> bool:
        candidates = [
            statement
            for statement in before_try
            if isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == name
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "ExitStack"
            and not statement.value.args
            and not statement.value.keywords
        ]
        return len(candidates) == 1

    expected_databases = {
        database for _entity, database, _table in _ASDW_APP009_SQL_COVERAGE
    }
    if audit_mode == _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST:
        expected_databases.add("SQL_DB_SVC12")

    connection_records: Dict[str, Tuple[str, int]] = {}
    direct_connect_calls: List[ast.Call] = []
    for index, statement in enumerate(body):
        if not (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "connect"
            and len(statement.value.args) == 1
            and not statement.value.keywords
            and isinstance(statement.value.args[0], ast.Constant)
            and isinstance(statement.value.args[0].value, str)
        ):
            continue
        match = re.search(
            r"(?:^|;)Database=\$(SQL_DB_SVC\d+);",
            statement.value.args[0].value,
        )
        if match is None:
            continue
        database = match.group(1)
        properties = [
            item.strip()
            for item in statement.value.args[0].value.split(";")
            if item.strip()
        ]
        parsed_properties = [
            (
                item.split("=", 1)[0].strip().casefold(),
                item.split("=", 1)[1].strip(),
            )
            for item in properties
            if "=" in item
        ]
        required_properties = {
            "server": "$SQL_HOST",
            "database": f"${database}",
            "uid": "$DATA_DEPLOY_IDENTITY_CLIENT_ID",
            "authentication": "ActiveDirectoryMSI",
            "encrypt": "yes",
            "trustservercertificate": "no",
        }
        if (
            len(properties) != len(required_properties)
            or len(parsed_properties) != len(required_properties)
            or any(
                sum(
                    1
                    for key, value in parsed_properties
                    if key == required_key and value == required_value
                )
                != 1
                for required_key, required_value in required_properties.items()
            )
        ):
            errors.append(
                "selected APP data coverage must use the canonical UAMI SQL "
                f"connection for ${database}."
            )
        direct_connect_calls.append(statement.value)
        if database in connection_records:
            errors.append(
                f"selected APP data coverage must open ${database} exactly once."
            )
        connection_records[database] = (statement.targets[0].id, index)
    all_connect_calls = [
        node
        for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "connect"
    ]
    if (
        set(connection_records) != expected_databases
        or {id(call) for call in all_connect_calls}
        != {id(call) for call in direct_connect_calls}
    ):
        errors.append(
            "selected APP data coverage must open exactly the design-selected "
            "SQL databases as direct top-level-try assignments."
        )

    cursor_by_database: Dict[str, Tuple[str, int]] = {}
    direct_cursor_calls: List[ast.Call] = []
    for database, (connection_name, connection_index) in connection_records.items():
        candidates = [
            (index, statement)
            for index, statement in enumerate(body)
            if isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Attribute)
            and statement.value.func.attr == "cursor"
            and isinstance(statement.value.func.value, ast.Name)
            and statement.value.func.value.id == connection_name
            and not statement.value.args
            and not statement.value.keywords
        ]
        if len(candidates) != 1 or candidates[0][0] <= connection_index:
            errors.append(
                f"selected APP data coverage must create one cursor from ${database}."
            )
            continue
        cursor_index, cursor_statement = candidates[0]
        assert isinstance(cursor_statement, ast.Assign)
        assert isinstance(cursor_statement.targets[0], ast.Name)
        assert isinstance(cursor_statement.value, ast.Call)
        cursor_by_database[database] = (cursor_statement.targets[0].id, cursor_index)
        direct_cursor_calls.append(cursor_statement.value)
    all_cursor_calls = [
        node
        for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "cursor"
    ]
    if {id(call) for call in all_cursor_calls} != {
        id(call) for call in direct_cursor_calls
    }:
        errors.append(
            "selected APP data coverage must not create SQL cursors in dead or nested scopes."
        )

    resource_names = {
        name
        for name, _index in connection_records.values()
    } | {
        name
        for name, _index in cursor_by_database.values()
    }
    for resource_name in sorted(resource_names):
        if not _exit_stack_placeholder(resource_name) or _name_store_count(resource_name) != 2:
            errors.append(
                "selected APP data coverage must initialize and assign each SQL "
                f"resource exactly once: {resource_name}."
            )

    credential_candidates = [
        (index, statement)
        for index, statement in enumerate(body)
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
        and statement.value.func.id == "DefaultAzureCredential"
    ]
    cosmos_candidates = [
        (index, statement)
        for index, statement in enumerate(body)
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
        and statement.value.func.id == "CosmosClient"
    ]
    all_credential_calls = [
        node for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "DefaultAzureCredential"
    ]
    all_cosmos_calls = [
        node for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CosmosClient"
    ]
    credential_name = ""
    cosmos_name = ""
    if (
        len(credential_candidates) != 1
        or len(cosmos_candidates) != 1
        or len(all_credential_calls) != 1
        or len(all_cosmos_calls) != 1
    ):
        errors.append(
            "selected APP data coverage requires exactly one reachable "
            "DefaultAzureCredential and CosmosClient without decoys."
        )
    else:
        credential_statement = credential_candidates[0][1]
        cosmos_statement = cosmos_candidates[0][1]
        assert isinstance(credential_statement, ast.Assign)
        assert isinstance(credential_statement.targets[0], ast.Name)
        assert isinstance(credential_statement.value, ast.Call)
        assert isinstance(cosmos_statement, ast.Assign)
        assert isinstance(cosmos_statement.targets[0], ast.Name)
        assert isinstance(cosmos_statement.value, ast.Call)
        credential_name = credential_statement.targets[0].id
        cosmos_name = cosmos_statement.targets[0].id
        credential_keywords = credential_statement.value.keywords
        client_id_names = [
            keyword.value.id
            for keyword in credential_keywords
            if keyword.arg == "managed_identity_client_id"
            and isinstance(keyword.value, ast.Name)
        ]
        client_id_name = client_id_names[0] if len(client_id_names) == 1 else ""
        client_id_assignments = [
            statement
            for statement in before_try
            if isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == client_id_name
            and isinstance(statement.value, ast.Constant)
            and statement.value.value == "$DATA_DEPLOY_IDENTITY_CLIENT_ID"
        ]
        cosmos_keywords = {
            keyword.arg: keyword.value for keyword in cosmos_statement.value.keywords
        }
        cosmos_credential = cosmos_keywords.get("credential")
        if (
            credential_statement.value.args
            or len(credential_keywords) != 1
            or len(client_id_assignments) != 1
            or _name_store_count(client_id_name) != 1
            or len(cosmos_statement.value.args) != 1
            or not _asdw_python_env_value(
                cosmos_statement.value.args[0], "COSMOS_ENDPOINT"
            )
            or not isinstance(cosmos_credential, ast.Name)
            or cosmos_credential.id != credential_name
        ):
            errors.append(
                "selected APP data coverage must bind its one CosmosClient and "
                "credential to DATA_DEPLOY_IDENTITY_CLIENT_ID."
            )
        for resource_name in (credential_name, cosmos_name):
            if (
                not resource_name
                or not _exit_stack_placeholder(resource_name)
                or _name_store_count(resource_name) != 2
            ):
                errors.append(
                    "selected APP data coverage must initialize and assign each "
                    "Cosmos resource exactly once."
                )

    container_name = ""
    container_candidates: List[Tuple[int, ast.Assign]] = []
    if cosmos_name:
        for index, statement in enumerate(body):
            if not (
                isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
                and isinstance(statement.value, ast.Call)
                and isinstance(statement.value.func, ast.Attribute)
                and statement.value.func.attr == "get_container_client"
                and len(statement.value.args) == 1
                and not statement.value.keywords
                and _asdw_python_env_value(
                    statement.value.args[0], "COSMOS_CONTAINER_VOC"
                )
                and isinstance(statement.value.func.value, ast.Call)
            ):
                continue
            database_call = statement.value.func.value
            if not (
                isinstance(database_call.func, ast.Attribute)
                and database_call.func.attr == "get_database_client"
                and isinstance(database_call.func.value, ast.Name)
                and database_call.func.value.id == cosmos_name
                and len(database_call.args) == 1
                and not database_call.keywords
                and _asdw_python_env_value(
                    database_call.args[0], "COSMOS_DATABASE"
                )
            ):
                continue
            container_candidates.append((index, statement))
    database_client_calls = [
        node for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get_database_client"
    ]
    container_client_calls = [
        node for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get_container_client"
    ]
    if (
        len(container_candidates) != 1
        or len(database_client_calls) != 1
        or len(container_client_calls) != 1
    ):
        errors.append(
            "selected APP data coverage must derive exactly one VocRecord "
            "container from its canonical CosmosClient."
        )
    else:
        container_target = container_candidates[0][1].targets[0]
        assert isinstance(container_target, ast.Name)
        container_name = container_target.id
        if _name_store_count(container_name) != 1:
            errors.append(
                "selected APP data coverage must not reassign its VocRecord container."
            )

    direct_execute_calls = [
        statement.value
        for statement in body
        if isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Attribute)
        and statement.value.func.attr == "execute"
    ]
    all_execute_calls = [
        node for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
    ]
    if {id(call) for call in all_execute_calls} != {
        id(call) for call in direct_execute_calls
    }:
        errors.append(
            "selected APP data coverage must keep every SQL execute call as a "
            "direct top-level-try statement."
        )

    allowed_exit_ids: set[int] = set()
    for statement in body:
        if not isinstance(statement, ast.Expr) or not isinstance(
            statement.value, ast.BoolOp
        ):
            continue
        if not statement.value.values or not isinstance(
            statement.value.values[0], ast.Compare
        ):
            continue
        comparison = statement.value.values[0]
        if not isinstance(comparison.left, ast.Name):
            continue
        guard = _asdw_direct_count_guard(statement, comparison.left.id)
        if guard is not None:
            allowed_exit_ids.add(id(guard[1]))

    canonical_count_names: set[str] = set()
    for entity, database, table_name in _ASDW_APP009_SQL_COVERAGE:
        cursor_record = cursor_by_database.get(database)
        if cursor_record is None:
            continue
        cursor_name, _cursor_index = cursor_record
        query = f"SELECT COUNT_BIG(*) FROM [dbo].[{table_name}]"
        query_indexes = [
            index
            for index, statement in enumerate(body)
            if isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Attribute)
            and statement.value.func.attr == "execute"
            and isinstance(statement.value.func.value, ast.Name)
            and statement.value.func.value.id == cursor_name
            and len(statement.value.args) == 1
            and not statement.value.keywords
            and isinstance(statement.value.args[0], ast.Constant)
            and statement.value.args[0].value == query
        ]
        if len(query_indexes) != 1:
            errors.append(
                "selected APP data coverage must bind "
                f"{entity} to ${database}/dbo.{table_name}."
            )
            continue
        query_index = query_indexes[0]
        if query_index + 1 >= len(body):
            errors.append(
                f"selected APP data coverage must fetch {entity} immediately."
            )
            continue
        fetch_statement = body[query_index + 1]
        if not (
            isinstance(fetch_statement, ast.Assign)
            and len(fetch_statement.targets) == 1
            and isinstance(fetch_statement.targets[0], ast.Name)
            and isinstance(fetch_statement.value, ast.Subscript)
            and isinstance(fetch_statement.value.value, ast.Call)
            and isinstance(fetch_statement.value.value.func, ast.Attribute)
            and fetch_statement.value.value.func.attr == "fetchone"
            and isinstance(fetch_statement.value.value.func.value, ast.Name)
            and fetch_statement.value.value.func.value.id == cursor_name
            and not fetch_statement.value.value.args
            and not fetch_statement.value.value.keywords
            and isinstance(fetch_statement.value.slice, ast.Constant)
            and fetch_statement.value.slice.value == 0
        ):
            errors.append(
                f"selected APP data coverage must fetch {entity} immediately."
            )
            continue
        count_name = fetch_statement.targets[0].id
        canonical_count_names.add(count_name)
        if _name_store_count(count_name) != 1:
            errors.append(
                f"selected APP data coverage must not reassign {entity} count."
            )
        guards = [
            (index, guard)
            for index, statement in enumerate(body)
            for guard in [_asdw_direct_count_guard(statement, count_name)]
            if guard is not None
        ]
        expected = counts.get(entity)
        if (
            len(guards) != 1
            or guards[0][0] <= query_index + 1
            or (expected is not None and guards[0][1][0] != expected)
        ):
            errors.append(
                "selected APP data coverage must validate "
                f"{entity} with the sample-data expected count."
            )
        emits = [
            index
            for index, statement in enumerate(body)
            if isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "print"
            and len(statement.value.args) == 1
            and isinstance(statement.value.args[0], ast.Call)
            and isinstance(statement.value.args[0].func, ast.Name)
            and statement.value.args[0].func.id == "int"
            and len(statement.value.args[0].args) == 1
            and isinstance(statement.value.args[0].args[0], ast.Name)
            and statement.value.args[0].args[0].id == count_name
        ]
        if len(emits) != 1 or emits[0] <= query_index + 1:
            errors.append(
                f"selected APP data coverage must emit the executed {entity} count."
            )

    query_item_calls = [
        node for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "query_items"
    ]
    cosmos_count_name = ""
    cosmos_count_index = -1
    if len(query_item_calls) == 1 and container_name:
        query_item_call = query_item_calls[0]
        query_item_receiver = (
            query_item_call.func.value
            if isinstance(query_item_call.func, ast.Attribute)
            else None
        )
        query_keywords = {
            keyword.arg: keyword.value for keyword in query_item_call.keywords
        }
        query_value = query_keywords.get("query")
        cross_partition_value = query_keywords.get(
            "enable_cross_partition_query"
        )
        for index, statement in enumerate(body):
            if not (
                isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
                and isinstance(statement.value, ast.Subscript)
                and isinstance(statement.value.value, ast.Call)
                and isinstance(statement.value.value.func, ast.Name)
                and statement.value.value.func.id == "list"
                and len(statement.value.value.args) == 1
                and not statement.value.value.keywords
                and statement.value.value.args[0] is query_item_call
                and isinstance(query_item_receiver, ast.Name)
                and query_item_receiver.id == container_name
                and isinstance(statement.value.slice, ast.Constant)
                and statement.value.slice.value == 0
            ):
                continue
            if not (
                isinstance(query_value, ast.Constant)
                and query_value.value == "SELECT VALUE COUNT(1) FROM c"
                and len(query_keywords) == 2
                and isinstance(cross_partition_value, ast.Constant)
                and cross_partition_value.value is True
            ):
                continue
            cosmos_count_name = statement.targets[0].id
            cosmos_count_index = index
            break
    if not cosmos_count_name or _name_store_count(cosmos_count_name) != 1:
        errors.append(
            "selected APP data coverage must execute exactly one canonical VocRecord count."
        )
    else:
        canonical_count_names.add(cosmos_count_name)
        cosmos_guards = [
            (index, guard)
            for index, statement in enumerate(body)
            for guard in [_asdw_direct_count_guard(statement, cosmos_count_name)]
            if guard is not None
        ]
        expected_voc = counts.get("VocRecord")
        if (
            len(cosmos_guards) != 1
            or cosmos_guards[0][0] <= cosmos_count_index
            or (expected_voc is not None and cosmos_guards[0][1][0] != expected_voc)
        ):
            errors.append(
                "selected APP data coverage must validate VocRecord with the "
                "sample-data expected count."
            )
        cosmos_emits = [
            index
            for index, statement in enumerate(body)
            if isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "print"
            and len(statement.value.args) == 1
            and isinstance(statement.value.args[0], ast.Call)
            and isinstance(statement.value.args[0].func, ast.Name)
            and statement.value.args[0].func.id == "int"
            and len(statement.value.args[0].args) == 1
            and isinstance(statement.value.args[0].args[0], ast.Name)
            and statement.value.args[0].args[0].id == cosmos_count_name
        ]
        if len(cosmos_emits) != 1 or cosmos_emits[0] <= cosmos_count_index:
            errors.append(
                "selected APP data coverage must emit the executed VocRecord count."
            )

    audit_count_candidates: List[str] = []
    if audit_mode == _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST:
        svc12_cursor_record = cursor_by_database.get("SQL_DB_SVC12")
        if svc12_cursor_record is not None:
            svc12_cursor_name = svc12_cursor_record[0]
            for index, statement in enumerate(body[1:], start=1):
                previous = body[index - 1]
                if not (
                    isinstance(previous, ast.Expr)
                    and isinstance(previous.value, ast.Call)
                    and isinstance(previous.value.func, ast.Attribute)
                    and previous.value.func.attr == "execute"
                    and isinstance(previous.value.func.value, ast.Name)
                    and previous.value.func.value.id == svc12_cursor_name
                    and len(previous.value.args) == 1
                    and isinstance(previous.value.args[0], ast.JoinedStr)
                    and isinstance(statement, ast.Assign)
                    and len(statement.targets) == 1
                    and isinstance(statement.targets[0], ast.Name)
                    and isinstance(statement.value, ast.Subscript)
                    and isinstance(statement.value.value, ast.Call)
                    and isinstance(statement.value.value.func, ast.Attribute)
                    and statement.value.value.func.attr == "fetchone"
                    and isinstance(statement.value.value.func.value, ast.Name)
                    and statement.value.value.func.value.id == svc12_cursor_name
                    and isinstance(statement.value.slice, ast.Constant)
                    and statement.value.slice.value == 0
                ):
                    continue
                audit_count_candidates.append(statement.targets[0].id)
    else:
        for statement in body:
            if not (
                isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
                and isinstance(statement.value, ast.Call)
                and isinstance(statement.value.func, ast.Name)
                and statement.value.func.id == "sum"
                and len(statement.value.args) == 1
                and isinstance(statement.value.args[0], ast.GeneratorExp)
            ):
                continue
            audit_count_candidates.append(statement.targets[0].id)
    if len(audit_count_candidates) == 1:
        canonical_count_names.add(audit_count_candidates[0])

    all_exit_calls = [
        node for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "sys"
        and node.func.attr == "exit"
    ]
    if any(id(call) not in allowed_exit_ids for call in all_exit_calls) or any(
        isinstance(node, ast.Raise) for node in ast.walk(program)
    ):
        errors.append(
            "selected APP data coverage permits only direct positive-count "
            "mismatch guards and no separate exit or raise path."
        )

    expected_audit = counts.get("AuditRecord")
    if audit_mode == _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST:
        errors.extend(_validate_asdw_sql_audit_count(source, expected_audit))
        errors.extend(_validate_asdw_sql_audit_metadata(source))
    else:
        errors.extend(_validate_asdw_acl_direct_count(source, expected_audit))

    ledger_certificate_directory_name = ""
    ledger_certificate_path_name = ""
    if audit_mode == _ASDW_AUDIT_MODE_ACL_DIRECT:
        ledger_name = ""
        ledger_assignments = [
            statement
            for statement in body
            if isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "ConfidentialLedgerClient"
        ]
        if len(ledger_assignments) == 1:
            ledger_target = ledger_assignments[0].targets[0]
            assert isinstance(ledger_target, ast.Name)
            ledger_name = ledger_target.id
            resource_names.add(ledger_name)
        certificate_directory_assignments = [
            statement
            for statement in body
            if isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "TemporaryDirectory"
            and not statement.value.args
            and not statement.value.keywords
        ]
        certificate_path_assignments = [
            statement
            for statement in body
            if isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.BinOp)
            and isinstance(statement.value.op, ast.Add)
            and isinstance(statement.value.left, ast.Attribute)
            and isinstance(statement.value.left.value, ast.Name)
            and statement.value.left.attr == "name"
            and isinstance(statement.value.right, ast.Constant)
            and statement.value.right.value == "/ledger_certificate.pem"
        ]
        if (
            len(certificate_directory_assignments) == 1
            and len(certificate_path_assignments) == 1
        ):
            certificate_directory_target = certificate_directory_assignments[0].targets[0]
            certificate_path_target = certificate_path_assignments[0].targets[0]
            assert isinstance(certificate_directory_target, ast.Name)
            assert isinstance(certificate_path_target, ast.Name)
            ledger_certificate_directory_name = certificate_directory_target.id
            ledger_certificate_path_name = certificate_path_target.id
            certificate_path_value = certificate_path_assignments[0].value
            assert isinstance(certificate_path_value, ast.BinOp)
            assert isinstance(certificate_path_value.left, ast.Attribute)
            assert isinstance(certificate_path_value.left.value, ast.Name)
            if (
                certificate_path_value.left.value.id
                != ledger_certificate_directory_name
                or not _exit_stack_placeholder(ledger_certificate_directory_name)
                or _name_store_count(ledger_certificate_directory_name) != 2
                or _name_store_count(ledger_certificate_path_name) != 1
            ):
                errors.append(
                    "selected APP data coverage must derive one fresh ledger TLS "
                    "certificate path from TemporaryDirectory."
                )
            resource_names.add(ledger_certificate_directory_name)
        else:
            errors.append(
                "selected APP data coverage must derive one fresh ledger TLS "
                "certificate path from TemporaryDirectory."
            )
    else:
        ledger_name = ""

    resource_names.update(name for name in (credential_name, cosmos_name) if name)
    expected_methods: Dict[str, List[str]] = {}
    entity_count_by_database: Dict[str, int] = {}
    for _entity, database, _table in _ASDW_APP009_SQL_COVERAGE:
        entity_count_by_database[database] = (
            entity_count_by_database.get(database, 0) + 1
        )
    for database, (connection_name, _connection_index) in connection_records.items():
        expected_methods[connection_name] = ["cursor", "close"]
        cursor_record = cursor_by_database.get(database)
        if cursor_record is None:
            continue
        cursor_name, _cursor_index = cursor_record
        if database == "SQL_DB_SVC12":
            expected_methods[cursor_name] = [
                "execute",
                "execute",
                "execute",
                "fetchone",
                "fetchall",
                "fetchall",
                "close",
            ]
        else:
            entity_count = entity_count_by_database.get(database, 0)
            expected_methods[cursor_name] = (
                ["execute"] * entity_count
                + ["fetchone"] * entity_count
                + ["close"]
            )
    if credential_name:
        expected_methods[credential_name] = ["close"]
    if cosmos_name:
        expected_methods[cosmos_name] = ["get_database_client", "close"]
    if container_name:
        expected_methods[container_name] = ["query_items"]
    if ledger_name:
        expected_methods[ledger_name] = ["list_ledger_entries", "close"]
    if ledger_certificate_directory_name:
        expected_methods[ledger_certificate_directory_name] = ["cleanup"]

    def _literal_assignment(name: str) -> Any:
        candidates = [
            statement.value
            for statement in before_try
            if isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == name
        ]
        if len(candidates) != 1 or _name_store_count(name) != 1:
            return None
        try:
            return ast.literal_eval(candidates[0])
        except (ValueError, TypeError):
            return None

    status_by_result_safe = _literal_assignment("status_by_result") == {
        (True, False): "[CRITICAL]",
        (False, True): "[OK]",
        (False, False): "[FAIL]",
    }
    binary_status_safe = _literal_assignment("binary_status") == (
        "[FAIL]",
        "[OK]",
    )

    def _one_direct_assignment(name: str) -> Optional[ast.AST]:
        values = [
            statement.value
            for statement in body
            if isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == name
        ]
        return values[0] if len(values) == 1 and _name_store_count(name) == 1 else None

    audit_ledger_type_value = _one_direct_assignment("audit_ledger_type")
    audit_ledger_type_safe = bool(
        isinstance(audit_ledger_type_value, ast.Call)
        and isinstance(audit_ledger_type_value.func, ast.Attribute)
        and isinstance(audit_ledger_type_value.func.value, ast.Name)
        and audit_ledger_type_value.func.value.id == "audit_table_types"
        and audit_ledger_type_value.func.attr == "get"
        and len(audit_ledger_type_value.args) == 2
        and not audit_ledger_type_value.keywords
        and isinstance(audit_ledger_type_value.args[0], ast.Tuple)
        and len(audit_ledger_type_value.args[0].elts) == 2
        and isinstance(audit_ledger_type_value.args[0].elts[0], ast.Constant)
        and audit_ledger_type_value.args[0].elts[0].value == "dbo"
        and isinstance(audit_ledger_type_value.args[0].elts[1], ast.Name)
        and audit_ledger_type_value.args[0].elts[1].id == "audit_table"
        and isinstance(audit_ledger_type_value.args[1], ast.Constant)
        and audit_ledger_type_value.args[1].value == ""
    )

    def _binary_status_assignment(name: str, condition_name: str) -> bool:
        value = _one_direct_assignment(name)
        return bool(
            binary_status_safe
            and isinstance(value, ast.Subscript)
            and isinstance(value.value, ast.Name)
            and value.value.id == "binary_status"
            and isinstance(value.slice, ast.Name)
            and value.slice.id == condition_name
        )

    audit_ledger_status_safe = _binary_status_assignment(
        "audit_ledger_status",
        "audit_ledger_ok",
    )
    digest_status_safe = _binary_status_assignment(
        "digest_status",
        "digest_ready",
    )

    protected_alias_roots = set(expected_methods) | protected_names

    def _aliases_protected_object(node: Optional[ast.AST]) -> bool:
        if isinstance(node, ast.Name):
            return node.id in protected_alias_roots
        if isinstance(node, ast.Attribute):
            return _aliases_protected_object(node.value)
        if isinstance(node, ast.Subscript):
            if (
                isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "os"
                and node.value.attr == "environ"
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
            ):
                return False
            return _aliases_protected_object(node.value)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return any(_aliases_protected_object(item) for item in node.elts)
        if isinstance(node, ast.Dict):
            return any(
                key is not None and _aliases_protected_object(key)
                for key in node.keys
            ) or any(_aliases_protected_object(value) for value in node.values)
        if isinstance(node, ast.IfExp):
            return _aliases_protected_object(node.body) or _aliases_protected_object(
                node.orelse
            )
        if isinstance(node, ast.BoolOp):
            return any(_aliases_protected_object(value) for value in node.values)
        if isinstance(node, ast.NamedExpr):
            return _aliases_protected_object(node.value)
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            return _aliases_protected_object(node.elt) or any(
                _aliases_protected_object(generator.iter)
                or any(
                    _aliases_protected_object(condition)
                    for condition in generator.ifs
                )
                for generator in node.generators
            )
        if isinstance(node, ast.DictComp):
            return (
                _aliases_protected_object(node.key)
                or _aliases_protected_object(node.value)
                or any(
                    _aliases_protected_object(generator.iter)
                    or any(
                        _aliases_protected_object(condition)
                        for condition in generator.ifs
                    )
                    for generator in node.generators
                )
            )
        if isinstance(node, ast.Starred):
            return _aliases_protected_object(node.value)
        return False

    protected_alias_assignments: List[ast.AST] = []
    for node in ast.walk(program):
        assignment_value: Optional[ast.AST] = None
        if isinstance(node, ast.Assign):
            assignment_value = node.value
        elif isinstance(node, ast.AnnAssign):
            assignment_value = node.value
        elif isinstance(node, ast.NamedExpr):
            assignment_value = node.value
        if assignment_value is not None and _aliases_protected_object(
            assignment_value
        ):
            protected_alias_assignments.append(node)
    protected_target_mutations = [
        node
        for node in ast.walk(program)
        if isinstance(node, (ast.Attribute, ast.Subscript))
        and isinstance(node.ctx, (ast.Store, ast.Del))
    ]
    if protected_alias_assignments or protected_target_mutations:
        errors.append(
            "selected APP data coverage must not alias or mutate protected "
            "runtime, environment, SDK, or bound data-plane resources."
        )

    sensitive_data_plane_methods = {
        "execute",
        "executemany",
        "callproc",
        "commit",
        "rollback",
        "query_items",
        "create_item",
        "upsert_item",
        "replace_item",
        "patch_item",
        "delete_item",
        "execute_item_batch",
        "list_ledger_entries",
        "begin_create_ledger_entry",
        "create_ledger_entry",
    }
    indirect_data_plane_calls = [
        node
        for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in sensitive_data_plane_methods
        and (
            not isinstance(node.func.value, ast.Name)
            or node.func.value.id not in expected_methods
        )
    ]
    if indirect_data_plane_calls:
        errors.append(
            "selected APP data coverage permits only canonical direct receivers "
            "for SQL, Cosmos, and confidential ledger data-plane calls."
        )

    def _canonical_container_client_call(call: ast.Call) -> bool:
        if not (
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "get_container_client"
            and isinstance(call.func.value, ast.Call)
        ):
            return False
        database_call = call.func.value
        return bool(
            isinstance(database_call.func, ast.Attribute)
            and database_call.func.attr == "get_database_client"
            and isinstance(database_call.func.value, ast.Name)
            and database_call.func.value.id == cosmos_name
        )

    def _approved_name_call(call: ast.Call) -> bool:
        assert isinstance(call.func, ast.Name)
        name = call.func.id
        if name == "ExitStack":
            return not call.args and not call.keywords
        if name == "connect":
            return len(call.args) == 1 and not call.keywords
        if name == "DefaultAzureCredential":
            return bool(
                not call.args
                and len(call.keywords) == 1
                and call.keywords[0].arg == "managed_identity_client_id"
                and isinstance(call.keywords[0].value, ast.Name)
            )
        if name == "TemporaryDirectory":
            return bool(
                audit_mode == _ASDW_AUDIT_MODE_ACL_DIRECT
                and not call.args
                and not call.keywords
            )
        if name == "CosmosClient":
            return bool(
                len(call.args) == 1
                and len(call.keywords) == 1
                and call.keywords[0].arg == "credential"
                and isinstance(call.keywords[0].value, ast.Name)
            )
        if name == "print":
            if len(call.args) != 1 or call.keywords:
                return False
            argument = call.args[0]
            if (
                isinstance(argument, ast.Call)
                and isinstance(argument.func, ast.Name)
                and argument.func.id == "int"
            ):
                return _approved_name_call(argument)
            if not isinstance(argument, ast.JoinedStr):
                return False
            safe_status_names = set(canonical_count_names)
            if audit_ledger_status_safe:
                safe_status_names.add("audit_ledger_status")
            if audit_ledger_type_safe:
                safe_status_names.add("audit_ledger_type")
            if digest_status_safe:
                safe_status_names.add("digest_status")

            def _safe_formatted_value(value: ast.AST) -> bool:
                if isinstance(value, ast.Name):
                    return value.id in safe_status_names
                if not (
                    isinstance(value, ast.Subscript)
                    and isinstance(value.value, ast.Name)
                    and value.value.id == "status_by_result"
                    and status_by_result_safe
                    and isinstance(value.slice, ast.Tuple)
                    and len(value.slice.elts) == 2
                ):
                    return False
                compared_names: List[str] = []
                for comparison in value.slice.elts:
                    if not (
                        isinstance(comparison, ast.Compare)
                        and isinstance(comparison.left, ast.Name)
                        and comparison.left.id in canonical_count_names
                        and len(comparison.ops) == 1
                        and isinstance(comparison.ops[0], ast.Eq)
                        and len(comparison.comparators) == 1
                        and isinstance(comparison.comparators[0], ast.Constant)
                        and isinstance(comparison.comparators[0].value, int)
                    ):
                        return False
                    compared_names.append(comparison.left.id)
                return len(set(compared_names)) == 1

            return all(
                isinstance(value, ast.Constant)
                and isinstance(value.value, str)
                or (
                    isinstance(value, ast.FormattedValue)
                    and value.conversion == -1
                    and value.format_spec is None
                    and _safe_formatted_value(value.value)
                )
                for value in argument.values
            )
        if name == "int":
            return bool(
                len(call.args) == 1
                and not call.keywords
                and isinstance(call.args[0], ast.Name)
                and call.args[0].id in canonical_count_names
            )
        if name == "str":
            return bool(
                len(call.args) == 1
                and not call.keywords
                and isinstance(call.args[0], ast.Subscript)
                and isinstance(call.args[0].value, ast.Name)
                and call.args[0].value.id == "row"
                and isinstance(call.args[0].slice, ast.Constant)
                and call.args[0].slice.value in {0, 1, 2}
            )
        if name == "urlparse":
            if len(call.args) != 1 or call.keywords:
                return False
            argument = call.args[0]
            return bool(
                _asdw_python_env_value(argument, "COSMOS_ENDPOINT")
                or _asdw_python_env_value(
                    argument, "CONFIDENTIAL_LEDGER_ENDPOINT"
                )
                or (
                    isinstance(argument, ast.Call)
                    and isinstance(argument.func, ast.Name)
                    and argument.func.id == "str"
                )
            )
        if name == "ConfidentialLedgerClient":
            if not (
                audit_mode == _ASDW_AUDIT_MODE_ACL_DIRECT
                and not call.args
                and {keyword.arg for keyword in call.keywords}
                == {"endpoint", "credential", "ledger_certificate_path"}
            ):
                return False
            keyword_values = {
                keyword.arg: keyword.value for keyword in call.keywords
            }
            certificate_value = keyword_values["ledger_certificate_path"]
            return bool(
                isinstance(certificate_value, ast.Name)
                and certificate_value.id == ledger_certificate_path_name
            )
        if name == "filter":
            return bool(
                len(call.args) == 2
                and not call.keywords
                and isinstance(call.args[0], ast.Constant)
                and call.args[0].value is None
                and isinstance(call.args[1], ast.List)
                and len(call.args[1].elts) == 1
            )
        if name == "next":
            return bool(
                len(call.args) == 1
                and not call.keywords
                and isinstance(call.args[0], ast.Call)
                and isinstance(call.args[0].func, ast.Name)
                and call.args[0].func.id in {"filter", "iter"}
                and _approved_name_call(call.args[0])
            )
        if name == "iter":
            return bool(
                len(call.args) == 1
                and not call.keywords
                and isinstance(call.args[0], ast.Name)
                and call.args[0].id in {
                    "sql_resolved_ips",
                    "cosmos_resolved_ips",
                }
            )
        if name == "list":
            return bool(
                len(call.args) == 1
                and not call.keywords
                and isinstance(call.args[0], ast.Call)
                and isinstance(call.args[0].func, ast.Attribute)
                and call.args[0].func.attr == "query_items"
                and isinstance(call.args[0].func.value, ast.Name)
                and call.args[0].func.value.id == container_name
            )
        if name == "sum":
            return bool(
                len(call.args) == 1
                and not call.keywords
                and isinstance(call.args[0], ast.GeneratorExp)
            )
        if name == "any":
            return bool(
                len(call.args) == 1
                and not call.keywords
                and isinstance(call.args[0], ast.GeneratorExp)
            )
        if name == "set":
            return bool(
                len(call.args) == 1
                and not call.keywords
                and isinstance(call.args[0], ast.Call)
                and isinstance(call.args[0].func, ast.Attribute)
                and call.args[0].func.attr == "split"
            )
        return False

    def _socket_lookup_kind(call: ast.Call) -> str:
        if not (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "socket"
            and call.func.attr == "getaddrinfo"
            and len(call.args) == 4
            and not call.keywords
            and isinstance(call.args[1], ast.Constant)
            and isinstance(call.args[2], ast.Constant)
            and call.args[2].value == 0
            and isinstance(call.args[3], ast.Attribute)
            and isinstance(call.args[3].value, ast.Name)
            and call.args[3].value.id == "socket"
            and call.args[3].attr == "SOCK_STREAM"
        ):
            return ""
        if (
            _asdw_python_env_value(call.args[0], "SQL_HOST")
            and call.args[1].value == 1433
        ):
            return "sql"
        if (
            isinstance(call.args[0], ast.Name)
            and call.args[0].id == "cosmos_host"
            and call.args[1].value == 443
        ):
            return "cosmos"
        return ""

    def _approved_call(call: ast.Call) -> bool:
        if isinstance(call.func, ast.Name):
            return _approved_name_call(call)
        if not isinstance(call.func, ast.Attribute):
            return False
        receiver = call.func.value
        method = call.func.attr
        if method.startswith("__") or method.endswith("__"):
            return False
        if isinstance(receiver, ast.Name):
            if receiver.id in expected_methods:
                return method in expected_methods[receiver.id]
            if (receiver.id, method) == ("sys", "exit"):
                return bool(
                    len(call.args) == 1
                    and isinstance(call.args[0], ast.Constant)
                    and call.args[0].value == 1
                    and not call.keywords
                )
            if (receiver.id, method) == ("re", "fullmatch"):
                return len(call.args) == 2 and not call.keywords
            if (receiver.id, method) == ("socket", "getaddrinfo"):
                return bool(_socket_lookup_kind(call))
            if receiver.id == "audit_table_types" and method == "get":
                return bool(
                    len(call.args) == 2
                    and not call.keywords
                    and isinstance(call.args[0], ast.Tuple)
                    and len(call.args[0].elts) == 2
                    and isinstance(call.args[0].elts[0], ast.Constant)
                    and call.args[0].elts[0].value == "dbo"
                    and isinstance(call.args[0].elts[1], ast.Name)
                    and call.args[0].elts[1].id == "audit_table"
                    and isinstance(call.args[1], ast.Constant)
                    and call.args[1].value == ""
                )
            if receiver.id in {
                "sql_resolved_ips",
                "cosmos_resolved_ips",
            } and method == "issubset":
                expected_argument = (
                    "sql_private_ips"
                    if receiver.id == "sql_resolved_ips"
                    else "cosmos_private_ips"
                )
                return bool(
                    len(call.args) == 1
                    and not call.keywords
                    and isinstance(call.args[0], ast.Name)
                    and call.args[0].id == expected_argument
                )
            return False
        if (
            method == "split"
            and isinstance(receiver, ast.Subscript)
            and isinstance(receiver.slice, ast.Constant)
            and isinstance(receiver.slice.value, str)
        ):
            return _asdw_python_env_value(receiver, receiver.slice.value)
        return _canonical_container_client_call(call)

    unapproved_calls = [
        call
        for call in ast.walk(program)
        if isinstance(call, ast.Call) and not _approved_call(call)
    ]
    if unapproved_calls:
        errors.append(
            "selected APP data coverage permits only its fixed canonical "
            "read/count, validation, and cleanup calls."
        )
    socket_lookup_kinds = [
        _socket_lookup_kind(call)
        for call in ast.walk(program)
        if isinstance(call, ast.Call) and _socket_lookup_kind(call)
    ]
    if sorted(socket_lookup_kinds) not in ([], ["cosmos", "sql"]):
        errors.append(
            "selected APP data coverage permits either no DNS preflight or "
            "exactly one canonical SQL and Cosmos DNS lookup."
        )

    observed_methods: Dict[str, List[str]] = {
        name: [] for name in expected_methods
    }
    for node in ast.walk(program):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in observed_methods
        ):
            continue
        observed_methods[node.func.value.id].append(node.func.attr)
    if any(
        sorted(observed_methods[name]) != sorted(methods)
        for name, methods in expected_methods.items()
    ):
        errors.append(
            "selected APP data coverage permits only the canonical read/count "
            "and close method calls on its bound data-plane resources."
        )
    if any(
        isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and isinstance(statement.value, ast.Name)
        and statement.value.id in expected_methods
        for statement in body
    ):
        errors.append(
            "selected APP data coverage must not alias its bound data-plane resources."
        )

    direct_finalizers = [
        (statement.value.func.value.id, statement.value.func.attr)
        for statement in main_try.finalbody
        if isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Attribute)
        and statement.value.func.attr in {"close", "cleanup"}
        and isinstance(statement.value.func.value, ast.Name)
        and not statement.value.args
        and not statement.value.keywords
    ]
    expected_finalizers = [
        (
            resource_name,
            "cleanup"
            if resource_name == ledger_certificate_directory_name
            else "close",
        )
        for resource_name in resource_names
    ]
    if (
        len(direct_finalizers) != len(main_try.finalbody)
        or len(direct_finalizers) != len(expected_finalizers)
        or set(direct_finalizers) != set(expected_finalizers)
        or len(set(direct_finalizers)) != len(direct_finalizers)
        or (
            audit_mode == _ASDW_AUDIT_MODE_ACL_DIRECT
            and direct_finalizers[-3:]
            != [
                (ledger_name, "close"),
                (credential_name, "close"),
                (ledger_certificate_directory_name, "cleanup"),
            ]
        )
    ):
        errors.append(
            "selected APP data coverage must close every SQL cursor/connection, "
            "CosmosClient, DefaultAzureCredential, and selected Audit client, "
            "then clean its ledger TLS certificate directory exactly once in "
            "the same direct finally block."
        )
    return errors


def _validate_asdw_audit_mode_wiring(text: str, audit_mode: str) -> List[str]:
    """選定Audit modeのshell/ACI配線と排他性を検査する。"""
    private_branch = _extract_shell_case_branch(text, "DATA_NETWORK_MODE", "private")
    payload = _extract_asdw_private_aci_payload(text)
    if not private_branch or not payload:
        return ["AuditRecord storage mode requires one executable private ACI payload."]
    aci_commands = _find_az_commands(private_branch, "container create")
    if len(aci_commands) != 1:
        return ["AuditRecord storage mode requires exactly one private ACI create command."]
    aci_create = aci_commands[0]
    private_commands = [
        _strip_shell_inline_comment(command).strip()
        for command in _extract_shell_logical_commands(private_branch)
    ]
    first_azure_offset = _find_first_executable_az_command_offset(private_branch)

    required_keys = [
        "SQL_HOST",
        "SQL_DB_SVC01",
        "SQL_DB_SVC02",
        "SQL_DB_SVC03",
        "SQL_DB_SVC07",
        "SQL_DB_SVC09",
        "COSMOS_ENDPOINT",
        "COSMOS_DATABASE",
        "COSMOS_CONTAINER_VOC",
        "CONFIDENTIAL_LEDGER_ENDPOINT",
    ]
    transferred_keys = [
        "COSMOS_ENDPOINT",
        "COSMOS_DATABASE",
        "COSMOS_CONTAINER_VOC",
        "CONFIDENTIAL_LEDGER_ENDPOINT",
    ]
    if audit_mode == _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST:
        required_keys.extend(("SQL_DB_SVC12", "SQL_AUDIT_TABLE"))
        transferred_keys.append("SQL_AUDIT_TABLE")
    if audit_mode == _ASDW_AUDIT_MODE_ACL_DIRECT:
        required_keys.append("CONFIDENTIAL_LEDGER_COLLECTION")
        transferred_keys.append("CONFIDENTIAL_LEDGER_COLLECTION")
    errors: List[str] = []
    for key in required_keys:
        guard = f': "${{{key}:?}}"'
        guard_commands = [
            command for command in private_commands if command == guard
        ]
        guard_offset = private_branch.find(guard)
        if (
            len(guard_commands) != 1
            or guard_offset < 0
            or first_azure_offset is None
            or guard_offset >= first_azure_offset
        ):
            errors.append(
                f"AuditRecord {audit_mode} mode must require `${key}` before Azure CLI."
            )
    environment_section = aci_create.split(
        "--environment-variables", 1
    )[1].split("--command-line", 1)[0] if (
        "--environment-variables" in aci_create
        and "--command-line" in aci_create
    ) else ""
    for key in transferred_keys:
        assignments = re.findall(
            rf"(?<!\S){re.escape(key)}\s*=\s*(\"[^\"]*\"|'[^']*'|\S+)",
            environment_section,
        )
        if len(assignments) != 1 or assignments[0] not in {
            f'"${key}"',
            f"'${key}'",
            f"${key}",
            f'"${{{key}}}"',
            f"'${{{key}}}'",
            f"${{{key}}}",
        }:
            errors.append(
                f"AuditRecord {audit_mode} mode must pass `${key}` into the private ACI."
            )

    for option, value in (
        ("--restart-policy", "Never"),
        ("--os-type", "Linux"),
        ("--cpu", "1"),
        ("--memory", "1"),
    ):
        option_count = len(
            re.findall(rf"(?<!\S){re.escape(option)}(?=\s|=)", aci_create)
        )
        exact_count = len(
            re.findall(
                rf"(?<!\S){re.escape(option)}(?:\s+|=)"
                rf"(?:{re.escape(value)}|\"{re.escape(value)}\"|"
                rf"'{re.escape(value)}')(?=\s|$)",
                aci_create,
            )
        )
        if option_count != 1 or exact_count != 1:
            errors.append(
                f"AuditRecord {audit_mode} mode private ACI must set "
                f"`{option} {value}` exactly once."
            )

    source, envelope_error = _extract_asdw_known_mode_python_source(
        payload,
        audit_mode,
    )
    if envelope_error is not None:
        return errors + [envelope_error]
    try:
        program = ast.parse(source)
    except SyntaxError:
        return errors + [
            "AuditRecord storage mode requires one parseable private Python payload."
        ]
    acl_inventory = [
        node
        for node in ast.walk(program)
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "azure.confidentialledger"
        )
        or (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ConfidentialLedgerClient"
        )
        or (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "list_ledger_entries"
        )
        or _asdw_python_env_value(node, "CONFIDENTIAL_LEDGER_COLLECTION")
    ]
    sql_audit_inventory = [
        node
        for node in ast.walk(program)
        if _asdw_python_env_value(node, "SQL_AUDIT_TABLE")
        or (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and (
                "Database=$SQL_DB_SVC12;" in node.value
                or node.value == "APPEND_ONLY_LEDGER_TABLE"
                or node.value
                == "SELECT path, last_digest_block_id FROM "
                "sys.database_ledger_digest_locations WHERE is_current = 1"
            )
        )
    ]
    if audit_mode == _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST:
        if acl_inventory:
            errors.append(
                "AuditRecord sql-ledger-digest mode must not include ACL-direct "
                "application entry logic."
            )
    elif audit_mode == _ASDW_AUDIT_MODE_ACL_DIRECT:
        if sql_audit_inventory:
            errors.append(
                "AuditRecord acl-direct mode must not include SQL ledger AuditRecord logic."
            )

    private_assignments = [
        command
        for command in _extract_shell_logical_commands(private_branch)
        if _is_generated_shell_assignment(command, "aci_command")
    ]
    outside_private = private_branch
    if len(private_assignments) == 1:
        outside_private = outside_private.replace(private_assignments[0], "", 1)
    case_end = re.search(r"(?m)^\s*esac\b", text)
    after_case = text[case_end.end():] if case_end is not None else ""
    outside_lines = "\n".join(
        _strip_shell_inline_comment(line)
        for line in (outside_private + "\n" + after_case).splitlines()
        if not line.lstrip().startswith("#")
    )
    forbidden_execution = re.search(
        r"(?m)^\s*(?:command|env|exec|nohup|nice|time)\b|"
        r"^\s*(?:(?:[A-Za-z_][A-Za-z0-9_]*=)?\$\()?"
        r"(?:python3?|bash|sh|eval|source|curl|wget|sqlcmd)\b|"
        r"^\s*\.\s+\S+|^\s*(?:\./|/)[^\s]+|"
        r"^\s*[A-Za-z0-9_.]+-[A-Za-z0-9_.-]*(?:\s|$)|"
        r"^\s*[A-Za-z0-9_.-]+\.(?:sh|py)(?:\s|$)",
        outside_lines,
    )
    if forbidden_execution:
        errors.append(
            "AuditRecord storage mode must keep SDK/data-plane script execution "
            "inside the private ACI payload only."
        )
    after_case_commands = [
        _strip_shell_inline_comment(command)
        for command in _extract_shell_logical_commands(after_case)
    ]
    azure_write_verb = re.compile(
        r"\b(?:create|update|delete|set|add|remove|assign|unassign|grant|"
        r"revoke|start|stop|restart|restore|import|export|failover)\b",
        re.IGNORECASE,
    )
    if any(
        re.search(r"\baz\b", command)
        and azure_write_verb.search(_mask_generated_query_argument(command))
        for command in after_case_commands
    ):
        errors.append(
            "AuditRecord verifier must not execute Azure create/update/delete "
            "or other mutation commands after the network-mode case."
        )
    rest_commands = [
        command
        for command in after_case_commands
        if re.search(r"\baz\s+rest\b", command)
    ]
    invalid_rest_command = False
    for command in rest_commands:
        rest_calls = re.findall(r"\baz\s+rest\b", command)
        method_options = re.findall(
            r"--method(?:\s+|=)(\"[^\"]+\"|'[^']+'|[^\s;&|]+)",
            command,
            re.IGNORECASE,
        )
        normalized_methods = [method.strip("\"'").upper() for method in method_options]
        if (
            len(rest_calls) != 1
            or len(method_options) != 1
            or normalized_methods[0] not in {"GET", "HEAD"}
            or _has_unquoted_shell_control_operator(command)
        ):
            invalid_rest_command = True
            break
    if invalid_rest_command:
        errors.append(
            "AuditRecord verifier permits only explicit Azure REST GET/HEAD "
            "methods in one direct command after the network-mode case."
        )
    if re.search(r"(?m)^\s*case\b.*\bin\s*(?:#.*)?$", after_case):
        errors.append(
            "AuditRecord verifier must not dispatch a second shell case after "
            "the canonical network-mode case."
        )
    return errors


def _validate_asdw_non_private_branches(text: str) -> List[str]:
    """Require public/nsp/blocked to fail closed without route attempts."""
    errors: List[str] = []
    for mode in ("public", "nsp", "blocked"):
        branch = _extract_shell_case_branch(text, "DATA_NETWORK_MODE", mode)
        visible = "\n".join(
            _strip_shell_inline_comment(line).strip()
            for line in branch.splitlines()
            if _strip_shell_inline_comment(line).strip()
        )
        if re.fullmatch(
            r"printf[ \t]+'\[ERROR\][^'\r\n]*(?:\\n)?'[ \t]+>&2\n"
            r"exit[ \t]+1",
            visible,
        ) is None:
            errors.append(
                f"{mode} mode must contain only one static [ERROR] printf to "
                "stderr followed by direct exit 1."
            )
    return errors


def _validate_asdw_network_case_contract(text: str) -> List[str]:
    """Validate the outer DATA_NETWORK_MODE case selector and clause inventory."""
    case_matches = list(
        re.finditer(
            r"(?m)^\s*case\s+(?P<selector>[^\r\n]+?)\s+in\s*(?:#.*)?$",
            text,
        )
    )
    network_cases = [
        match
        for match in case_matches
        if "DATA_NETWORK_MODE" in match.group("selector")
    ]
    if len(network_cases) != 1:
        return [
            "network-mode verifier requires exactly one direct DATA_NETWORK_MODE case."
        ]
    network_case = network_cases[0]
    if re.fullmatch(
        r'"\$\{DATA_NETWORK_MODE:\?\}"',
        network_case.group("selector").strip(),
    ) is None:
        return [
            "network-mode case selector must be one direct DATA_NETWORK_MODE expansion."
        ]
    tail = text[network_case.end():]
    esac_match = re.search(r"(?m)^\s*esac\s*(?:#.*)?$", tail)
    if esac_match is None:
        return ["network-mode case must terminate with one direct esac."]
    case_body = tail[:esac_match.start()]
    patterns: List[str] = []
    invalid_header = False
    for command in _extract_shell_logical_commands(case_body):
        if _is_generated_shell_assignment(command, "aci_command"):
            continue
        stripped = _strip_shell_inline_comment(command).strip()
        if not stripped or re.match(
            r"^(?:function\s+)?[A-Za-z_][A-Za-z0-9_]*\s*\(\)\s*\{",
            stripped,
        ):
            continue
        header = re.match(
            r"^(?P<pattern>[^\s()]+)\)(?P<suffix>.*)$",
            stripped,
            re.DOTALL,
        )
        if header is not None:
            patterns.append(header.group("pattern"))
            if header.group("suffix").strip():
                invalid_header = True
            continue
        first_word = stripped.split(None, 1)[0]
        if ")" in first_word:
            invalid_header = True
    canonical = {"private", "public", "nsp", "blocked"}
    if (
        invalid_header
        or any(pattern not in canonical | {"*"} for pattern in patterns)
        or any(patterns.count(pattern) != 1 for pattern in canonical)
        or patterns.count("*") != 1
        or patterns[-1] != "*"
    ):
        return [
            "network-mode case requires private/public/nsp/blocked exactly once "
            "and one mandatory final wildcard failure clause."
        ]
    wildcard = _extract_shell_case_branch(text, "DATA_NETWORK_MODE", "*")
    visible = "\n".join(
        _strip_shell_inline_comment(line).strip()
        for line in wildcard.splitlines()
        if _strip_shell_inline_comment(line).strip()
    )
    if re.fullmatch(
        r"printf[ \t]+'\[ERROR\][^'\r\n]*(?:\\n)?'[ \t]+>&2\n"
        r"exit[ \t]+1",
        visible,
    ) is None:
        return [
            "network-mode wildcard clause must contain only static failure output "
            "and direct exit 1."
        ]
    return []


def _validate_asdw_selected_data_coverage(
    text: str,
    sample_data_path: "Path | str | None",
    audit_mode: Optional[str] = None,
    sample_data_text: Optional[str] = None,
) -> List[str]:
    """Require APP-009 private payload coverage to match sample-data exactly."""
    if sample_data_path is None:
        return []
    counts, sample_error = _load_asdw_sample_counts(
        sample_data_path,
        sample_data_text,
    )
    if sample_error is not None:
        return [sample_error]
    required_entities = {
        entity for entity, _database, _table in _ASDW_APP009_SQL_COVERAGE
    } | {"VocRecord", "AuditRecord"}
    missing_entities = sorted(required_entities - counts.keys())
    if missing_entities:
        return [
            "selected APP data coverage sample-data must contain list values for: "
            + ", ".join(missing_entities)
            + "."
        ]
    empty_entities = sorted(
        entity for entity in required_entities if counts[entity] <= 0
    )
    if empty_entities:
        return [
            "selected APP data coverage sample-data must contain at least one "
            "record for: "
            + ", ".join(empty_entities)
            + "."
        ]

    errors: List[str] = []
    payload = _extract_asdw_private_aci_payload(text)
    marker = "python -c '"
    start = payload.find(marker)
    end = payload.rfind("'")
    if start == -1 or end <= start + len(marker):
        return ["selected APP data coverage requires one executable private Python payload."]
    source = payload[start + len(marker):end]
    try:
        program = ast.parse(source)
    except SyntaxError:
        return ["selected APP data coverage private Python payload is not parseable."]

    connections: Dict[str, str] = {}
    cursors: Dict[str, str] = {}
    count_records: Dict[str, Tuple[str, str]] = {}
    pending_table_by_cursor: Dict[str, str] = {}
    guarded_counts: Dict[str, int] = {}
    cosmos_clients: set[str] = set()
    credentials: set[str] = set()

    for statement in ast.walk(program):
        if not isinstance(statement, ast.stmt):
            continue
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            value = statement.value
            if isinstance(target, ast.Name) and isinstance(value, ast.Call):
                if isinstance(value.func, ast.Name) and value.func.id == "connect" and value.args:
                    argument = value.args[0]
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                        match = re.search(r"Database=\$(SQL_DB_SVC\d+);", argument.value)
                        if match:
                            connections[target.id] = match.group(1)
                elif (
                    isinstance(value.func, ast.Attribute)
                    and value.func.attr == "cursor"
                    and isinstance(value.func.value, ast.Name)
                ):
                    cursors[target.id] = value.func.value.id
                elif isinstance(value.func, ast.Name) and value.func.id == "CosmosClient":
                    cosmos_clients.add(target.id)
                elif isinstance(value.func, ast.Name) and value.func.id == "DefaultAzureCredential":
                    credentials.add(target.id)

                fetch = value
                if isinstance(fetch.func, ast.Attribute) and fetch.func.attr == "fetchone":
                    cursor = fetch.func.value
                    if isinstance(cursor, ast.Name) and cursor.id in pending_table_by_cursor:
                        count_records[target.id] = (
                            pending_table_by_cursor[cursor.id],
                            cursor.id,
                        )
            elif (
                isinstance(target, ast.Name)
                and isinstance(value, ast.Subscript)
                and isinstance(value.value, ast.Call)
                and isinstance(value.value.func, ast.Attribute)
                and value.value.func.attr == "fetchone"
                and isinstance(value.value.func.value, ast.Name)
            ):
                cursor_name = value.value.func.value.id
                if cursor_name in pending_table_by_cursor:
                    count_records[target.id] = (
                        pending_table_by_cursor[cursor_name],
                        cursor_name,
                    )

        if (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Attribute)
            and statement.value.func.attr == "execute"
            and isinstance(statement.value.func.value, ast.Name)
            and statement.value.args
        ):
            query = statement.value.args[0]
            if isinstance(query, ast.Constant) and isinstance(query.value, str):
                table_match = re.search(
                    r"SELECT\s+COUNT_BIG\(\*\)\s+FROM\s+\[dbo\]\.\[([A-Za-z_][A-Za-z0-9_]*)\]",
                    query.value,
                    re.IGNORECASE,
                )
                if table_match:
                    pending_table_by_cursor[statement.value.func.value.id] = (
                        table_match.group(1)
                    )

        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.BoolOp):
            values = statement.value.values
            if isinstance(statement.value.op, ast.Or) and len(values) == 2:
                comparison, failure = values
                if (
                    isinstance(comparison, ast.Compare)
                    and len(comparison.ops) == 1
                    and isinstance(comparison.ops[0], ast.Eq)
                    and isinstance(comparison.left, ast.Name)
                    and len(comparison.comparators) == 1
                    and isinstance(comparison.comparators[0], ast.Constant)
                    and isinstance(comparison.comparators[0].value, int)
                    and isinstance(failure, ast.Call)
                    and isinstance(failure.func, ast.Attribute)
                    and isinstance(failure.func.value, ast.Name)
                    and failure.func.value.id == "sys"
                    and failure.func.attr == "exit"
                    and failure.args
                    and isinstance(failure.args[0], ast.Constant)
                    and failure.args[0].value == 1
                ):
                    guarded_counts[comparison.left.id] = comparison.comparators[0].value

    observed_tables: Dict[str, Tuple[str, int]] = {}
    for count_name, (table, cursor_name) in count_records.items():
        connection_name = cursors.get(cursor_name, "")
        database = connections.get(connection_name, "")
        if count_name in guarded_counts:
            observed_tables[table] = (database, guarded_counts[count_name])

    for entity, database, table_name in _ASDW_APP009_SQL_COVERAGE:
        expected = counts[entity]
        if observed_tables.get(table_name) != (database, expected):
            errors.append(
                "selected APP data coverage must bind "
                f"{entity} to ${database}/dbo.{table_name} with expected count {expected}."
            )

    cosmos_count = re.search(
        r"\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*list\s*\(\s*"
        r"[A-Za-z_][A-Za-z0-9_]*\.query_items\s*\(",
        source,
    )
    if cosmos_count is None or guarded_counts.get(cosmos_count.group("name")) != counts["VocRecord"]:
        errors.append(
            "selected APP data coverage must validate VocRecord with the sample-data expected count."
        )
    if audit_mode == _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST:
        errors.extend(_validate_asdw_sql_audit_count(source, counts["AuditRecord"]))
        errors.extend(_validate_asdw_sql_audit_metadata(source))
    elif audit_mode == _ASDW_AUDIT_MODE_ACL_DIRECT:
        errors.extend(_validate_asdw_acl_direct_count(source, counts["AuditRecord"]))
    elif audit_mode is None and not _asdw_has_executable_audit_count(
        text, counts["AuditRecord"]
    ):
        errors.append(
            "selected APP data coverage must obtain AuditRecord through an "
            "executable Confidential Ledger Python count and pass it to the "
            "defined check_count function with the sample-data expected count."
        )

    required_closes = set(connections) | set(cursors) | cosmos_clients | credentials
    finally_close_sets = []
    for node in ast.walk(program):
        if not isinstance(node, ast.Try) or not node.finalbody:
            continue
        finally_close_sets.append(
            {
                child.func.value.id
                for statement in node.finalbody
                for child in ast.walk(statement)
                if isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "close"
                and isinstance(child.func.value, ast.Name)
            }
        )
    if not any(
        required_closes.issubset(close_names)
        for close_names in finally_close_sets
    ):
        errors.append(
            "selected APP data coverage must close every SQL cursor/connection, "
            "CosmosClient, and DefaultAzureCredential in the same finally block."
        )
    return errors


def _validate_asdw_private_verify_capability(text: str) -> List[str]:
    """Validate the deterministic private verifier wiring without Azure I/O."""
    errors: List[str] = []
    if not _has_leading_fail_fast_shell_options(text):
        errors.append(
            "private-aware verifier must enable `set -euo pipefail` before "
            "executing topology checks."
        )
    if _has_unapproved_pre_case_statement(text):
        errors.append(
            "private-aware verifier must not define or execute host statements "
            "before network-mode case dispatch."
        )
    private_branch = _extract_shell_case_branch(
        text, "DATA_NETWORK_MODE", "private"
    )
    if not private_branch:
        errors.append(
            "private-aware verifier contract requires an executable "
            "`case \"$DATA_NETWORK_MODE\" in ... private)` branch."
        )
        errors.extend(
            "private-aware verifier contract does not consume required "
            f"private input `${key}` inside the private mode branch."
            for key in _ASDW_PRIVATE_ENV_KEYS
        )
        return errors

    private_commands = [
        _strip_shell_inline_comment(command)
        for command in _extract_shell_logical_commands(private_branch)
    ]
    executable_text = "\n".join(private_commands)
    run_id_guard = 'if [[ ! "$DATA_VERIFY_RUN_ID" =~ ^[0-9a-f]{32}$ ]]; then'
    timeout_guard = "if ! command -v timeout >/dev/null 2>&1; then"
    first_azure_offset = _find_executable_az_command_offset(
        private_branch, "network vnet show"
    )
    if (
        private_commands.count(run_id_guard) != 1
        or private_commands.count(timeout_guard) != 1
        or first_azure_offset is None
        or private_branch.find(run_id_guard) >= first_azure_offset
        or private_branch.find(timeout_guard) >= first_azure_offset
    ):
        errors.append(
            "private verifier must validate DATA_VERIFY_RUN_ID as 32 lowercase "
            "hex and require GNU timeout before its first Azure CLI call."
        )
    if any(
        re.fullmatch(r"\s*if\s+\[\[.*\]\];\s*then\s*", command)
        and not _private_condition_is_fail_closed(command)
        for command in private_commands
    ):
        errors.append(
            "private-aware verifier topology condition must use only explicit "
            "fail-closed comparisons joined by `||`."
        )
    private_without_cleanup = _private_branch_without_cleanup(private_branch)
    if not _private_conditions_have_direct_exit(private_without_cleanup):
        errors.append(
            "private-aware verifier topology condition must use a direct "
            "`exit 1` true branch before continuing."
        )
    required_failure_predicates = (
        '"$sql_pe_state" != "Approved"',
        '"$cosmos_pe_state" != "Approved"',
        '"$sql_pe_subnet" != "$DATA_PRIVATE_ENDPOINT_SUBNET_ID"',
        '"$cosmos_pe_subnet" != "$DATA_PRIVATE_ENDPOINT_SUBNET_ID"',
        '"$aci_delegation" != "1"',
        '-z "$aci_nat_id"',
        '"${aci_nat_id##*/}" != "$DATA_NAT_GATEWAY_NAME"',
        '"$sql_dns_match" == "0"',
        '"$cosmos_dns_match" == "0"',
        '"$sql_vnet_link_count" == "0"',
        '"$cosmos_vnet_link_count" == "0"',
    )
    if any(predicate not in executable_text for predicate in required_failure_predicates):
        errors.append(
            "private-aware verifier topology condition must retain each "
            "required fail-closed comparison direction."
        )
    if re.search(
        r"(?m)(?:^|[;\n][ \t]*)if[ \t]+(?:false|![ \t]+(?:true|:))"
        r"[ \t]*(?:;[ \t]*)?(?:\n[ \t]*)?then\b",
        executable_text,
    ):
        errors.append(
            "private-aware verifier must not place its required topology or "
            "ACI sequence in an unreachable `if false` guard."
        )
    if _private_branch_has_disallowed_function_or_nested_az(private_branch):
        errors.append(
            "private-aware verifier must keep required Azure CLI commands as "
            "direct private-case statements; only `cleanup_aci` may be a function."
        )
    for key in _ASDW_PRIVATE_ENV_KEYS:
        if not re.search(_shell_variable_pattern(key), executable_text):
            errors.append(
                "private-aware verifier contract does not consume required "
                f"private input `${key}` inside the private mode branch."
            )

    topology_requirements = (
        ("network vnet show", "DATA_VNET_NAME"),
        ("network vnet subnet show", "DATA_PRIVATE_ENDPOINT_SUBNET_ID"),
        ("network vnet subnet show", "DATA_ACI_SUBNET_ID"),
        ("network nat gateway show", "DATA_NAT_GATEWAY_NAME"),
        ("network private-endpoint show", "SQL_PRIVATE_ENDPOINT_NAME"),
        ("network private-endpoint show", "COSMOS_PRIVATE_ENDPOINT_NAME"),
        ("network private-dns zone show", "SQL_PRIVATE_DNS_ZONE"),
        ("network private-dns zone show", "COSMOS_PRIVATE_DNS_ZONE"),
        ("identity show", "DATA_DEPLOY_IDENTITY_ID"),
    )
    for command_group, key in topology_requirements:
        commands = _find_az_commands(private_branch, command_group)
        if not any(re.search(_shell_variable_pattern(key), command) for command in commands):
            errors.append(
                "private-aware verifier topology check must execute "
                f"`az {command_group}` with `${key}`."
            )

    if not _has_reference_comparison(
        executable_text,
        _shell_reference_pattern("DATA_PRIVATE_ENDPOINT_SUBNET_ID"),
        _shell_reference_pattern("DATA_ACI_SUBNET_ID"),
    ):
        errors.append(
            "private-aware verifier topology must reject identical "
            "DATA_PRIVATE_ENDPOINT_SUBNET_ID and DATA_ACI_SUBNET_ID values."
        )
    if "Microsoft.ContainerInstance/containerGroups" not in executable_text:
        errors.append(
            "private-aware verifier topology must verify the ACI subnet "
            "delegation `Microsoft.ContainerInstance/containerGroups`."
        )
    if _count_shell_variable_comparisons(
        executable_text, "DATA_NAT_GATEWAY_NAME"
    ) < 1:
        errors.append(
            "private-aware verifier topology must compare the ACI subnet NAT "
            "Gateway with DATA_NAT_GATEWAY_NAME."
        )

    for service, endpoint_key in (
        ("SQL", "SQL_PRIVATE_ENDPOINT_NAME"),
        ("Cosmos", "COSMOS_PRIVATE_ENDPOINT_NAME"),
    ):
        state = _find_assigned_az_command(
            private_branch,
            "network private-endpoint show",
            (endpoint_key,),
            "privateLinkServiceConnectionState.status",
        )
        if state is None or not _has_shell_result_literal_check(
            executable_text, state[0], "Approved"
        ):
            errors.append(
                "private-aware verifier topology must query and compare the "
                f"{service} Private Endpoint state with `Approved`."
            )
        subnet = _find_assigned_az_command(
            private_branch,
            "network private-endpoint show",
            (endpoint_key,),
            "subnet.id",
        )
        if subnet is None or not _has_reference_comparison(
            executable_text,
            rf"[\"']?\${re.escape(subnet[0])}\b[\"']?",
            _shell_reference_pattern("DATA_PRIVATE_ENDPOINT_SUBNET_ID"),
        ):
            errors.append(
                "private-aware verifier topology must query and compare the "
                f"{service} Private Endpoint subnet with "
                "DATA_PRIVATE_ENDPOINT_SUBNET_ID."
            )
    for state_name in ("sql_pe_state", "cosmos_pe_state"):
        if not re.search(
            rf'"\${state_name}"\s*!=\s*"Approved"', executable_text
        ):
            errors.append(
                "private-aware verifier topology condition must reject a "
                f"non-Approved `{state_name}` result."
            )

    for service, endpoint_key, zone_key in (
        ("SQL", "SQL_PRIVATE_ENDPOINT_NAME", "SQL_PRIVATE_DNS_ZONE"),
        ("Cosmos", "COSMOS_PRIVATE_ENDPOINT_NAME", "COSMOS_PRIVATE_DNS_ZONE"),
    ):
        zone_group = _find_assigned_az_command(
            private_branch,
            "network private-endpoint dns-zone-group list",
            (endpoint_key, zone_key),
        )
        if zone_group is None or not _has_shell_result_literal_check(
            executable_text, zone_group[0], "0"
        ):
            errors.append(
                "private-aware verifier topology must query and reject a zero "
                f"result for the {service} Private Endpoint DNS zone group."
            )
        vnet_link = _find_assigned_az_command(
            private_branch,
            "network private-dns link vnet list",
            (zone_key, "vnet_id"),
        )
        if vnet_link is None or not _has_shell_result_literal_check(
            executable_text, vnet_link[0], "0"
        ):
            errors.append(
                "private-aware verifier topology must query and reject a zero "
                f"result for the {service} Private DNS VNet link."
            )

    identity = _find_assigned_az_command(
        private_branch,
        "identity show",
        ("DATA_DEPLOY_IDENTITY_ID",),
        "clientId",
    )
    if identity is None or not _is_unreassigned_shell_result(
        private_branch,
        identity[0],
        "DATA_DEPLOY_IDENTITY_CLIENT_ID",
    ):
        errors.append(
            "private-aware verifier topology must compare the resolved UAMI "
            "clientId with DATA_DEPLOY_IDENTITY_CLIENT_ID without reassignment."
        )
    for name, query in (
        ("vnet_id", "id"),
        ("pe_subnet_vnet", "contains(id, '$vnet_id') && id"),
        ("aci_subnet_vnet", "contains(id, '$vnet_id') && id"),
        (
            "aci_delegation",
            "delegations[?serviceName=='Microsoft.ContainerInstance/containerGroups'] | length(@)",
        ),
        ("aci_nat_id", "natGateway.id"),
        (
            "sql_pe_state",
            "privateLinkServiceConnections[0].privateLinkServiceConnectionState.status",
        ),
        (
            "cosmos_pe_state",
            "privateLinkServiceConnections[0].privateLinkServiceConnectionState.status",
        ),
        ("sql_pe_subnet", "subnet.id"),
        ("cosmos_pe_subnet", "subnet.id"),
        (
            "sql_dns_match",
            "[?privateDnsZoneConfigs[?contains(privateDnsZoneId, '/privateDnsZones/$SQL_PRIVATE_DNS_ZONE')]] | length(@)",
        ),
        (
            "cosmos_dns_match",
            "[?privateDnsZoneConfigs[?contains(privateDnsZoneId, '/privateDnsZones/$COSMOS_PRIVATE_DNS_ZONE')]] | length(@)",
        ),
        (
            "sql_vnet_link_count",
            "[?contains(virtualNetwork.id, '$vnet_id')] | length(@)",
        ),
        (
            "cosmos_vnet_link_count",
            "[?contains(virtualNetwork.id, '$vnet_id')] | length(@)",
        ),
        ("identity_client_id", "clientId"),
    ):
        if not _has_canonical_private_topology_query(private_branch, name, query):
            errors.append(
                "private-aware verifier topology query must use the canonical "
                f"JMESPath expression for `{name}`."
            )

    aci_commands = _find_az_commands(private_branch, "container create")
    if len(aci_commands) != 1:
        errors.append(
            "private SQL/Cosmos verification must execute exactly one "
            "`az container create` command in the private mode branch."
        )
        return errors

    aci_create = aci_commands[0]
    for option, key in (
        ("--resource-group", "RESOURCE_GROUP"),
        ("--name", "aci_name"),
        ("--image", "DATA_VERIFY_ACI_IMAGE"),
        ("--subnet", "DATA_ACI_SUBNET_ID"),
        ("--acr-identity", "DATA_DEPLOY_IDENTITY_ID"),
        ("--assign-identity", "DATA_DEPLOY_IDENTITY_ID"),
    ):
        if not _command_option_references_variable(aci_create, option, key):
            errors.append(
                f"private ACI `{option}` must reference `${key}` directly."
            )
    if not re.search(
        rf"--tags[ \t]+hveVerifyRunId=[\"']?{_shell_variable_pattern('DATA_VERIFY_RUN_ID')}",
        aci_create,
    ):
        errors.append(
            "private ACI create must tag the workload with `$DATA_VERIFY_RUN_ID`."
        )
    if not re.search(
        rf"\bAZURE_CLIENT_ID\s*=\s*[\"']?"
        rf"{_shell_variable_pattern('DATA_DEPLOY_IDENTITY_CLIENT_ID')}",
        aci_create,
    ):
        errors.append(
            "private ACI must pass `AZURE_CLIENT_ID` from "
            "`$DATA_DEPLOY_IDENTITY_CLIENT_ID`."
        )
    if not _command_option_references_variable(
        aci_create, "--command-line", "aci_command"
    ):
        errors.append(
            "private SQL/Cosmos verifier payload must run inside ACI via "
            "`--command-line \"$aci_command\"`; local direct execution is not allowed."
        )

    aci_name_assignment = re.search(
        r"(?m)^\s*(?:local\s+)?aci_name\s*=", private_branch
    )
    aci_name_assignments = re.findall(
        r'(?m)^\s*(?:local\s+)?aci_name="verify-data-\$DATA_VERIFY_RUN_ID"\s*(?:#.*)?$',
        private_branch,
    )
    assignment = re.search(
        r"(?m)^\s*(?:local\s+)?aci_command\s*=", private_branch
    )
    create_start = _find_executable_az_command_offset(
        private_branch, "container create"
    )
    if (
        aci_name_assignment is None
        or assignment is None
        or create_start is None
        or aci_name_assignment.start() >= create_start
        or assignment.start() >= create_start
    ):
        errors.append(
            "private SQL/Cosmos ACI name and payload must be assigned before "
            "`az container create`."
        )
        return errors
    if len(aci_name_assignments) != 1:
        errors.append(
            "private verifier must assign the fixed run-scoped `aci_name` exactly once."
        )
    existing_aci_lookup = re.search(
        r'aci_name_count="\$\(az container list '
        r'--resource-group "\$RESOURCE_GROUP" '
        r'--query "\[\?name==\x27\$aci_name\x27\] \| length\(@\)" '
        r'--output tsv\)"',
        private_branch,
    )
    existing_aci_guard = re.search(
        r'if \[\[ "\$aci_name_count" != "0" \]\]; then\s*exit 1\s*fi',
        private_branch,
        re.DOTALL,
    )
    if (
        existing_aci_lookup is None
        or existing_aci_guard is None
        or existing_aci_lookup.start() >= existing_aci_guard.start()
        or existing_aci_guard.start() >= create_start
    ):
        errors.append(
            "private verifier pre-create ACI lookup must use a successful "
            "`az container list` count and allow create only when the count is exactly zero."
        )
    aci_created_initializations = list(
        re.finditer(r"(?m)^\s*aci_created=0\s*$", private_branch)
    )
    aci_created_markers = list(
        re.finditer(r"(?m)^\s*aci_created=1\s*$", private_branch)
    )
    if (
        len(aci_created_initializations) != 1
        or len(aci_created_markers) != 1
        or aci_created_initializations[0].start() >= aci_name_assignment.start()
        or aci_created_markers[0].start() <= create_start
    ):
        errors.append(
            "private verifier must initialize `aci_created=0` before ACI setup "
            "and set `aci_created=1` only after `az container create` succeeds."
        )
    private_logical_commands = _extract_shell_logical_commands(private_branch)
    create_command_index = next(
        (
            index
            for index, command in enumerate(private_logical_commands)
            if re.match(r"^az[ \t]+container[ \t]+create\b", command)
        ),
        -1,
    )
    if (
        create_command_index < 0
        or create_command_index + 1 >= len(private_logical_commands)
        or private_logical_commands[create_command_index + 1].strip()
        != "aci_created=1"
    ):
        errors.append(
            "private verifier must make `aci_created=1` the immediately "
            "following logical statement after `az container create`."
        )
    wait_command_index = next(
        (
            index
            for index, command in enumerate(private_logical_commands)
            if re.fullmatch(
                r'aci_logs="\$\(timeout 600 az container logs '
                r'--resource-group "\$RESOURCE_GROUP" --name "\$aci_name" --follow\)" '
                r'\|\| aci_wait_failed=1',
                command.strip(),
            )
        ),
        -1,
    )
    exit_code_command_index = next(
        (
            index
            for index, command in enumerate(private_logical_commands)
            if re.fullmatch(
                r'aci_exit_code="\$\(az container show '
                r'--resource-group "\$RESOURCE_GROUP" --name "\$aci_name" '
                r'--query "containers\[0\]\.instanceView\.currentState\.exitCode" '
                r'--output tsv\)"',
                command.strip(),
            )
        ),
        -1,
    )
    result_condition_index = next(
        (
            index
            for index, command in enumerate(private_logical_commands)
            if re.fullmatch(
                r'if \[\[ "\$aci_wait_failed" != "0" \|\| "\$aci_exit_code" != "0" '
                r'\|\| -z "\$aci_logs" \]\]; then',
                command.strip(),
            )
        ),
        -1,
    )
    if not (
        wait_command_index == create_command_index + 3
        and wait_command_index < exit_code_command_index < result_condition_index
    ):
        errors.append(
            "private verifier must order one-shot ACI execution as `create`, "
            "`aci_created=1`, `aci_wait_failed=0`, fixed bounded log wait, "
            "canonical exitCode query, then result condition."
        )
    aci_assignment_commands = [
        command
        for command in private_logical_commands
        if _is_generated_shell_assignment(command, "aci_command")
    ]
    aci_assignment = (
        _split_generated_quoted_assignment(aci_assignment_commands[0], "aci_command")
        if len(aci_assignment_commands) == 1
        else None
    )
    assignment_word = (
        aci_assignment[0]
        if aci_assignment is not None
        else aci_assignment_commands[0]
        if len(aci_assignment_commands) == 1
        else ""
    )
    if assignment_word and _has_disallowed_generated_assignment_evaluation(
        assignment_word
    ):
        errors.append(
            "private SQL/Cosmos `aci_command` assignment must not contain "
            "host-evaluated substitution or indirection."
        )
    if aci_assignment is None or aci_assignment[1]:
        errors.append(
            "private SQL/Cosmos ACI payload must use exactly one direct quoted "
            "`aci_command` assignment without host-side statements."
        )
    payload = (
        aci_assignment[0].replace(r'\"', '"')
        if aci_assignment is not None
        else _extract_shell_assignment_value(private_branch, "aci_command")
    )
    if not payload:
        errors.append(
            "private SQL/Cosmos ACI payload must be assigned to `aci_command` "
            "before `az container create`."
        )
        return errors
    outside_payload = "\n".join(
        outside_command
        for command in private_logical_commands
        for outside_command in [
            _command_outside_generated_assignment(command, "aci_command")
        ]
        if outside_command
    )
    outside_executable_text = "\n".join(
        _strip_shell_inline_comment(command)
        for command in _extract_shell_logical_commands(outside_payload)
    )

    if "mssql-python" not in payload or not re.search(
        r"\bmssql_python\b", payload
    ):
        errors.append(
            "private SQL ACI payload must use the `mssql-python` package."
        )
    if "ActiveDirectoryMSI" not in payload or not re.search(
        rf"\bUID\s*=\s*{_shell_variable_pattern('DATA_DEPLOY_IDENTITY_CLIENT_ID')}"
        rf"\s*;\s*Authentication\s*=\s*ActiveDirectoryMSI\b",
        payload,
        re.IGNORECASE,
    ):
        errors.append(
            "private SQL ACI payload must set `UID` from "
            "`$DATA_DEPLOY_IDENTITY_CLIENT_ID` with "
            "`Authentication=ActiveDirectoryMSI`."
        )
    if not (
        re.search(r"\bconnect\s*\(", payload)
        and re.search(r"\b(?:cursor\.)?execute\s*\(", payload)
        and re.search(r"\bSELECT\s+(?:VALUE\s+)?COUNT(?:_BIG)?\s*\(", payload, re.IGNORECASE)
        and re.search(r"\bfetchone\s*\(", payload)
    ):
        errors.append(
            "private SQL ACI payload must execute a COUNT query through "
            "`mssql-python`, not only initialize a connection."
        )
    if re.search(r"\bif\s+False\s*:", payload):
        errors.append(
            "private SQL ACI payload must not place its COUNT query in an "
            "unreachable `if False` branch."
        )
    payload_without_count_exit_guards = re.sub(
        r"\b[A-Za-z_][A-Za-z0-9_]*\s*==\s*[1-9][0-9]*\s+or\s+sys\.exit\(1\)",
        "",
        payload,
    )
    if re.search(
        r"\b(?:exec|eval|if|else|and|or|lambda|type|globals|locals|getattr|setattr)\b",
        payload_without_count_exit_guards,
    ):
        errors.append(
            "private SQL/Cosmos ACI payload must not hide its COUNT queries in "
            "unreachable or non-straight-line execution."
        )
    if _payload_has_unexecuted_python_string(payload):
        errors.append(
            "private SQL/Cosmos ACI payload COUNT operations must be executable "
            "Python statements, not unexecuted string literals."
        )
    if not re.search(
        r'cursor\.execute\s*\(\s*"SELECT\s+COUNT_BIG\(\*\)\s+'
        r'FROM\s+\[dbo\]\.\[?[A-Za-z_][A-Za-z0-9_]*\]?"\s*\)',
        payload,
        re.IGNORECASE,
    ):
        errors.append(
            "private SQL ACI payload COUNT query must read one concrete "
            "`[dbo].<table>` source without a filter or derived query."
        )
    sql_count = re.search(
        r"\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
        r"(?:cursor\.)?fetchone\s*\(\)\s*\[\s*0\s*\]",
        payload,
    )
    if sql_count is None or not re.search(
        rf"\bprint\s*\(\s*int\s*\(\s*{re.escape(sql_count.group('name'))}\s*\)\s*\)",
        payload,
    ):
        errors.append(
            "private SQL ACI payload must emit the executed COUNT result."
        )
    elif not re.search(
        rf"\b{re.escape(sql_count.group('name'))}\s*==\s*[1-9][0-9]*\s+"
        r"or\s+sys\.exit\(1\)",
        payload,
    ):
        errors.append(
            "private SQL ACI payload must compare its COUNT result with a "
            "nonzero embedded expected value and explicitly `sys.exit(1)` on mismatch."
        )
    elif len(re.findall(
        rf"\b{re.escape(sql_count.group('name'))}\s*(?<![=!])=(?!=)", payload
    )) != 1:
        errors.append(
            "private SQL ACI payload COUNT result must not be reassigned before emit."
        )

    cosmos_credential = re.search(
        r"\bcredential\s*=\s*DefaultAzureCredential\s*\("
        r"[^)]*\bmanaged_identity_client_id\s*=\s*"
        r"(?P<client_id>[A-Za-z_][A-Za-z0-9_]*|"
        + _shell_variable_pattern("DATA_DEPLOY_IDENTITY_CLIENT_ID")
        + r")[^)]*\)",
        payload,
        re.DOTALL,
    )
    cosmos_client = re.search(
        r"\bCosmosClient\s*\([^)]*\bcredential\s*=\s*credential\b",
        payload,
        re.DOTALL,
    )
    cosmos_client_id_bound = False
    if cosmos_credential is not None:
        client_id_value = cosmos_credential.group("client_id")
        cosmos_client_id_bound = "DATA_DEPLOY_IDENTITY_CLIENT_ID" in client_id_value
        if not cosmos_client_id_bound and re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*", client_id_value
        ):
            cosmos_client_id_bound = re.search(
                rf"\b{re.escape(client_id_value)}\s*=\s*[\"']?"
                rf"{_shell_variable_pattern('DATA_DEPLOY_IDENTITY_CLIENT_ID')}",
                payload,
            ) is not None
    if "azure-cosmos" not in payload or not cosmos_client_id_bound:
        errors.append(
            "private Cosmos ACI payload must build `DefaultAzureCredential` "
            "with `DATA_DEPLOY_IDENTITY_CLIENT_ID`."
        )
    if cosmos_client is None:
        errors.append(
            "private Cosmos ACI payload must pass the managed-identity "
            "`credential` to `CosmosClient`."
        )
    if not (
        re.search(r"\bget_database_client\s*\(", payload)
        and re.search(r"\bget_container_client\s*\(", payload)
        and re.search(r"\bquery_items\s*\(", payload)
        and re.search(r"\bSELECT\s+(?:VALUE\s+)?COUNT\s*\(", payload, re.IGNORECASE)
    ):
        errors.append(
            "private Cosmos ACI payload must execute a COUNT query through "
            "the managed-identity CosmosClient."
        )
    if not re.search(
        r'container\.query_items\s*\(\s*query\s*=\s*'
        r'"SELECT\s+VALUE\s+COUNT\(1\)\s+FROM\s+c"',
        payload,
        re.IGNORECASE,
    ):
        errors.append(
            "private Cosmos ACI payload COUNT query must read all items from "
            "container alias `c` without a filter."
        )
    if re.search(r"\bif\s+False\s*:", payload):
        errors.append(
            "private Cosmos ACI payload must not place its COUNT query in an "
            "unreachable `if False` branch."
        )
    cosmos_count = re.search(
        r"\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*list\s*\(\s*"
        r"container\.query_items\s*\(",
        payload,
    )
    if cosmos_count is None or not re.search(
        rf"\bprint\s*\(\s*int\s*\(\s*{re.escape(cosmos_count.group('name'))}\s*\)\s*\)",
        payload,
    ):
        errors.append(
            "private Cosmos ACI payload must emit the executed COUNT result."
        )
    elif not re.search(
        rf"\b{re.escape(cosmos_count.group('name'))}\s*==\s*[1-9][0-9]*\s+"
        r"or\s+sys\.exit\(1\)",
        payload,
    ):
        errors.append(
            "private Cosmos ACI payload must compare its COUNT result with a "
            "nonzero embedded expected value and explicitly `sys.exit(1)` on mismatch."
        )
    elif len(re.findall(
        rf"\b{re.escape(cosmos_count.group('name'))}\s*(?<![=!])=(?!=)", payload
    )) != 1:
        errors.append(
            "private Cosmos ACI payload COUNT result must not be reassigned before emit."
        )

    if re.search(r"\bPYTHONOPTIMIZE\b|\bpython\s+-O{1,2}\b", payload):
        errors.append(
            "private SQL/Cosmos ACI payload must not enable Python optimization "
            "while enforcing COUNT checks."
        )
    if re.search(
        r"\b(?:sys\s*=|sys\.exit\s*=|sys\.__dict__|del\s+sys(?:\.exit)?\b|"
        r"from\s+sys\s+import\s+exit\b|\bexit\s*=|setattr\s*\(\s*sys\b|"
        r"delattr\s*\(\s*sys\b|vars\s*\(\s*sys\s*\))",
        payload,
    ):
        errors.append(
            "private SQL/Cosmos ACI payload must not rebind or delete the "
            "`sys.exit` COUNT failure handler."
        )

    after_create = private_branch[create_start:]
    aci_show_commands = _find_az_commands(after_create, "container show")
    if not aci_show_commands or any(
        not _command_option_references_variable(
            command, "--resource-group", "RESOURCE_GROUP"
        )
        or not _command_option_references_variable(command, "--name", "aci_name")
        for command in aci_show_commands
    ):
        errors.append(
            "private verifier must use `$RESOURCE_GROUP` and `$aci_name` for "
            "every `az container show` command after `az container create`."
        )
    exit_code = _find_assigned_az_command(
        after_create,
        "container show",
        ("aci_name", "RESOURCE_GROUP"),
        "exitCode",
    )
    if exit_code is None or not _has_shell_result_literal_check(
        after_create, exit_code[0], "0"
    ):
        errors.append(
            "private verifier must collect and compare the one-shot ACI "
            "exitCode with `0` after `az container create`."
        )
    aci_logs_commands = _find_az_commands(after_create, "container logs")
    if not aci_logs_commands or any(
        not _command_option_references_variable(
            command, "--resource-group", "RESOURCE_GROUP"
        )
        or not _command_option_references_variable(command, "--name", "aci_name")
        for command in aci_logs_commands
    ):
        errors.append(
            "private verifier must use `$RESOURCE_GROUP` and `$aci_name` for "
            "every `az container logs` command after `az container create`."
        )
    logs = _find_assigned_az_command(
        after_create,
        "container logs",
        ("aci_name", "RESOURCE_GROUP"),
    )
    if logs is None or not _has_shell_result_nonempty_check(after_create, logs[0]):
        errors.append(
            "private verifier must collect and check nonempty one-shot ACI "
            "logs after `az container create`."
        )
    if not re.search(
        r'(?m)^\s*aci_logs="\$\(timeout[ \t]+600[ \t]+az[ \t]+container[ \t]+'
        r'logs[ \t]+--resource-group[ \t]+"\$RESOURCE_GROUP"[ \t]+'
        r'--name[ \t]+"\$aci_name"[ \t]+--follow\)"[ \t]+'
        r'\|\|[ \t]+aci_wait_failed=1\s*$',
        after_create,
    ):
        errors.append(
            "private verifier must wait for the one-shot ACI with the fixed "
            "`timeout 600 az container logs ... --follow` command before "
            "checking its exitCode and logs."
        )
    cleanup_handler = re.search(
        r"(?ms)^\s*cleanup_aci\s*\(\)\s*\{(?P<body>.*?)\}",
        private_branch,
    )
    cleanup_trap = re.search(
        r"(?m)^\s*trap[ \t]+cleanup_aci\b[^\n]*$",
        private_branch,
    )
    cleanup_signals_complete = (
        cleanup_trap is not None
        and all(
            re.search(rf"\b{signal}\b", cleanup_trap.group(0)) is not None
            for signal in ("EXIT", "INT", "TERM")
        )
    )
    cleanup_trap_start = cleanup_trap.start() if cleanup_trap is not None else -1
    cleanup_body = cleanup_handler.group("body") if cleanup_handler is not None else ""
    cleanup_delete = (
        cleanup_handler is not None
        and _cleanup_body_has_only_expected_delete(cleanup_body)
    )
    if (
        not cleanup_delete
        or not cleanup_signals_complete
        or cleanup_trap_start >= create_start
    ):
        errors.append(
            "private verifier `cleanup_aci` must delete only the current "
            "Resource Group / aci_name one-shot ACI before `az container create`."
        )
    private_without_cleanup = _private_branch_without_cleanup(private_branch)
    if _has_obfuscated_private_host_command_source(private_without_cleanup):
        errors.append(
            "private verifier must keep host Azure CLI commands direct; do not "
            "reconstruct command names with quotes, escapes, or expansions."
        )
    if _private_branch_has_unapproved_host_statement(private_without_cleanup):
        errors.append(
            "private verifier must keep host Azure CLI commands direct and "
            "within the approved private topology / ACI command set."
        )
    outside_cleanup_commands = [
        _strip_shell_inline_comment(outside_command).replace('""', "").replace("''", "")
        for command in _extract_shell_logical_commands(private_without_cleanup)
        for outside_command in [
            _command_outside_generated_assignment(command, "aci_command")
        ]
        if outside_command
    ]
    if any(
        re.search(r"\bdelete\b", command, re.IGNORECASE)
        for command in outside_cleanup_commands
    ):
        errors.append(
            "private verifier must not execute any delete operation outside "
            "`cleanup_aci`."
        )
    if _has_disallowed_private_host_azure_cli(outside_cleanup_commands):
        errors.append(
            "private verifier must keep host Azure CLI commands direct and "
            "within the approved private topology / ACI command set."
        )
    if _contains_shell_command_token(outside_executable_text, "sqlcmd"):
        errors.append(
            "private verifier must not execute local direct SQL commands "
            "outside the ACI payload."
        )
    if _contains_shell_command_token(
        outside_executable_text, "python", "python3"
    ) and re.search(
        r"(?:mssql_python|azure\.cosmos|CosmosClient)", outside_executable_text
    ):
        errors.append(
            "private verifier must not execute local direct Cosmos or SQL "
            "Python code outside the ACI payload."
        )
    if re.search(
        r"\b(?:COSMOS_KEY|ACCOUNT_KEY|AccountKey\s*=|SharedAccessSignature\s*=|"
        r"(?:connection|connection_string)\s*=)",
        outside_executable_text,
        re.IGNORECASE,
    ):
        errors.append(
            "private verifier must not use a Cosmos key or connection string "
            "outside the ACI payload."
        )
    outside_without_aci_create = outside_executable_text.replace(aci_create, "", 1)
    if re.search(
        r"(?:mssql_python|azure\.cosmos|CosmosClient|DefaultAzureCredential)",
        outside_without_aci_create,
    ):
        errors.append(
            "private verifier must not keep SQL/Cosmos SDK code outside the "
            "ACI payload."
        )
    if (
        re.search(_shell_variable_pattern("aci_command"), outside_without_aci_create)
        or re.search(r"\$\{!", outside_without_aci_create)
        or re.search(
            r"\b(?:eval|source)\b|(?:^|[;\s])\.|"
            r"/(?:usr/)?bin/(?:bash|sh|python3?|env)\b",
            outside_without_aci_create,
        )
    ):
        errors.append(
            "private verifier must not locally replay `aci_command` outside "
            "the ACI payload."
        )
    if _contains_shell_command_token(
        outside_executable_text, "python", "python3", "sh", "bash", "eval"
    ) and re.search(_shell_variable_pattern("aci_command"), outside_executable_text):
        errors.append(
            "private verifier must not locally replay `aci_command` outside "
            "the ACI payload."
        )
    if _contains_shell_command_token(payload, "sqlcmd") and re.search(
        r"\bsql(?:\"\"|'')?cmd\b[^\n]*\s-G\b", payload
    ):
        errors.append(
            "private SQL ACI must use explicit UAMI authentication via "
            "`mssql-python`, not implicit `sqlcmd -G`."
        )
    if _command_option_references_variable(
        aci_create, "--image", "SQLCMD_ACI_IMAGE"
    ) or _payload_uses_variable(payload, "SQLCMD_ACI_IMAGE"):
        errors.append(
            "private Cosmos ACI must use `DATA_VERIFY_ACI_IMAGE`; "
            "do not reuse `SQLCMD_ACI_IMAGE` as a Python runtime."
        )
    if "validate_nsp_evidence" in executable_text and "collect_values(" in text:
        errors.append(
            "NSP evidence must use a fixed schema tied to the target resource; "
            "recursive arbitrary JSON value collection is not allowed."
        )
    return errors


def validate_asdw_data_verify_script(
    path: "Path | str",
    design_doc_path: "Path | str | None" = None,
    private_capability_required: bool = False,
    sample_data_path: "Path | str | None" = None,
    script_text: Optional[str] = None,
    design_doc_text: Optional[str] = None,
    sample_data_text: Optional[str] = None,
) -> List[str]:
    """ASDW-WEB Step.1.2 の data verify スクリプト契約を検証する。

    Step.1.2 は `src/infra/azure/verify-data-resources.sh` を既存成果物として
    再利用し得るため、ファイル存在だけでは stale な PostgreSQL 判定
    (`provisioningState=Succeeded`) や、GREEN 到達不能な PostgreSQL ACI
    fallback を検出できない。ここでは今回確認済みの最小契約に限定し、
    PostgreSQL Flexible Server の正常状態判定が `state=Ready` であること、
    かつ psql 不在/egress 不可時の ACI fallback が安全な引数で作られている
    こと、および PostgreSQL データベース存在確認 `db show` が存在しない
    引数 `--database-name`（正しくは `--name`/`-n`）を使用していないことを
    静的検査する。

    ただし PostgreSQL Flexible Server の検証要求は、`design_doc_path`
    （`docs/azure/azure-services-data.md`）が PostgreSQL を「選定サービス
    （Chosen Azure service）」として採用している場合、またはスクリプト内に
    PostgreSQL 検証ブロックが実在する場合に限る。DataDesign はデータストアを
    動的に選定するため、PostgreSQL を含まない設計（例: Azure SQL / Cosmos DB /
    Blob / ADX）では PostgreSQL ブロックの不在を契約違反としない（偽陽性回避）。
    """
    script_path = Path(path)
    if script_text is None:
        if not script_path.exists():
            return [f"verify-data-resources.sh not found: {script_path}"]
        try:
            text = script_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return [f"verify-data-resources.sh read error: {exc}"]
    else:
        text = script_text

    errors: List[str] = []
    if private_capability_required:
        errors.extend(_validate_asdw_network_case_contract(text))
        errors.extend(_validate_asdw_private_verify_capability(text))
        audit_mode: Optional[str] = None
        if design_doc_path is not None:
            audit_mode, audit_mode_errors = _resolve_asdw_audit_storage_mode(
                design_doc_path,
                design_doc_text,
            )
            errors.extend(audit_mode_errors)
            if audit_mode_errors:
                audit_mode = "invalid"
            elif audit_mode is not None:
                errors.extend(_validate_asdw_audit_mode_wiring(text, audit_mode))
        errors.extend(_validate_asdw_non_private_branches(text))
        errors.extend(
            _validate_asdw_known_mode_selected_data(
                text,
                sample_data_path,
                audit_mode,
                sample_data_text,
            )
            if audit_mode in {
                _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST,
                _ASDW_AUDIT_MODE_ACL_DIRECT,
            }
            else _validate_asdw_selected_data_coverage(
                text,
                sample_data_path,
                audit_mode=audit_mode,
                sample_data_text=sample_data_text,
            )
        )
    pg_section = _extract_postgresql_section(text)
    has_pg_show = _has_postgresql_flexible_show(text)
    has_pg_block = bool(pg_section) or "PostgreSQL Flexible Server" in text

    postgres_present = has_pg_show or has_pg_block
    postgres_required = _design_requires_postgresql(
        design_doc_path,
        design_doc_text,
    )

    # PostgreSQL が設計で選定されておらず、スクリプトにも存在しない場合は
    # PostgreSQL 検証を一切要求しない。DataDesign はデータストアを動的に選定
    # するため、PostgreSQL を含まない設計（Azure SQL / Cosmos DB / Blob / ADX 等）
    # では PostgreSQL 検証ブロックの不在は正当であり、偽陽性で Step を止めない
    # （2026-07-02: PostgreSQL 非選定設計で 4 件の偽陽性 fail を実証）。
    if not postgres_required and not postgres_present:
        return errors

    if not has_pg_block and not has_pg_show:
        errors.append("PostgreSQL Flexible Server 検証ブロックが見つかりません。")

    if not has_pg_show:
        errors.append("PostgreSQL Flexible Server の `az postgres flexible-server show` が見つかりません。")

    pg_contract_text = pg_section or text
    if "--query state" not in pg_contract_text and "--query 'state'" not in pg_contract_text and '--query "state"' not in pg_contract_text:
        errors.append("PostgreSQL Flexible Server は `--query state` で状態確認してください。")

    if "Ready" not in pg_contract_text:
        errors.append("PostgreSQL Flexible Server の正常状態 `Ready` が検証スクリプトに含まれていません。")

    if "--query 'provisioningState'" in pg_section or '--query "provisioningState"' in pg_section or "--query provisioningState" in pg_section:
        errors.append("PostgreSQL Flexible Server に `provisioningState` 判定を一律適用しないでください。")

    if "provisioningState=Succeeded" in pg_section or "provisioningState == Succeeded" in pg_section:
        errors.append("PostgreSQL Flexible Server は `provisioningState=Succeeded` ではなく `state=Ready` を確認してください。")

    # コメント行（`#` 以降）を除去してから判定する。コメントで正しい引数を
    # 説明する文言（例:「db show は --database-name 不可」）まで誤検知しない
    # ようにするため（2026-07-02 敵対的レビューで実証された false positive）。
    pg_contract_text_no_comments = "\n".join(
        line.split("#", 1)[0] for line in pg_contract_text.splitlines()
    )
    if "flexible-server db show" in pg_contract_text_no_comments and "--database-name" in pg_contract_text_no_comments:
        errors.append(
            "PostgreSQL データベース存在確認 `az postgres flexible-server db show` は "
            "`--database-name` ではなく `--name`/`-n` を使用してください"
            "（`--database-name` という引数は存在しません）。"
        )

    pg_aci_section = pg_section
    postgres_count_via_aci = _extract_shell_function(text, "postgres_count_via_aci")
    if postgres_count_via_aci:
        pg_aci_section = f"{pg_section}\n{postgres_count_via_aci}"

    pg_has_aci = "az container create" in pg_aci_section and "postgres:16-alpine" in pg_aci_section
    if not pg_has_aci:
        errors.append("PostgreSQL 件数検証は psql 不在/egress 不可時の ACI fallback（postgres:16-alpine）を含めてください。")
    else:
        aci_command = _extract_first_az_container_create_command(pg_aci_section)
        if "--os-type Linux" not in aci_command and "--os-type=Linux" not in aci_command:
            errors.append("PostgreSQL ACI fallback の `az container create` には `--os-type Linux` を指定してください。")
        if not re.search(r"--cpu(?:\s+|=)\S+", aci_command):
            errors.append("PostgreSQL ACI fallback の `az container create` には `--cpu` を指定してください。")
        if not re.search(r"--memory(?:\s+|=)\S+", aci_command):
            errors.append("PostgreSQL ACI fallback の `az container create` には `--memory` を指定してください。")
        if "--secure-environment-variables" not in aci_command:
            errors.append("PostgreSQL ACI fallback は `PGPASSWORD` を `--secure-environment-variables` で渡してください。")
        for required_env in ("PGPASSWORD", "PGSSLMODE", "PGHOST", "PGUSER", "PGDATABASE"):
            if required_env not in aci_command:
                errors.append(f"PostgreSQL ACI fallback の環境変数 `{required_env}` が見つかりません。")
        if re.search(r"PGPASSWORD=\$\{?PG_TOKEN\}?\s+psql", aci_command):
            errors.append("PostgreSQL ACI fallback でアクセストークンを `--command-line` に直接展開しないでください。")
        if re.search(r"-U\s+\$\{?PG_ADMIN_USER\}?", aci_command):
            errors.append("PostgreSQL ACI fallback で UPN を `--command-line` に直接展開せず、`PGUSER` 環境変数で渡してください。")

    return errors


_ASDW_DATA_PREP_BEGIN = "# HVE-ASDW-DATA-PREP-BEGIN"
_ASDW_DATA_PREP_END = "# HVE-ASDW-DATA-PREP-END"
_ASDW_DATA_CREATE_BEGIN = "# HVE-ASDW-DATA-CREATE-BEGIN"
_ASDW_DATA_CREATE_END = "# HVE-ASDW-DATA-CREATE-END"
_ASDW_DATA_DEPLOY_NETWORK_KEYS = (
    "DATA_NETWORK_MODE",
    "DATA_VNET_NAME",
    "DATA_PRIVATE_ENDPOINT_SUBNET_ID",
    "DATA_ACI_SUBNET_ID",
    "DATA_NAT_GATEWAY_NAME",
    "DATA_DEPLOY_IDENTITY_ID",
    "DATA_DEPLOY_IDENTITY_CLIENT_ID",
    "SQL_PRIVATE_ENDPOINT_NAME",
    "COSMOS_PRIVATE_ENDPOINT_NAME",
    "SQL_PRIVATE_DNS_ZONE",
    "COSMOS_PRIVATE_DNS_ZONE",
)
_ASDW_DATA_CREATE_WRITE_VERB = re.compile(
    r"\b(?:create|update|delete|register|unregister|add|remove|enable|"
    r"disable|set|assign|unassign|grant|revoke|start|stop|restart|restore|"
    r"import|export|failover|purge)\b",
    re.IGNORECASE,
)
_ASDW_DATA_CREATE_FORBIDDEN_PUBLIC = re.compile(
    r"publicNetworkAccess\s*=\s*Enabled|--enable-public-network(?:\s+|=)true|"
    r"--public-network-access(?:\s+|=)Enabled|\bfirewall-rule\b|"
    r"\bAllowAzureServices\b|--start-ip-address\s+0\.0\.0\.0|"
    r"--end-ip-address\s+0\.0\.0\.0",
    re.IGNORECASE,
)
_ASDW_DATA_CREATE_FORBIDDEN_SECRET = re.compile(
    r"SQL_ADMIN_PASSWORD|PGPASSWORD|COSMOS_(?:KEY|ACCOUNT_KEY)|"
    r"ACCOUNT_KEY|SharedAccessSignature|AccountKey\s*=|"
    r"\baz\s+[^\r\n]*(?:keys\s+list|list-keys|get-access-token)\b|"
    r"Authorization\s*:\s*Bearer|--admin-password\b|(?:^|\s)-P(?:\s|$)",
    re.IGNORECASE | re.MULTILINE,
)
_ASDW_DATA_CREATE_FORBIDDEN_AUDIT_WRITE = re.compile(
    r"AUDIT_RECORD_JSON|auditEventId|entities\s*\[\s*[\"']AuditRecord[\"']\s*\]|"
    r"begin_create_ledger_entry|create_ledger_entry\s*\(",
    re.IGNORECASE,
)
_ASDW_DATA_CREATE_CHILD_REFERENCE = re.compile(
    r"data-registration-script(?:\.sh)?|verify-data-resources(?:\.sh)?|"
    r"hve\.asdw_data_script_launcher",
    re.IGNORECASE,
)
_ASDW_NON_AUDIT_ID_FIELDS = {
    "Member": "memberId",
    "ConsentRecord": "consentRecordId",
    "DataRightsRequest": "requestId",
    "LoyaltyAccount": "loyaltyAccountId",
    "PointTransaction": "pointTransactionId",
    "Reward": "rewardId",
    "RewardExchange": "rewardExchangeId",
    "PaidMembershipContract": "contractId",
    "SupportCase": "supportCaseId",
    "CaseResolution": "resolutionId",
    "VocRecord": "sourceRecordId",
}


def _build_asdw_non_audit_registration_source(
    counts: Mapping[str, int],
    audit_mode: str,
) -> str:
    """Build the one canonical APP-009 non-Audit registration program."""
    non_audit_entities = [
        entity for entity, _database, _table in _ASDW_APP009_SQL_COVERAGE
    ] + ["VocRecord"]
    expected_counts = {
        entity: counts[entity]
        for entity in non_audit_entities
    }
    sql_mappings = [
        [entity, database, table, _ASDW_NON_AUDIT_ID_FIELDS[entity]]
        for entity, database, table in _ASDW_APP009_SQL_COVERAGE
    ]
    lines = [
        "from azure.core.exceptions import ResourceNotFoundError",
        "from azure.cosmos import CosmosClient",
        "from azure.identity import DefaultAzureCredential",
        "from contextlib import ExitStack, closing",
        "from mssql_python import connect",
        "from urllib.parse import urlparse",
        "import json, os, re",
        "",
        f"expected_counts = {json.dumps(expected_counts, ensure_ascii=True, sort_keys=True)}",
        f"sql_mappings = {json.dumps(sql_mappings, ensure_ascii=True)}",
        "resources = ExitStack()",
        "try:",
        '    sample = json.loads(os.environ["NON_AUDIT_DATA_JSON"])',
        '    next(filter(None, [isinstance(sample, dict)]))',
        '    entities = sample["entities"]',
        '    next(filter(None, [isinstance(entities, dict)]))',
        '    next(filter(None, [set(entities) == set(expected_counts) | {"AuditRecord"}]))',
        '    next(filter(None, [isinstance(entities["AuditRecord"], list)]))',
        f'    next(filter(None, [len(entities["AuditRecord"]) == {counts["AuditRecord"]}]))',
        "    for entity, expected_count in expected_counts.items():",
        "        next(filter(None, [isinstance(entities[entity], list)]))",
        "        next(filter(None, [len(entities[entity]) == expected_count]))",
        "        next(filter(None, [expected_count > 0]))",
        "    connections = {}",
        "    cursors = {}",
        "    for entity, database_key, table, id_field in sql_mappings:",
        "        if database_key not in connections:",
        '            connection = resources.enter_context(closing(connect("Server=" + os.environ["SQL_HOST"] + ";Database=" + os.environ[database_key] + ";UID=" + os.environ["DATA_DEPLOY_IDENTITY_CLIENT_ID"] + ";Authentication=ActiveDirectoryMSI;Encrypt=yes;TrustServerCertificate=no")))',
        "            connections[database_key] = connection",
        "            cursors[database_key] = resources.enter_context(closing(connection.cursor()))",
        "        cursor = cursors[database_key]",
        '        next(filter(None, [re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table)]))',
        '        cursor.execute(f"IF OBJECT_ID(N\'[dbo].[{table}]\', N\'U\') IS NULL EXEC(N\'CREATE TABLE [dbo].[{table}] ([id] nvarchar(256) NOT NULL PRIMARY KEY, [payload] nvarchar(max) NOT NULL)\')")',
        "        for record in entities[entity]:",
        "            next(filter(None, [isinstance(record, dict)]))",
        "            record_id = record[id_field]",
        "            next(filter(None, [isinstance(record_id, str)]))",
        "            normalized_id = record_id.strip()",
        "            next(filter(None, [normalized_id and normalized_id == record_id]))",
        '            payload = json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True)',
        '            cursor.execute(f"IF NOT EXISTS (SELECT 1 FROM [dbo].[{table}] WITH (UPDLOCK, HOLDLOCK) WHERE id = ?) BEGIN INSERT INTO [dbo].[{table}] (id, payload) VALUES (?, ?); END; SELECT COUNT_BIG(*), COALESCE(SUM(CASE WHEN payload = ? THEN 1 ELSE 0 END), 0) FROM [dbo].[{table}] WITH (HOLDLOCK) WHERE id = ?;", (normalized_id, normalized_id, payload, payload, normalized_id))',
        "            stored_summary = cursor.fetchone()",
        "            next(filter(None, [stored_summary == (1, 1)]))",
    ]
    if audit_mode == _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST:
        lines.extend(
            [
                '    audit_table = os.environ["SQL_AUDIT_TABLE"]',
                '    next(filter(None, [re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", audit_table)]))',
                '    audit_connection = resources.enter_context(closing(connect("Server=" + os.environ["SQL_HOST"] + ";Database=" + os.environ["SQL_DB_SVC12"] + ";UID=" + os.environ["DATA_DEPLOY_IDENTITY_CLIENT_ID"] + ";Authentication=ActiveDirectoryMSI;Encrypt=yes;TrustServerCertificate=no")))',
                "    audit_cursor = resources.enter_context(closing(audit_connection.cursor()))",
                '    audit_cursor.execute(f"IF OBJECT_ID(N\'[dbo].[{audit_table}]\', N\'U\') IS NULL EXEC(N\'CREATE TABLE [dbo].[{audit_table}] ([id] nvarchar(256) NOT NULL PRIMARY KEY, [payload] nvarchar(max) NOT NULL) WITH (LEDGER = ON (APPEND_ONLY = ON))\')")',
                '    audit_cursor.execute("SELECT ledger_type_desc FROM sys.tables WHERE schema_id = SCHEMA_ID(\'dbo\') AND name = ?", (audit_table,))',
                "    audit_table_rows = audit_cursor.fetchall()",
                '    next(filter(None, [audit_table_rows == [("APPEND_ONLY_LEDGER_TABLE",)]]))',
                '    audit_cursor.execute("SELECT path FROM sys.database_ledger_digest_locations WHERE is_current = 1")',
                "    digest_rows = audit_cursor.fetchall()",
                '    ledger_host = urlparse(os.environ["CONFIDENTIAL_LEDGER_ENDPOINT"]).hostname',
                "    next(filter(None, [ledger_host]))",
                "    next(filter(None, [any(urlparse(str(row[0])).hostname == ledger_host for row in digest_rows)]))",
                "    audit_connection.commit()",
            ]
        )
    lines.extend(
        [
            "    for connection in connections.values():",
            "        connection.commit()",
            '    client_id = os.environ["DATA_DEPLOY_IDENTITY_CLIENT_ID"]',
            "    credential = resources.enter_context(closing(DefaultAzureCredential(managed_identity_client_id=client_id)))",
            '    cosmos = resources.enter_context(closing(CosmosClient(os.environ["COSMOS_ENDPOINT"], credential=credential)))',
            '    container = cosmos.get_database_client(os.environ["COSMOS_DATABASE"]).get_container_client(os.environ["COSMOS_CONTAINER_VOC"])',
            '    for record in entities["VocRecord"]:',
            "        next(filter(None, [isinstance(record, dict)]))",
            '        source_id = record["sourceRecordId"]',
            "        next(filter(None, [isinstance(source_id, str)]))",
            "        normalized_id = source_id.strip()",
            "        next(filter(None, [normalized_id and normalized_id == source_id]))",
            "        item = dict(record)",
            '        item["id"] = normalized_id',
            '        payload = json.dumps(item, ensure_ascii=False, separators=(",", ":"), sort_keys=True)',
            "        try:",
            "            stored_item = container.read_item(item=normalized_id, partition_key=source_id)",
            "        except ResourceNotFoundError:",
            "            container.create_item(item)",
            "        else:",
            '            stored_business_item = {key: value for key, value in stored_item.items() if not key.startswith("_")}',
            '            stored_payload = json.dumps(stored_business_item, ensure_ascii=False, separators=(",", ":"), sort_keys=True)',
            "            next(filter(None, [stored_payload == payload]))",
            '    print("HVE_NON_AUDIT_REGISTRATION_OK")',
            "finally:",
            "    resources.close()",
        ]
    )
    return "\n".join(lines) + "\n"


def _build_asdw_non_audit_aci_command(
    counts: Mapping[str, int],
    audit_mode: str,
) -> str:
    """Encode the canonical program without exposing shell quote structure."""
    source = _build_asdw_non_audit_registration_source(counts, audit_mode)
    encoded = base64.b64encode(source.encode("utf-8")).decode("ascii")
    return (
        "python -c 'import base64;exec(base64.b64decode(\""
        + encoded
        + "\",validate=True).decode(\"utf-8\"))'"
    )


def _extract_asdw_non_audit_registration_source(
    private_branch: str,
) -> Tuple[str, List[str]]:
    assignments = [
        command
        for command in _extract_shell_logical_commands(private_branch)
        if _is_generated_shell_assignment(command, "non_audit_command")
    ]
    if len(assignments) != 1:
        return "", [
            "DataDeploy non-Audit registration requires exactly one direct non_audit_command assignment."
        ]
    assignment = _split_generated_quoted_assignment(
        assignments[0], "non_audit_command"
    )
    if assignment is None or assignment[1]:
        return "", [
            "DataDeploy non-Audit registration command must be one direct quoted assignment."
        ]
    assignment_word = assignment[0]
    if (
        len(assignment_word) < 2
        or assignment_word[0] != '"'
        or assignment_word[-1] != '"'
    ):
        return "", [
            "DataDeploy non-Audit registration command must use one double-quoted shell assignment."
        ]
    command = assignment_word[1:-1].replace(r'\"', '"')
    match = re.fullmatch(
        r"python -c 'import base64;exec\(base64\.b64decode\(\""
        r"(?P<payload>[A-Za-z0-9+/]+={0,2})"
        r"\",validate=True\)\.decode\(\"utf-8\"\)\)'",
        command,
    )
    if match is None:
        return "", [
            "DataDeploy non-Audit ACI must use the canonical base64 Python envelope."
        ]
    try:
        source = base64.b64decode(
            match.group("payload"),
            validate=True,
        ).decode("utf-8")
    except (ValueError, UnicodeError) as exc:
        return "", [f"DataDeploy non-Audit Python payload decode error: {exc}"]
    return source, []


def _load_asdw_data_deploy_shell_text(
    path: "Path | str",
    label: str,
    override_text: Optional[str],
) -> Tuple[str, List[str]]:
    """Read one strict UTF-8/LF shell artifact, or validate a byte snapshot text."""
    script_path = Path(path)
    if override_text is None:
        if not script_path.is_file():
            return "", [f"{label} not found: {script_path}"]
        try:
            raw = script_path.read_bytes()
        except OSError as exc:
            return "", [f"{label} read error: {exc}"]
        if raw.startswith(b"\xef\xbb\xbf"):
            return "", [f"{label} must not contain a UTF-8 BOM."]
        if b"\r" in raw:
            return "", [f"{label} must use LF line endings only."]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            return "", [f"{label} UTF-8 decode error: {exc}"]
    else:
        text = override_text
        if text.startswith("\ufeff"):
            return "", [f"{label} must not contain a UTF-8 BOM."]
        if "\r" in text:
            return "", [f"{label} must use LF line endings only."]
    return text, []


def _extract_asdw_data_deploy_marker_block(
    text: str,
    *,
    begin: str,
    end: str,
    label: str,
) -> Tuple[str, List[str]]:
    """Require the complete executable artifact inside one shebang-bound block."""
    lines = text.splitlines()
    begin_indexes = [index for index, line in enumerate(lines) if line == begin]
    end_indexes = [index for index, line in enumerate(lines) if line == end]
    if (
        len(begin_indexes) != 1
        or len(end_indexes) != 1
        or begin_indexes[0] >= end_indexes[0]
    ):
        return "", [f"{label} requires exactly one ordered marker pair."]
    if (
        not lines
        or lines[0] != "#!/usr/bin/env bash"
        or begin_indexes[0] != 1
    ):
        return "", [
            f"{label} BEGIN marker must be the direct second physical line after the Bash shebang."
        ]
    if any(line.strip() for line in lines[end_indexes[0] + 1 :]):
        return "", [f"{label} must not execute or declare content after its END marker."]
    block = "\n".join(lines[begin_indexes[0] + 1 : end_indexes[0]]).strip()
    if not block:
        return "", [f"{label} marker block must not be empty."]
    return block + "\n", []


_ASDW_PREP_DIRECT_AZ_PREFIXES = (
    ("az", "group", "create"),
    ("az", "provider", "register"),
    ("az", "network", "vnet", "create"),
    ("az", "network", "vnet", "subnet", "create"),
    ("az", "network", "vnet", "subnet", "update"),
    ("az", "network", "nat", "gateway", "create"),
    ("az", "identity", "create"),
    ("az", "acr", "create"),
    ("az", "acr", "build"),
    ("az", "role", "assignment", "create"),
)
_ASDW_CREATE_DIRECT_AZ_PREFIXES = (
    ("az", "network", "private-endpoint", "create"),
    ("az", "network", "private-endpoint", "dns-zone-group", "create"),
    ("az", "network", "private-dns", "zone", "create"),
    ("az", "network", "private-dns", "link", "vnet", "create"),
    ("az", "sql", "server", "create"),
    ("az", "sql", "db", "create"),
    ("az", "sql", "db", "ledger-digest-uploads", "enable"),
    ("az", "cosmosdb", "create"),
    ("az", "cosmosdb", "sql", "database", "create"),
    ("az", "cosmosdb", "sql", "container", "create"),
    ("az", "confidentialledger", "create"),
    ("az", "container", "create"),
    ("az", "container", "show"),
    ("az", "container", "list"),
    ("az", "container", "logs"),
    ("az", "container", "delete"),
)


def _asdw_shell_tokens(command: str) -> Optional[List[str]]:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except ValueError:
        return None


def _asdw_tokens_start_with(
    tokens: List[str],
    prefixes: Tuple[Tuple[str, ...], ...],
) -> bool:
    return any(tuple(tokens[: len(prefix)]) == prefix for prefix in prefixes)


def _validate_asdw_data_deploy_top_level_shape(
    text: str,
    label: str,
) -> List[str]:
    """Require a fixed preamble followed by one direct top-level network case."""
    visible_lines = [
        _strip_shell_inline_comment(line).strip()
        for line in text.splitlines()
        if _strip_shell_inline_comment(line).strip()
    ]
    expected_preamble = [
        "set -euo pipefail",
        ': "${HVE_ASDW_SCRIPT_DIR:?}"',
        'SCRIPT_DIR="$HVE_ASDW_SCRIPT_DIR"',
        'case "${DATA_NETWORK_MODE:?}" in',
    ]
    if visible_lines[:4] != expected_preamble or visible_lines[-1:] != ["esac"]:
        return [
            f"{label} must use the fixed preamble and one direct top-level network-mode case."
        ]
    if (
        sum(line.startswith("case ") for line in visible_lines) != 1
        or visible_lines.count("esac") != 1
        or re.search(r"(?m)^\s*(?:if|for|while|until|select)\b", "\n".join(visible_lines[:3]))
    ):
        return [
            f"{label} must keep its network-mode case reachable at top level."
        ]
    return []


def _validate_asdw_data_deploy_host_boundary(
    text: str,
    label: str,
) -> List[str]:
    """Permit only the fixed host grammar and direct Azure command shapes."""
    logical_commands = [
        _strip_shell_inline_comment(command).strip()
        for command in _extract_shell_logical_commands(text)
        if _strip_shell_inline_comment(command).strip()
    ]
    host_commands = [
        command
        for command in logical_commands
        if not _is_generated_shell_assignment(command, "non_audit_command")
    ]
    executable = "\n".join(host_commands)
    errors = _validate_asdw_data_deploy_top_level_shape(text, label)
    if executable.count("set -euo pipefail") != 1 or not executable.startswith(
        "set -euo pipefail\n"
    ):
        errors.append(f"{label} must enable set -euo pipefail as its first statement.")
    if executable.count(': "${HVE_ASDW_SCRIPT_DIR:?}"') != 1 or executable.count(
        'SCRIPT_DIR="$HVE_ASDW_SCRIPT_DIR"'
    ) != 1:
        errors.append(
            f"{label} must consume the launcher-owned HVE_ASDW_SCRIPT_DIR exactly once."
        )
    if re.search(r"BASH_SOURCE|\bdirname\b|\breadlink\b|\brealpath\b|\$0", executable):
        errors.append(
            f"{label} must not resolve its path dynamically outside the HVE launcher."
        )
    if _ASDW_DATA_CREATE_CHILD_REFERENCE.search(executable):
        errors.append(
            f"{label} must not child-execute registration, verifier, or the HVE launcher."
        )
    if re.search(
        r"(?:^|[;&|\n]\s*)(?:source\b|\.\s+|eval\b|exec\b|"
        r"(?:bash|sh)\s+-c\b|xargs\b|nohup\b|coproc\b)|"
        r"`|[<>]\(|\bsubprocess\b|\bos\.system\b|\bPopen\b",
        executable,
        re.IGNORECASE,
    ):
        errors.append(
            f"{label} must not use dynamic host execution or replay commands."
        )
    if _contains_shell_command_token(
        executable,
        "python",
        "python3",
        "sqlcmd",
        "psql",
        "curl",
        "wget",
    ):
        errors.append(
            f"{label} must keep SDK/data-plane execution inside its validated ACI payload."
        )
    allowed_az_prefixes = (
        _ASDW_PREP_DIRECT_AZ_PREFIXES
        if label.endswith("-prep.sh")
        else _ASDW_CREATE_DIRECT_AZ_PREFIXES
    )
    allowed_fixed = {
        "set -euo pipefail",
        ': "${HVE_ASDW_SCRIPT_DIR:?}"',
        'SCRIPT_DIR="$HVE_ASDW_SCRIPT_DIR"',
        # `az acr build` は Windows で絶対パス／多階層相対パスのソース指定を
        # 受理せず `Unable to find 'Dockerfile'.` で失敗する。カレントを移して
        # `.` を渡す形式だけが成立するため、この 2 文だけを許可する。
        'cd "$SCRIPT_DIR/data-verify"',
        'cd "$SCRIPT_DIR"',
        'case "${DATA_NETWORK_MODE:?}" in',
        "private)",
        "public)",
        "nsp)",
        "blocked)",
        "*)",
        ";;",
        "esac",
        "exit 1",
        "fi",
        "hve_policy_preflight_complete=1",
        'if [[ -z "$policy_assignments" || -z "$policy_exemptions" ]]; then',
        'if [[ ! "$DATA_CREATE_RUN_ID" =~ ^[0-9a-f]{32}$ ]]; then',
        "if ! command -v timeout >/dev/null 2>&1; then",
        "cleanup_data_aci() {",
        'if [[ "$data_aci_created" == "1" ]]; then',
        'if [[ "$data_aci_owner" == "$DATA_CREATE_RUN_ID" ]]; then',
        'if [[ "$data_aci_name_count" != "0" ]]; then',
        'if [[ "$data_aci_wait_failed" != "0" || "$data_aci_exit_code" != "0" || "$data_aci_logs" != "HVE_NON_AUDIT_REGISTRATION_OK" ]]; then',
        "}",
        "trap cleanup_data_aci EXIT INT TERM",
    }
    assignment_names = {
        "policy_assignments",
        "policy_exemptions",
        "data_identity_principal_id",
        "non_audit_command",
        "data_aci_name",
        "data_aci_created",
        "data_aci_wait_failed",
        "data_aci_logs",
        "data_aci_exit_code",
        "data_aci_owner",
        "data_aci_name_count",
    }
    for raw_command in _extract_shell_logical_commands(text):
        command = _strip_shell_inline_comment(raw_command).strip()
        if not command or command in allowed_fixed:
            continue
        if re.fullmatch(r': "\$\{[A-Za-z_][A-Za-z0-9_]*:\?\}"', command):
            continue
        if re.fullmatch(r"printf[ \t]+'\[ERROR\][^'\r\n]*(?:\\n)?'[ \t]+>&2", command):
            continue
        assignment_match = re.match(
            r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)=",
            command,
        )
        if assignment_match is not None:
            name = assignment_match.group("name")
            if name not in assignment_names:
                errors.append(
                    f"{label} host grammar rejects unknown assignment `{name}`."
                )
                continue
            if name == "policy_assignments" and re.fullmatch(
                r'policy_assignments="\$\(az policy assignment list '
                r'--scope "/subscriptions/\$SUBSCRIPTION_ID" --output json\)"',
                command,
            ):
                continue
            if name == "policy_exemptions" and re.fullmatch(
                r'policy_exemptions="\$\(az policy exemption list '
                r'--scope "/subscriptions/\$SUBSCRIPTION_ID" --output json\)"',
                command,
            ):
                continue
            if name == "non_audit_command" and _is_generated_shell_assignment(
                command,
                name,
            ):
                continue
            if name == "data_identity_principal_id" and command == (
                'data_identity_principal_id="$(az identity show --resource-group '
                '"$RESOURCE_GROUP" --name data-deploy-identity --query principalId '
                '--output tsv)"'
            ):
                continue
            if name == "data_aci_name" and command == (
                'data_aci_name="data-create-$DATA_CREATE_RUN_ID"'
            ):
                continue
            if name == "data_aci_created" and command in {
                "data_aci_created=0",
                "data_aci_created=1",
            }:
                continue
            if name == "data_aci_wait_failed" and command == "data_aci_wait_failed=0":
                continue
            if name == "data_aci_owner" and command == (
                'data_aci_owner="$(az container show --resource-group '
                '"$RESOURCE_GROUP" --name "$data_aci_name" --query '
                '"tags.hveCreateRunId" --output tsv 2>/dev/null || true)"'
            ):
                continue
            if name == "data_aci_name_count" and command == (
                'data_aci_name_count="$(az container list --resource-group '
                '"$RESOURCE_GROUP" --query "[?name==\'$data_aci_name\'] | '
                'length(@)" --output tsv)"'
            ):
                continue
            if name == "data_aci_logs" and command == (
                'data_aci_logs="$(timeout 600 az container logs --resource-group '
                '"$RESOURCE_GROUP" --name "$data_aci_name" --follow)" || '
                "data_aci_wait_failed=1"
            ):
                continue
            if name == "data_aci_exit_code" and command == (
                'data_aci_exit_code="$(az container show --resource-group '
                '"$RESOURCE_GROUP" --name "$data_aci_name" --query '
                '"containers[0].instanceView.currentState.exitCode" --output tsv)"'
            ):
                continue
            errors.append(
                f"{label} host grammar rejects noncanonical assignment `{name}`."
            )
            continue
        tokens = _asdw_shell_tokens(command)
        if command == (
            'az container delete --resource-group "$RESOURCE_GROUP" --name '
            '"$data_aci_name" --yes || true'
        ):
            continue
        if (
            tokens is not None
            and tokens
            and tokens[0] == "az"
            and _asdw_tokens_start_with(tokens, allowed_az_prefixes)
            and not any(token in {";", "&&", "||", "|", "&", ">", "<"} for token in tokens)
            and not any(
                re.search(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?", token)
                for token in tokens[1 : len(next(
                    prefix
                    for prefix in allowed_az_prefixes
                    if tuple(tokens[: len(prefix)]) == prefix
                ))]
            )
        ):
            continue
        errors.append(f"{label} host grammar rejects statement: {command[:160]}")
    return errors


def _asdw_data_create_command_offsets(text: str) -> List[Tuple[int, str]]:
    """Return logical commands with stable first-occurrence offsets."""
    result: List[Tuple[int, str]] = []
    cursor = 0
    for raw_command in _extract_shell_logical_commands(text):
        command = _strip_shell_inline_comment(raw_command).strip()
        if not command:
            continue
        offset = text.find(raw_command, cursor)
        if offset < 0:
            offset = text.find(command, cursor)
        if offset < 0:
            offset = cursor
        result.append((offset, command))
        cursor = max(cursor, offset + len(raw_command))
    return result


def _validate_asdw_data_policy_preflight(text: str, label: str) -> List[str]:
    """Require fail-closed policy inventory before every Azure mutation."""
    commands = _asdw_data_create_command_offsets(text)
    assignments = [
        offset
        for offset, command in commands
        if re.search(r"\baz\s+policy\s+assignment\s+list\b", command)
    ]
    exemptions = [
        offset
        for offset, command in commands
        if re.search(r"\baz\s+policy\s+exemption\s+list\b", command)
    ]
    markers = [
        offset
        for offset, command in commands
        if command == "hve_policy_preflight_complete=1"
    ]
    azure_writes = [
        offset
        for offset, command in commands
        if re.search(r"(?:^|[;&|]\s*|\$\(\s*)az\b", command)
        and _ASDW_DATA_CREATE_WRITE_VERB.search(
            re.sub(r"--query(?:\s+|=)(?:\"[^\"]*\"|'[^']*'|\S+)", "", command)
        )
    ]
    guard = re.search(
        r'if \[\[ -z "\$policy_assignments" \|\| -z "\$policy_exemptions" \]\]; then\s*'
        r"exit 1\s*fi",
        text,
        re.DOTALL,
    )
    if (
        len(assignments) != 1
        or len(exemptions) != 1
        or len(markers) != 1
        or guard is None
        or guard.start() <= max(assignments[0], exemptions[0])
        or guard.end() >= markers[0]
        or (azure_writes and markers[0] >= min(azure_writes))
    ):
        return [
            f"{label} must complete one fail-closed Policy pre-flight before its first Azure write."
        ]
    if re.search(r"\baz\s+rest\b(?![^\r\n]*--method(?:\s+|=)(?:GET|HEAD)\b)", text, re.IGNORECASE):
        return [f"{label} permits only explicit Azure REST GET/HEAD pre-flight calls."]
    return []


def _validate_asdw_data_create_aci_lifecycle(private: str) -> List[str]:
    """Require one owned, bounded, completion-checked non-Audit ACI."""
    commands = [
        _strip_shell_inline_comment(command).strip()
        for command in _extract_shell_logical_commands(private)
        if _strip_shell_inline_comment(command).strip()
    ]
    assignments = [
        index
        for index, command in enumerate(commands)
        if _is_generated_shell_assignment(command, "non_audit_command")
    ]
    create_indexes = [
        index
        for index, command in enumerate(commands)
        if re.match(r"^az[ \t]+container[ \t]+create\b", command)
    ]
    if len(assignments) != 1 or len(create_indexes) != 1:
        return [
            "DataDeploy non-Audit ACI lifecycle requires one payload assignment and one direct create."
        ]
    assignment_index = assignments[0]
    create_index = create_indexes[0]
    expected_before_create = [
        'data_aci_name="data-create-$DATA_CREATE_RUN_ID"',
        "data_aci_created=0",
        "cleanup_data_aci() {",
        'if [[ "$data_aci_created" == "1" ]]; then',
        'data_aci_owner="$(az container show --resource-group "$RESOURCE_GROUP" --name "$data_aci_name" --query "tags.hveCreateRunId" --output tsv 2>/dev/null || true)"',
        'if [[ "$data_aci_owner" == "$DATA_CREATE_RUN_ID" ]]; then',
        'az container delete --resource-group "$RESOURCE_GROUP" --name "$data_aci_name" --yes || true',
        "fi",
        "fi",
        "}",
        "trap cleanup_data_aci EXIT INT TERM",
        'data_aci_name_count="$(az container list --resource-group "$RESOURCE_GROUP" --query "[?name==\'$data_aci_name\'] | length(@)" --output tsv)"',
        'if [[ "$data_aci_name_count" != "0" ]]; then',
        "exit 1",
        "fi",
    ]
    if commands[assignment_index + 1 : create_index] != expected_before_create:
        return [
            "DataDeploy non-Audit ACI must use the canonical ownership-safe cleanup and collision sequence."
        ]
    expected_after_create = [
        "data_aci_created=1",
        "data_aci_wait_failed=0",
        'data_aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$data_aci_name" --follow)" || data_aci_wait_failed=1',
        'data_aci_exit_code="$(az container show --resource-group "$RESOURCE_GROUP" --name "$data_aci_name" --query "containers[0].instanceView.currentState.exitCode" --output tsv)"',
        'if [[ "$data_aci_wait_failed" != "0" || "$data_aci_exit_code" != "0" || "$data_aci_logs" != "HVE_NON_AUDIT_REGISTRATION_OK" ]]; then',
        "exit 1",
        "fi",
    ]
    if commands[create_index + 1 :] != expected_after_create:
        return [
            "DataDeploy non-Audit ACI must wait exactly 600 seconds at most, require exitCode 0 and the exact success marker, then cleanup."
        ]
    return []


def _validate_asdw_data_create_selected_resources(
    prep: str,
    create: str,
    audit_mode: str,
    sample_data_path: "Path | str | None",
    sample_data_text: Optional[str] = None,
) -> List[str]:
    """Require APP-009 selected stores and non-Audit sample coverage."""
    combined = prep + "\n" + create
    private = _extract_shell_case_branch(create, "DATA_NETWORK_MODE", "private")
    errors: List[str] = []
    decoded_source, decoded_source_errors = (
        _extract_asdw_non_audit_registration_source(private)
    )
    errors.extend(decoded_source_errors)
    for key in _ASDW_DATA_DEPLOY_NETWORK_KEYS:
        if not re.search(_shell_variable_pattern(key), combined):
            errors.append(f"DataDeploy prep/create must consume `${key}`.")
    for key in _ASDW_DATA_DEPLOY_NETWORK_KEYS[1:]:
        if f': "${{{key}:?}}"' not in prep + private:
            errors.append(
                f"DataDeploy prep/create must require `${key}` before Azure write."
            )
    for key in ("DATA_VERIFY_ACR_NAME", "DATA_VERIFY_IMAGE_NAME"):
        if f': "${{{key}:?}}"' not in prep:
            errors.append(
                f"DataDeploy prep must require `${key}` before Azure write."
            )

    required_prep_commands = (
        (
            'az acr create --resource-group "$RESOURCE_GROUP" '
            '--name "$DATA_VERIFY_ACR_NAME" --sku Basic --output none',
            "verification registry",
        ),
        (
            'cd "$SCRIPT_DIR/data-verify"\n'
            '    az acr build --registry "$DATA_VERIFY_ACR_NAME" '
            '--image "$DATA_VERIFY_IMAGE_NAME" --file Dockerfile .\n'
            '    cd "$SCRIPT_DIR"',
            "verification image build",
        ),
        (
            'az role assignment create --assignee "$data_identity_principal_id" '
            '--scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/'
            '$RESOURCE_GROUP/providers/Microsoft.ContainerRegistry/registries/'
            '$DATA_VERIFY_ACR_NAME" --role acrpull --output none',
            "acrpull role assignment",
        ),
    )
    for command, resource in required_prep_commands:
        if command not in prep:
            errors.append(
                f"DataDeploy prep must create the {resource} with the fixed command."
            )
    if re.search(r"--admin-enabled\s+true|\bdocker\s+login\b|\baz\s+acr\s+login\b", prep):
        errors.append(
            "DataDeploy prep must not enable the registry admin user or use a login secret."
        )

    required_commands = (
        (r"\baz\s+network\s+vnet\s+create\b", "private VNet"),
        (r"\baz\s+network\s+vnet\s+subnet\s+create\b", "private subnets"),
        (r"\baz\s+network\s+nat\s+gateway\s+create\b", "NAT Gateway"),
        (r"\baz\s+identity\s+create\b", "User-assigned Managed Identity"),
        (r"\baz\s+network\s+private-endpoint\s+create\b", "Private Endpoint"),
        (r"\baz\s+network\s+private-dns\s+zone\s+create\b", "Private DNS zone"),
        (r"\baz\s+sql\s+server\s+create\b", "Azure SQL server"),
        (r"\baz\s+sql\s+db\s+create\b", "Azure SQL database"),
        (r"\baz\s+cosmosdb\s+create\b", "Azure Cosmos DB account"),
        (r"\baz\s+cosmosdb\s+sql\s+database\s+create\b", "Cosmos database"),
        (r"\baz\s+cosmosdb\s+sql\s+container\s+create\b", "Cosmos container"),
        (r"\baz\s+confidentialledger\s+create\b", "Azure confidential ledger"),
    )
    for pattern, resource in required_commands:
        if re.search(pattern, combined) is None:
            errors.append(f"DataDeploy prep/create must create or reuse the selected {resource}.")

    def _commands(group: str) -> List[str]:
        return _find_az_commands(combined, group)

    private_endpoints = _commands("network private-endpoint create")
    for service, name_key, group_id, target_fragment in (
        ("SQL", "SQL_PRIVATE_ENDPOINT_NAME", "sqlServer", "Microsoft.Sql/servers"),
        ("Cosmos", "COSMOS_PRIVATE_ENDPOINT_NAME", "Sql", "Microsoft.DocumentDB/databaseAccounts"),
    ):
        matched = [
            command
            for command in private_endpoints
            if _command_option_references_variable(command, "--name", name_key)
            and _command_option_references_variable(
                command,
                "--subnet",
                "DATA_PRIVATE_ENDPOINT_SUBNET_ID",
            )
            and re.search(
                rf"--group-id(?:\s+|=)[\"']?{re.escape(group_id)}[\"']?(?:\s|$)",
                command,
            )
            and target_fragment in command
            and "--private-connection-resource-id" in command
        ]
        if len(matched) != 1:
            errors.append(
                f"DataDeploy private topology requires exactly one {service} Private Endpoint with the selected target, group ID, and subnet."
            )

    dns_zones = _commands("network private-dns zone create")
    dns_links = _commands("network private-dns link vnet create")
    dns_groups = _commands("network private-endpoint dns-zone-group create")
    for service, endpoint_key, zone_key in (
        ("SQL", "SQL_PRIVATE_ENDPOINT_NAME", "SQL_PRIVATE_DNS_ZONE"),
        ("Cosmos", "COSMOS_PRIVATE_ENDPOINT_NAME", "COSMOS_PRIVATE_DNS_ZONE"),
    ):
        if sum(
            _command_option_references_variable(command, "--name", zone_key)
            for command in dns_zones
        ) != 1:
            errors.append(
                f"DataDeploy private topology requires exactly one {service} Private DNS zone."
            )
        if sum(
            _command_option_references_variable(command, "--zone-name", zone_key)
            and _command_option_references_variable(
                command,
                "--virtual-network",
                "DATA_VNET_NAME",
            )
            for command in dns_links
        ) != 1:
            errors.append(
                f"DataDeploy private topology requires exactly one {service} Private DNS VNet link."
            )
        if sum(
            _command_option_references_variable(
                command,
                "--endpoint-name",
                endpoint_key,
            )
            and _command_option_references_variable(command, "--zone-name", zone_key)
            for command in dns_groups
        ) != 1:
            errors.append(
                f"DataDeploy private topology requires exactly one {service} Private Endpoint DNS zone group."
            )

    aci_subnet_updates = _commands("network vnet subnet update")
    if not any(
        _command_option_references_variable(
            command,
            "--ids",
            "DATA_ACI_SUBNET_ID",
        )
        and _command_option_references_variable(
            command,
            "--nat-gateway",
            "DATA_NAT_GATEWAY_NAME",
        )
        and "Microsoft.ContainerInstance/containerGroups" in command
        for command in aci_subnet_updates
    ):
        errors.append(
            "DataDeploy private topology must delegate the ACI subnet and attach the selected NAT Gateway."
        )

    sql_create = "\n".join(_find_az_commands(create, "sql server create"))
    cosmos_create = "\n".join(_find_az_commands(create, "cosmosdb create"))
    if "--enable-ad-only-auth" not in sql_create:
        errors.append("DataDeploy SQL creation must enforce Microsoft Entra-only authentication.")
    if not re.search(
        r"--enable-public-network(?:\s+|=)false|publicNetworkAccess=Disabled",
        sql_create,
        re.IGNORECASE,
    ):
        errors.append("DataDeploy SQL creation must disable public network access.")
    if not re.search(
        r"--disable-local-auth(?:\s+|=)true", cosmos_create, re.IGNORECASE
    ) or not re.search(
        r"--public-network-access(?:\s+|=)Disabled", cosmos_create, re.IGNORECASE
    ):
        errors.append(
            "DataDeploy Cosmos creation must disable local auth and public network access."
        )

    if audit_mode == _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST:
        for key in ("SQL_DB_SVC12", "SQL_AUDIT_TABLE"):
            if f': "${{{key}:?}}"' not in private:
                errors.append(f"sql-ledger-digest create must require `${key}`.")
        digest_commands = _find_az_commands(
            private,
            "sql db ledger-digest-uploads enable",
        )
        if (
            "APPEND_ONLY" not in decoded_source
            or "sys.database_ledger_digest_locations" not in decoded_source
            or len(digest_commands) != 1
            or not _command_option_references_variable(
                digest_commands[0], "--name", "SQL_DB_SVC12"
            )
            or not _command_option_references_variable(
                digest_commands[0], "--endpoint", "CONFIDENTIAL_LEDGER_ENDPOINT"
            )
        ):
            errors.append(
                "sql-ledger-digest create must provision an append-only ledger table and digest target."
            )
    elif audit_mode == _ASDW_AUDIT_MODE_ACL_DIRECT:
        if ': "${CONFIDENTIAL_LEDGER_COLLECTION:?}"' not in private:
            errors.append("acl-direct create must require `CONFIDENTIAL_LEDGER_COLLECTION`.")

    counts, sample_error = _load_asdw_sample_counts(
        sample_data_path,
        sample_data_text,
    )
    if sample_error is not None:
        return errors + [sample_error]
    required_entities = {
        entity for entity, _database, _table in _ASDW_APP009_SQL_COVERAGE
    } | {"VocRecord", "AuditRecord"}
    missing = sorted(required_entities - counts.keys())
    empty = sorted(entity for entity in required_entities if counts.get(entity, 0) <= 0)
    if missing:
        errors.append(
            "DataDeploy sample-data must contain list values for: " + ", ".join(missing) + "."
        )
    if empty:
        errors.append(
            "DataDeploy sample-data must contain nonzero records for: " + ", ".join(empty) + "."
        )
    if not missing and not empty:
        if not decoded_source_errors:
            try:
                actual_program = ast.parse(decoded_source)
                expected_program = ast.parse(
                    _build_asdw_non_audit_registration_source(counts, audit_mode)
                )
            except SyntaxError:
                errors.append(
                    "DataDeploy non-Audit registration Python source is not parseable."
                )
            else:
                if ast.dump(actual_program) != ast.dump(expected_program):
                    errors.append(
                        "DataDeploy non-Audit registration must use the canonical executable sample-data, mapping, idempotency, AuditRecord-separation, and cleanup sequence."
                    )

    aci_commands = _find_az_commands(private, "container create")
    if len(aci_commands) != 1:
        errors.append("DataDeploy non-Audit registration must use exactly one private ACI.")
    else:
        aci = aci_commands[0]
        for option, variable in (
            ("--image", "DATA_VERIFY_ACI_IMAGE"),
            ("--subnet", "DATA_ACI_SUBNET_ID"),
            ("--acr-identity", "DATA_DEPLOY_IDENTITY_ID"),
            ("--assign-identity", "DATA_DEPLOY_IDENTITY_ID"),
            ("--command-line", "non_audit_command"),
        ):
            if not _command_option_references_variable(aci, option, variable):
                errors.append(
                    f"DataDeploy non-Audit ACI `{option}` must reference `${variable}`."
                )
        for fixed in ("--restart-policy Never", "--os-type Linux", "--cpu 1", "--memory 1"):
            if fixed not in aci:
                errors.append(f"DataDeploy non-Audit ACI must set `{fixed}`.")
        if not re.search(
            r"--secure-environment-variables\s+"
            r'NON_AUDIT_DATA_JSON="\$HVE_ASDW_SAMPLE_DATA_JSON"',
            aci,
        ):
            errors.append(
                "DataDeploy non-Audit ACI must receive only the launcher-pinned sample JSON through its secure environment."
            )
    errors.extend(_validate_asdw_data_create_aci_lifecycle(private))
    return errors


def validate_asdw_data_create_scripts(
    prep_path: "Path | str",
    create_path: "Path | str",
    *,
    design_doc_path: "Path | str | None" = None,
    sample_data_path: "Path | str | None" = None,
    prep_text: Optional[str] = None,
    create_text: Optional[str] = None,
    sample_data_text: Optional[str] = None,
    design_doc_text: Optional[str] = None,
) -> List[str]:
    """Validate Step 1.3 prep/create before an HVE-owned byte-pinned launch."""
    prep, prep_errors = _load_asdw_data_deploy_shell_text(
        prep_path,
        "create-azure-data-resources-prep.sh",
        prep_text,
    )
    create, create_errors = _load_asdw_data_deploy_shell_text(
        create_path,
        "create-azure-data-resources.sh",
        create_text,
    )
    errors = prep_errors + create_errors
    if errors:
        return errors
    prep_block, marker_errors = _extract_asdw_data_deploy_marker_block(
        prep,
        begin=_ASDW_DATA_PREP_BEGIN,
        end=_ASDW_DATA_PREP_END,
        label="create-azure-data-resources-prep.sh",
    )
    errors.extend(marker_errors)
    create_block, marker_errors = _extract_asdw_data_deploy_marker_block(
        create,
        begin=_ASDW_DATA_CREATE_BEGIN,
        end=_ASDW_DATA_CREATE_END,
        label="create-azure-data-resources.sh",
    )
    errors.extend(marker_errors)
    if errors:
        return errors

    audit_mode, audit_errors = _resolve_asdw_audit_storage_mode(
        design_doc_path,
        design_doc_text,
    )
    errors.extend(audit_errors)
    if audit_errors or audit_mode is None:
        return errors
    for block, label in (
        (prep_block, "create-azure-data-resources-prep.sh"),
        (create_block, "create-azure-data-resources.sh"),
    ):
        errors.extend(_validate_asdw_network_case_contract(block))
        errors.extend(_validate_asdw_non_private_branches(block))
        errors.extend(_validate_asdw_data_deploy_host_boundary(block, label))
        errors.extend(_validate_asdw_data_policy_preflight(block, label))
        if _ASDW_DATA_CREATE_FORBIDDEN_PUBLIC.search(block):
            errors.append(
                f"{label} must not enable public access or create a firewall fallback."
            )
        if _ASDW_DATA_CREATE_FORBIDDEN_SECRET.search(block):
            errors.append(
                f"{label} must not acquire or use a shared secret, password, or bearer token."
            )
        if _ASDW_DATA_CREATE_FORBIDDEN_AUDIT_WRITE.search(block):
            errors.append(
                f"{label} must not register the AuditRecord payload; registration is a separate launcher stage."
            )
    errors.extend(
        _validate_asdw_data_create_selected_resources(
            prep_block,
            create_block,
            audit_mode,
            sample_data_path,
            sample_data_text,
        )
    )
    return errors


_ASDW_AUDIT_REGISTRATION_BEGIN = "# HVE-AUDIT-REGISTRATION-BEGIN"
_ASDW_AUDIT_REGISTRATION_END = "# HVE-AUDIT-REGISTRATION-END"


def _extract_asdw_audit_registration_block(
    text: str,
) -> Tuple[str, List[str]]:
    """Extract the Audit-only block fixed immediately after the Bash shebang."""
    lines = text.splitlines()
    begin_indexes = [
        index
        for index, line in enumerate(lines)
        if line == _ASDW_AUDIT_REGISTRATION_BEGIN
    ]
    end_indexes = [
        index
        for index, line in enumerate(lines)
        if line == _ASDW_AUDIT_REGISTRATION_END
    ]
    if (
        len(begin_indexes) != 1
        or len(end_indexes) != 1
        or begin_indexes[0] >= end_indexes[0]
    ):
        return "", [
            "AuditRecord registration requires exactly one ordered pair of "
            "HVE-AUDIT-REGISTRATION markers."
        ]
    begin_index = begin_indexes[0]
    end_index = end_indexes[0]
    if (
        not lines
        or lines[0] != "#!/usr/bin/env bash"
        or begin_index != 1
    ):
        return "", [
            "AuditRecord registration BEGIN marker must be the direct second "
            "physical line immediately after `#!/usr/bin/env bash`."
        ]
    block = "\n".join(lines[begin_index + 1 : end_index]).strip()
    if not block:
        return "", ["AuditRecord registration marker block must not be empty."]
    return block + "\n", []


def _asdw_audit_registration_host_statement_is_allowed(command: str) -> bool:
    """Accept one statement from the fixed Audit registration host grammar."""
    line = _strip_shell_inline_comment(command).strip()
    if not line:
        return True
    if line in {
        "set -euo pipefail",
        'aci_name="data-register-$DATA_REGISTER_RUN_ID"',
        "aci_created=0",
        "aci_created=1",
        "aci_wait_failed=0",
        "cleanup_aci() {",
        'if [[ "$aci_created" == "1" ]]; then',
        'if [[ "$aci_owner" == "$DATA_REGISTER_RUN_ID" ]]; then',
        'if [[ "$aci_wait_failed" != "0" || "$aci_exit_code" != "0" '
        '|| "$aci_logs" != "HVE_AUDIT_REGISTRATION_OK" ]]; then',
        "fi",
        "}",
        "trap cleanup_aci EXIT INT TERM",
        'if az container show --resource-group "$RESOURCE_GROUP" '
        '--name "$aci_name" --only-show-errors; then',
        "exit 1",
        'aci_owner="$(az container show --resource-group "$RESOURCE_GROUP" '
        '--name "$aci_name" --query "tags.hveRegisterRunId" --output tsv '
        '2>/dev/null || true)"',
        'az container delete --resource-group "$RESOURCE_GROUP" '
        '--name "$aci_name" --yes || true',
        'aci_logs="$(timeout 600 az container logs --resource-group '
        '"$RESOURCE_GROUP" --name "$aci_name" --follow)" || aci_wait_failed=1',
        'aci_exit_code="$(az container show --resource-group "$RESOURCE_GROUP" '
        '--name "$aci_name" --query '
        '"containers[0].instanceView.currentState.exitCode" --output tsv)"',
    }:
        return True
    if re.fullmatch(r':\s+"\$\{[A-Za-z_][A-Za-z0-9_]*:\?\}"', line):
        return True
    if _is_generated_shell_assignment(command, "aci_command"):
        assignment = _split_generated_quoted_assignment(command, "aci_command")
        return bool(
            assignment is not None
            and not assignment[1]
            and not _has_disallowed_generated_assignment_evaluation(
                assignment[0]
            )
        )
    return bool(
        re.match(r"^az[ \t]+container[ \t]+create\b", line)
        and not _has_unquoted_shell_control_operator(line)
        and re.search(r"`|\$\(|[<>]\(", line) is None
    )


def _validate_asdw_audit_registration_block_structure(
    block: str,
) -> List[str]:
    """Permit only the canonical shell compound structure in the Audit block."""
    logical_commands = _extract_shell_logical_commands(block)
    structural_lines: List[str] = []
    function_like_lines: List[str] = []
    for raw_command in logical_commands:
        if _is_generated_shell_assignment(raw_command, "aci_command"):
            continue
        line = _strip_shell_inline_comment(raw_command).strip()
        if not line:
            continue
        if "<<" in line or re.search(r"[<>]\(", line):
            return [
                "AuditRecord registration marker block must not contain a "
                "heredoc or process substitution."
            ]
        if line == "cleanup_aci() {" or re.match(
            r"^(?:if|then|elif|else|fi|for|while|until|select|do|done|"
            r"case|esac|function)\b",
            line,
        ) or line in {"(", ")", "{", "}"}:
            structural_lines.append(line)
        if (
            re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\s*(?:\(\))?", line)
            and line not in {"then", "elif", "else", "fi", "do", "done", "in", "esac"}
        ):
            function_like_lines.append(line)

    expected_structural_lines = [
        "cleanup_aci() {",
        'if [[ "$aci_created" == "1" ]]; then',
        'if [[ "$aci_owner" == "$DATA_REGISTER_RUN_ID" ]]; then',
        "fi",
        "fi",
        "}",
        'if az container show --resource-group "$RESOURCE_GROUP" '
        '--name "$aci_name" --only-show-errors; then',
        "fi",
        'if [[ "$aci_wait_failed" != "0" || "$aci_exit_code" != "0" '
        '|| "$aci_logs" != "HVE_AUDIT_REGISTRATION_OK" ]]; then',
        "fi",
    ]
    if (
        structural_lines != expected_structural_lines
        or function_like_lines
    ):
        return [
            "AuditRecord registration marker block must use only the canonical "
            "cleanup function and collision guard shell structure."
        ]
    visible_commands = [
        _strip_shell_inline_comment(command).strip()
        for command in logical_commands
        if _strip_shell_inline_comment(command).strip()
    ]
    if (
        not visible_commands
        or visible_commands[0] != "set -euo pipefail"
        or visible_commands.count("set -euo pipefail") != 1
        or any(
            not _asdw_audit_registration_host_statement_is_allowed(command)
            for command in logical_commands
        )
    ):
        return [
            "AuditRecord registration marker block host statement allowlist "
            "permits only the canonical fail-fast setup, guards, ownership "
            "lifecycle, ACI payload assignment, and ACI create statement."
        ]
    for command in logical_commands:
        if _is_generated_shell_assignment(command, "aci_command"):
            continue
        visible_command = _strip_shell_inline_comment(command).strip()
        if not visible_command:
            continue
        if re.search(r"&&\s*\{|[;&|]\s*\{|}\s*(?:&&|\|\||;)", visible_command):
            return [
                "AuditRecord registration marker block must not be wrapped in a "
                "compound brace command or status mask."
            ]
    return []


def _validate_asdw_outside_audit_registration_block(text: str) -> List[str]:
    """Keep every Audit-specific input and write inside the validated block."""
    lines = text.splitlines()
    try:
        begin_index = lines.index(_ASDW_AUDIT_REGISTRATION_BEGIN)
        end_index = lines.index(_ASDW_AUDIT_REGISTRATION_END)
    except ValueError:
        return []
    outside_lines = lines[:begin_index] + lines[end_index + 1 :]
    non_comment_lines: List[str] = []
    executable_lines: List[str] = []
    for raw_line in outside_lines:
        line = _strip_shell_inline_comment(raw_line).strip()
        if not line:
            continue
        non_comment_lines.append(line)
        if re.fullmatch(
            r"printf[ \t]+'%s\\n'[ \t]+'[^'\r\n]*'",
            line,
        ):
            continue
        executable_lines.append(line)
    outside = "\n".join(executable_lines)
    outside_with_logs = "\n".join(non_comment_lines)
    if re.search(r"(?m)^}\s*(?:&&|\|\||;)", outside_with_logs):
        return [
            "complete data-registration-script.sh must not close or status-mask "
            "an Audit marker block from outside the validated boundary."
        ]
    audit_inputs = re.compile(
        r"AUDIT_RECORD_JSON|auditEventId|SQL_AUDIT_TABLE|SQL_DB_SVC12|"
        r"CONFIDENTIAL_LEDGER_COLLECTION",
        re.IGNORECASE,
    )
    acl_writes = re.compile(
        r"\b(?:begin_)?create_ledger_entry\s*\(",
        re.IGNORECASE,
    )
    acl_method_aliases = {
        match.group("alias")
        for match in re.finditer(
            r"\b(?P<alias>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
            r"[A-Za-z_][A-Za-z0-9_]*\.(?:begin_)?create_ledger_entry\b",
            outside,
        )
    }
    has_aliased_acl_write = any(
        re.search(rf"\b{re.escape(alias)}\s*\(", outside)
        for alias in acl_method_aliases
    )
    if (
        audit_inputs.search(outside)
        or acl_writes.search(outside)
        or has_aliased_acl_write
    ):
        return [
            "complete data-registration-script.sh must keep every AuditRecord "
            "input and SQL/ACL write inside its validated marker block."
        ]
    known_tables = {
        table.casefold() for _entity, _database, table in _ASDW_APP009_SQL_COVERAGE
    }
    sql_write = re.compile(
        r"(?i)\b(?:INSERT\s+INTO|MERGE(?:\s+INTO)?|UPDATE|"
        r"DELETE(?:\s+[A-Za-z_][A-Za-z0-9_]*)?\s+FROM)\s+"
        r"(?P<target>(?:\[?dbo\]?\s*\.\s*)?\[?[A-Za-z_][A-Za-z0-9_]*\]?)"
    )
    write_keywords = list(
        re.finditer(
            r"(?i)\b(?:INSERT\s+INTO|MERGE(?:\s+INTO)?|UPDATE|"
            r"DELETE(?:\s+[A-Za-z_][A-Za-z0-9_]*)?\s+FROM)\b",
            outside,
        )
    )
    recognized_offsets: set[int] = set()
    for match in sql_write.finditer(outside):
        unresolved_suffix = outside[match.end() : match.end() + 16].lstrip()
        if unresolved_suffix.startswith((".", "{", "$")):
            return [
                "complete data-registration-script.sh must not use a dynamic or "
                "unresolved SQL write target outside the Audit block."
            ]
        target = re.sub(r"[\[\]\s]", "", match.group("target"))
        table = target.rsplit(".", 1)[-1].casefold()
        if table == "set" and match.group(0).lstrip().upper().startswith("UPDATE"):
            continue
        recognized_offsets.add(match.start())
        if table not in known_tables:
            return [
                "complete data-registration-script.sh must keep SQL writes outside "
                "the Audit block limited to the ten known non-Audit tables."
            ]
    for keyword in write_keywords:
        if keyword.start() in recognized_offsets:
            continue
        if keyword.group(0).strip().upper() == "UPDATE":
            suffix = outside[keyword.end() : keyword.end() + 16]
            if re.match(r"\s+SET\b", suffix, re.IGNORECASE):
                continue
        return [
            "complete data-registration-script.sh must not use a dynamic or "
            "unresolved SQL write target outside the Audit block."
        ]
    if re.search(
        r"\b(?:execute|executemany)\s*\(\s*"
        r"[A-Za-z_][A-Za-z0-9_]*\s*(?:[,)]|$)",
        outside,
    ):
        return [
            "complete data-registration-script.sh must not execute a dynamically "
            "constructed SQL statement outside the Audit block."
        ]
    if outside:
        return [
            "complete data-registration-script.sh must not execute any statement "
            "outside its validated Audit marker block."
        ]
    return []


def _extract_asdw_registration_python_source(text: str) -> Tuple[str, List[str]]:
    """Extract one direct ``python -c`` source from the registration ACI."""
    commands = _extract_shell_logical_commands(text)
    assignments = [
        command
        for command in commands
        if _is_generated_shell_assignment(command, "aci_command")
    ]
    if len(assignments) != 1:
        return "", [
            "AuditRecord registration requires exactly one direct `aci_command` assignment."
        ]
    assignment = _split_generated_quoted_assignment(assignments[0], "aci_command")
    if assignment is None or assignment[1]:
        return "", [
            "AuditRecord registration `aci_command` must be one direct quoted assignment."
        ]
    payload = assignment[0].replace(r'\"', '"')
    if len(payload) < 2 or payload[0] != '"' or payload[-1] != '"':
        return "", [
            "AuditRecord registration `aci_command` must use a double-quoted assignment."
        ]
    command = payload[1:-1]
    prefix = "python -c '"
    if not command.startswith(prefix) or not command.endswith("'"):
        return "", [
            "AuditRecord registration ACI must execute exactly one `python -c` payload."
        ]
    source = command[len(prefix):-1]
    if not source or "'" in source:
        return "", [
            "AuditRecord registration Python source must use one unbroken quoted argument."
        ]
    create_commands = _find_az_commands(text, "container create")
    if len(create_commands) != 1 or not _command_option_references_variable(
        create_commands[0], "--command-line", "aci_command"
    ):
        return "", [
            "AuditRecord registration ACI create must execute `--command-line \"$aci_command\"`."
        ]
    return source, []


def _validate_asdw_sql_audit_registration(source: str) -> List[str]:
    """Validate one SVC-12 AuditRecord payload insert for SQL ledger mode."""
    try:
        program = ast.parse(source)
    except SyntaxError:
        return ["SQL AuditRecord registration Python source is not parseable."]
    canonical_program = ast.parse(_ASDW_SQL_AUDIT_REGISTRATION_SOURCE)
    if ast.dump(program) == ast.dump(canonical_program):
        return []
    return [
        "SQL AuditRecord registration must use the fixed idempotent sequence.",
        "AuditRecord registration must use exactly its canonical imports without aliases or extra modules.",
        "AuditRecord registration canonical imports must precede every runtime initialization.",
        "AuditRecord registration must not rebind canonical imports/builtins or mutate attributes/subscripts.",
        "AuditRecord registration must use one direct straight-line top-level try/finally without early termination.",
        "SQL AuditRecord registration must initialize resources before try and must not rebind its data-flow values.",
        "SQL AuditRecord registration must validate SQL_AUDIT_TABLE as a safe identifier and trim auditEventId from AUDIT_RECORD_JSON.",
        "SQL AuditRecord registration must require auditEventId to be a string and reject a non-normalized ID.",
        "SQL AuditRecord registration JSON serialization must be canonical and type-preserving.",
        "SQL AuditRecord registration must execute exactly one canonical idempotent range-locked conditional INSERT/read-back batch.",
        "SQL AuditRecord registration must fail closed for a missing row, duplicate rows, or a different payload.",
        "SQL AuditRecord registration must commit exactly once after the idempotent read-back guard.",
        "SQL AuditRecord registration must use exception-safe resource cleanup to close cursor then connection.",
        "SQL AuditRecord registration must not write AuditRecord to Azure confidential ledger application entries.",
    ]


def _validate_asdw_acl_direct_audit_registration(source: str) -> List[str]:
    """Validate one ACL application-entry AuditRecord write."""
    try:
        program = ast.parse(source)
    except SyntaxError:
        return ["ACL-direct AuditRecord registration Python source is not parseable."]
    canonical_program = ast.parse(_ASDW_ACL_AUDIT_REGISTRATION_SOURCE)
    if ast.dump(program) == ast.dump(canonical_program):
        return []
    return [
        "ACL-direct AuditRecord registration must use the fixed idempotent sequence.",
        "AuditRecord registration must use exactly its canonical imports without aliases or extra modules.",
        "AuditRecord registration canonical imports must precede every runtime initialization.",
        "AuditRecord registration must not rebind canonical imports/builtins or mutate attributes/subscripts.",
        "AuditRecord registration must use one direct straight-line top-level try/finally without early termination.",
        "ACL-direct AuditRecord registration must initialize resources before try and must not rebind its identity or data-flow values.",
        "ACL-direct AuditRecord registration requires one fresh ledger TLS certificate path and one UAMI credential.",
        "ACL-direct AuditRecord registration must require auditEventId to be a string, trim auditEventId, and reject a non-normalized ID.",
        "ACL-direct AuditRecord registration JSON serialization must be canonical and type-preserving.",
        "ACL-direct AuditRecord registration must list and decode a bounded collection view exactly once.",
        "ACL-direct AuditRecord registration must fail closed for malformed entries or more than one existing auditEventId entry.",
        "ACL-direct AuditRecord registration must use one same-payload no-op branch and one absent-only append branch.",
        "ACL-direct AuditRecord registration must fail closed when an existing auditEventId has a different payload.",
        "ACL-direct AuditRecord registration must write exactly one application entry only when absent.",
        "ACL-direct AuditRecord registration must use exception-safe cleanup to close client then credential and the TLS directory.",
        "ACL-direct AuditRecord registration must not require SVC-12 Audit SQL.",
    ]


def _validate_asdw_registration_mode_wiring(
    text: str,
    audit_mode: str,
) -> List[str]:
    """Validate mode-selected registration ACI identity and environment wiring."""
    commands = [
        _strip_shell_inline_comment(command).strip()
        for command in _extract_shell_logical_commands(text)
    ]
    create_indexes = [
        index
        for index, command in enumerate(commands)
        if re.match(r"^az[ \t]+container[ \t]+create\b", command)
    ]
    assignment_indexes = [
        index
        for index, command in enumerate(commands)
        if _is_generated_shell_assignment(command, "aci_command")
    ]
    if (
        len(create_indexes) != 1
        or len(assignment_indexes) != 1
        or assignment_indexes[0] >= create_indexes[0]
    ):
        return [
            "AuditRecord registration must assign one direct aci_command before "
            "one az container create."
        ]
    if assignment_indexes[0] + 1 != create_indexes[0]:
        return [
            "AuditRecord registration aci_command assignment must be immediately "
            "followed by az container create."
        ]
    create = commands[create_indexes[0]]
    azure_commands = [
        command
        for command in commands
        if re.search(r"(?<![-A-Za-z0-9_])az(?![-A-Za-z0-9_])", command)
    ]
    allowed_azure_shapes = (
        re.compile(r'^aci_owner="\$\(az container show\b'),
        re.compile(r'^aci_logs="\$\(timeout 600 az container logs\b'),
        re.compile(r'^aci_exit_code="\$\(az container show\b'),
        re.compile(r'^az container delete\b'),
        re.compile(r'^if az container show\b'),
        re.compile(r'^az container create\b'),
    )
    if any(
        sum(pattern.search(command) is not None for pattern in allowed_azure_shapes)
        != 1
        or len(
            re.findall(r"(?<![-A-Za-z0-9_])az(?![-A-Za-z0-9_])", command)
        )
        != 1
        or re.search(r"`|[<>]\(", command) is not None
        or (
            "$(" in command
            and not command.startswith(
                (
                    'aci_owner="$(az container show',
                    'aci_logs="$(timeout 600 az container logs',
                    'aci_exit_code="$(az container show',
                )
            )
        )
        for command in azure_commands
    ):
        return [
            "AuditRecord registration permits only direct owner-check, cleanup, "
            "collision-check, and create Azure CLI lifecycle commands."
        ]
    first_azure_offset = _find_first_executable_az_command_offset(text)
    common_keys = [
        "DATA_REGISTER_RUN_ID",
        "RESOURCE_GROUP",
        "DATA_ACI_SUBNET_ID",
        "DATA_DEPLOY_IDENTITY_ID",
        "DATA_DEPLOY_IDENTITY_CLIENT_ID",
        "DATA_VERIFY_ACI_IMAGE",
        "AUDIT_RECORD_JSON",
    ]
    if audit_mode == _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST:
        mode_keys = ["SQL_HOST", "SQL_DB_SVC12", "SQL_AUDIT_TABLE"]
        opposite_keys = ["CONFIDENTIAL_LEDGER_COLLECTION"]
    else:
        mode_keys = [
            "CONFIDENTIAL_LEDGER_ENDPOINT",
            "CONFIDENTIAL_LEDGER_COLLECTION",
        ]
        opposite_keys = ["SQL_DB_SVC12", "SQL_AUDIT_TABLE"]
    errors: List[str] = []
    expected_guards = [
        f': "${{{key}:?}}"'
        for key in common_keys + mode_keys
    ]
    actual_guards = [
        command
        for command in commands
        if re.fullmatch(
            r':\s+"\$\{[A-Za-z_][A-Za-z0-9_]*:\?\}"',
            command,
        )
    ]
    if actual_guards != expected_guards:
        errors.append(
            "AuditRecord registration guards must exactly match the canonical "
            "common and selected-mode key sequence."
        )
    for key in common_keys + mode_keys:
        guard = f': "${{{key}:?}}"'
        guard_offsets = [
            match.start()
            for match in re.finditer(
                rf'(?m)^\s*:\s+"\$\{{{re.escape(key)}:\?\}}"\s*$',
                text,
            )
        ]
        if (
            len(guard_offsets) != 1
            or commands.count(guard) != 1
            or first_azure_offset is None
            or guard_offsets[0] >= first_azure_offset
        ):
            errors.append(
                f"AuditRecord registration must require `${key}` before Azure CLI."
            )
    def _exact_variable_option(option: str, variable: str) -> bool:
        option_count = len(
            re.findall(rf"(?<!\S){re.escape(option)}(?=\s|=)", create)
        )
        exact_count = len(
            re.findall(
                rf"(?<!\S){re.escape(option)}(?:\s+|=)"
                rf"\"\${re.escape(variable)}\""
                rf"(?=\s|$)",
                create,
            )
        )
        return option_count == 1 and exact_count == 1

    for option, variable in (
        ("--resource-group", "RESOURCE_GROUP"),
        ("--name", "aci_name"),
        ("--image", "DATA_VERIFY_ACI_IMAGE"),
        ("--subnet", "DATA_ACI_SUBNET_ID"),
        ("--acr-identity", "DATA_DEPLOY_IDENTITY_ID"),
        ("--assign-identity", "DATA_DEPLOY_IDENTITY_ID"),
        ("--command-line", "aci_command"),
    ):
        if not _exact_variable_option(option, variable):
            errors.append(
                f"AuditRecord registration ACI `{option}` must reference `${variable}`."
            )
    for option, value in (
        ("--restart-policy", "Never"),
        ("--os-type", "Linux"),
        ("--cpu", "1"),
        ("--memory", "1"),
    ):
        option_count = len(
            re.findall(rf"(?<!\S){re.escape(option)}(?=\s|=)", create)
        )
        exact_count = len(
            re.findall(
                rf"(?<!\S){re.escape(option)}(?:\s+|=)"
                rf"(?:{re.escape(value)}|\"{re.escape(value)}\"|'{re.escape(value)}')"
                rf"(?=\s|$)",
                create,
            )
        )
        if option_count != 1 or exact_count != 1:
            errors.append(
                f"AuditRecord registration ACI must set `{option} {value}` exactly once."
            )
    if re.search(
        r'--command-line[ \t]+"\$aci_command"\s*$',
        create,
    ) is None:
        errors.append(
            "AuditRecord registration ACI command-line must be exactly "
            "`\"$aci_command\"` with no prefix, suffix, or status mask."
        )
    canonical_assignment_index = assignment_indexes[0]
    assert canonical_assignment_index + 1 == create_indexes[0]
    secure_section = (
        create.split("--secure-environment-variables", 1)[1]
        .split("--environment-variables", 1)[0]
        if "--secure-environment-variables" in create
        and "--environment-variables" in create
        else ""
    )
    environment_section = (
        create.split("--environment-variables", 1)[1]
        .split("--command-line", 1)[0]
        if "--environment-variables" in create
        and "--command-line" in create
        else ""
    )
    if (
        create.count("--secure-environment-variables") != 1
        or create.count("--environment-variables") != 1
        or create.count("--command-line") != 1
        or create.index("--secure-environment-variables")
        >= create.index("--environment-variables")
        or create.index("--environment-variables")
        >= create.index("--command-line")
    ):
        errors.append(
            "AuditRecord registration ACI must order one secure environment section, "
            "one regular environment section, then one command-line option."
        )

    def _exact_shell_assignment(section: str, key: str) -> bool:
        values = re.findall(
            rf"(?<!\S){re.escape(key)}=(\"[^\"]*\")(?=\s|$)",
            section,
        )
        return len(values) == 1 and values[0] == f'"${key}"'

    def _parse_environment_section(section: str) -> Optional[List[Tuple[str, str]]]:
        assignments: List[Tuple[str, str]] = []
        position = 0
        token = re.compile(
            r"\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)="
            r'"\$(?P<source>[A-Za-z_][A-Za-z0-9_]*)"'
        )
        while position < len(section):
            if not section[position:].strip():
                position = len(section)
                break
            match = token.match(section, position)
            if match is None:
                return None
            assignments.append((match.group("name"), match.group("source")))
            position = match.end()
        return assignments

    secure_assignments = _parse_environment_section(secure_section)
    expected_environment_assignments = [
        ("AZURE_CLIENT_ID", "DATA_DEPLOY_IDENTITY_CLIENT_ID"),
        *((key, key) for key in mode_keys),
    ]
    environment_assignments = _parse_environment_section(environment_section)
    if secure_assignments != [("AUDIT_RECORD_JSON", "AUDIT_RECORD_JSON")]:
        errors.append(
            "AuditRecord registration secure environment must contain only "
            "AUDIT_RECORD_JSON exactly once."
        )
    if environment_assignments != expected_environment_assignments:
        errors.append(
            "AuditRecord registration regular environment assignments must exactly "
            "match AZURE_CLIENT_ID and the selected Audit storage mode."
        )

    if not _exact_shell_assignment(
        secure_section,
        "AUDIT_RECORD_JSON",
    ):
        errors.append(
            "AuditRecord registration ACI must transfer AUDIT_RECORD_JSON once "
            "through secure environment variables."
        )
    if re.search(r"(?<!\S)AUDIT_RECORD_JSON\s*=", environment_section):
        errors.append(
            "AuditRecord registration ACI must not duplicate AUDIT_RECORD_JSON "
            "in regular environment variables."
        )
    for key in ["DATA_DEPLOY_IDENTITY_CLIENT_ID"] + mode_keys:
        environment_key = (
            "AZURE_CLIENT_ID"
            if key == "DATA_DEPLOY_IDENTITY_CLIENT_ID"
            else key
        )
        values = re.findall(
            rf"(?<!\S){re.escape(environment_key)}="
            r"(\"[^\"]*\")(?=\s|$)",
            environment_section,
        )
        if len(values) != 1 or values[0] != f'"${key}"':
            errors.append(
                f"AuditRecord registration ACI must transfer `${key}` once as "
                f"`{environment_key}`."
            )
    if any(
        re.search(
            rf"(?<!\S){re.escape(key)}\s*=",
            environment_section + " " + secure_section,
        )
        for key in opposite_keys
    ) or any(
        commands.count(f': "${{{key}:?}}"') > 0
        for key in opposite_keys
    ):
        errors.append(
            f"AuditRecord {audit_mode} registration must not transfer opposite-mode "
            "Audit storage variables."
        )
    tag_values = re.findall(
        r"(?<!\S)hveRegisterRunId=(\"[^\"]*\")(?=\s|$)",
        create,
    )
    if (
        len(re.findall(r"(?<!\S)--tags(?=\s|=)", create)) != 1
        or tag_values != ['"$DATA_REGISTER_RUN_ID"']
    ):
        errors.append(
            "AuditRecord registration ACI must set exactly one "
            "`hveRegisterRunId=\"$DATA_REGISTER_RUN_ID\"` ownership tag."
        )
    expected_mode_environment = " ".join(
        f'{key}="${key}"' for key in mode_keys
    )
    expected_create = (
        'az container create --resource-group "$RESOURCE_GROUP" '
        '--name "$aci_name" --tags hveRegisterRunId="$DATA_REGISTER_RUN_ID" '
        '--image "$DATA_VERIFY_ACI_IMAGE" --subnet "$DATA_ACI_SUBNET_ID" '
        '--acr-identity "$DATA_DEPLOY_IDENTITY_ID" '
        '--assign-identity "$DATA_DEPLOY_IDENTITY_ID" '
        '--restart-policy Never --os-type Linux --cpu 1 --memory 1 '
        '--secure-environment-variables AUDIT_RECORD_JSON="$AUDIT_RECORD_JSON" '
        '--environment-variables '
        'AZURE_CLIENT_ID="$DATA_DEPLOY_IDENTITY_CLIENT_ID" '
        + expected_mode_environment
        + ' --command-line "$aci_command"'
    )
    if create != expected_create:
        errors.append(
            "AuditRecord registration must use the canonical az container create "
            "command with no extra option, tag, control operator, or transformation."
        )
    expected_lifecycle_tail = [
        "aci_created=1",
        "aci_wait_failed=0",
        'aci_logs="$(timeout 600 az container logs --resource-group '
        '"$RESOURCE_GROUP" --name "$aci_name" --follow)" || aci_wait_failed=1',
        'aci_exit_code="$(az container show --resource-group "$RESOURCE_GROUP" '
        '--name "$aci_name" --query '
        '"containers[0].instanceView.currentState.exitCode" --output tsv)"',
        'if [[ "$aci_wait_failed" != "0" || "$aci_exit_code" != "0" '
        '|| "$aci_logs" != "HVE_AUDIT_REGISTRATION_OK" ]]; then',
        "exit 1",
        "fi",
    ]
    if commands[create_indexes[0] + 1 :] != expected_lifecycle_tail:
        errors.append(
            "AuditRecord registration must wait up to 600 seconds for its ACI, "
            "require exitCode 0 and the canonical success marker, then allow "
            "ownership-safe cleanup."
        )
    return errors


def _validate_asdw_registration_audit_mode(
    text: str,
    audit_mode: str,
) -> List[str]:
    """Validate the mode-selected AuditRecord registration payload."""
    source, extraction_errors = _extract_asdw_registration_python_source(text)
    if extraction_errors:
        return extraction_errors
    errors = _validate_asdw_registration_mode_wiring(text, audit_mode)
    if audit_mode == _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST:
        return errors + _validate_asdw_sql_audit_registration(source)
    if audit_mode == _ASDW_AUDIT_MODE_ACL_DIRECT:
        return errors + _validate_asdw_acl_direct_audit_registration(source)
    return errors


def validate_asdw_data_registration_script(
    path: "Path | str",
    design_doc_path: "Path | str | None" = None,
    script_text: Optional[str] = None,
    design_doc_text: Optional[str] = None,
) -> List[str]:
    """Step.1.3 登録ACIのrun所有権・cleanup契約を静的に検査する。"""
    script_path = Path(path)
    if script_text is None:
        if not script_path.exists():
            return [f"data-registration-script.sh not found: {script_path}"]
        try:
            text = script_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return [f"data-registration-script.sh read error: {exc}"]
    else:
        text = script_text

    errors: List[str] = []
    if design_doc_path is not None:
        audit_mode, audit_mode_errors = _resolve_asdw_audit_storage_mode(
                design_doc_path,
                design_doc_text,
        )
        errors.extend(audit_mode_errors)
        if not audit_mode_errors and audit_mode is not None:
            audit_block, audit_block_errors = (
                _extract_asdw_audit_registration_block(text)
            )
            errors.extend(audit_block_errors)
            if not audit_block_errors:
                errors.extend(
                    _validate_asdw_audit_registration_block_structure(
                        audit_block
                    )
                )
                errors.extend(
                    _validate_asdw_outside_audit_registration_block(text)
                )
                text = audit_block
                errors.extend(
                    _validate_asdw_registration_audit_mode(text, audit_mode)
                )
    canonical_completion_tail = (
        "aci_created=1\n"
        "aci_wait_failed=0\n"
        'aci_logs="$(timeout 600 az container logs --resource-group '
        '"$RESOURCE_GROUP" --name "$aci_name" --follow)" || aci_wait_failed=1\n'
        'aci_exit_code="$(az container show --resource-group "$RESOURCE_GROUP" '
        '--name "$aci_name" --query '
        '"containers[0].instanceView.currentState.exitCode" --output tsv)"\n'
        'if [[ "$aci_wait_failed" != "0" || "$aci_exit_code" != "0" '
        '|| "$aci_logs" != "HVE_AUDIT_REGISTRATION_OK" ]]; then\n'
        "    exit 1\n"
        "fi\n"
    )
    generic_lifecycle_text = text.replace(canonical_completion_tail, "")
    protected_owner_names = r"(?:RESOURCE_GROUP|DATA_REGISTER_RUN_ID|aci_name)"
    if re.search(
        r"(?m)\bcleanup_aci\s*\\\s*$\s*(?:\r?\n)\s*\+?\s*(?:\(\))?\s*\{",
        generic_lifecycle_text,
    ):
        errors.append("registration ACI must not define `cleanup_aci` through line continuation.")
    if "<<" in generic_lifecycle_text:
        errors.append("registration ACI lifecycle must not appear in a here-document.")
    if "$'" in generic_lifecycle_text:
        errors.append("registration ACI lifecycle must not use ANSI-C quoted shell words.")
    if re.search(r"(?ms)\bcase\b.*?\baz\s+container\s+create\b", generic_lifecycle_text):
        errors.append("registration ACI lifecycle must not be placed in a case branch.")
    if re.search(r"\ba(?:\\|\$|['\"])z\b", generic_lifecycle_text):
        errors.append("registration ACI lifecycle must not reconstruct the Azure CLI command name.")
    if re.search(r"\b(?:a|de|tra)\$\{[^}]+\}(?:z|lete|p)\b", generic_lifecycle_text):
        errors.append("registration ACI lifecycle must not reconstruct shell command words with parameter expansion.")
    if re.search(
        r"\b(?:a|de|tra)(?:[\"']|\$\{[^}]+\})+(?:[\"']|\$\{[^}]+\})*(?:z|lete|p)\b",
        generic_lifecycle_text,
    ):
        errors.append("registration ACI lifecycle must not reconstruct shell command words with quoted parameter expansion.")
    if re.search(
        r"[A-Za-z][\"']?\$(?:\{[^}]+\}|[A-Za-z_][A-Za-z0-9_]*)(?![A-Za-z0-9_])|"
        r"\$(?:\{[^}]+\}|[A-Za-z_][A-Za-z0-9_]*)(?![A-Za-z0-9_])[\"']?[A-Za-z]",
        generic_lifecycle_text,
    ):
        errors.append("registration ACI lifecycle must not concatenate parameter expansion into shell command words.")
    if re.search(r"\b(?:bash|sh)(?:[\"']*|\$\{[^}]+\})*\s+-c\b", generic_lifecycle_text):
        errors.append("registration ACI lifecycle must not execute shell source through `bash -c` or `sh -c`.")
    continuation_lines = generic_lifecycle_text.splitlines()
    for index, raw_line in enumerate(continuation_lines):
        if not raw_line.rstrip().endswith("\\"):
            continue
        block_start = index
        while block_start > 0 and continuation_lines[block_start - 1].rstrip().endswith("\\"):
            block_start -= 1
        if not continuation_lines[block_start].lstrip().startswith("az container create "):
            errors.append(
                "registration ACI may use line continuation only for direct `az container create` options."
            )
            break
    if re.search(
        r"(?ms)\b(?:for|while|until|select)\b.*?"
        r"\baz\s+container\s+create\b.*?\bdone\b|"
        r"\(\s*.*?\baz\s+container\s+create\b.*?\)",
        generic_lifecycle_text,
    ):
        errors.append(
            "registration ACI lifecycle must use top-level direct statements, not loops or subshells."
        )
    commands = [
        _strip_shell_inline_comment(command)
        for command in _extract_shell_logical_commands(text)
    ]
    normalized_commands = [
        command.replace('"', "").replace("'", "").replace("\\", "")
        for command in _extract_shell_logical_commands(generic_lifecycle_text)
    ]
    if re.search(r"\b(?:declare|typeset)\s+-[A-Za-z]*n\b", generic_lifecycle_text):
        errors.append("registration ACI must not create namerefs for lifecycle values.")
    required_run_id = ': "${DATA_REGISTER_RUN_ID:?}"'
    if commands.count(required_run_id) != 1:
        errors.append("registration ACI must require `$DATA_REGISTER_RUN_ID` directly.")
    aci_name = 'aci_name="data-register-$DATA_REGISTER_RUN_ID"'
    if commands.count(aci_name) != 1:
        errors.append("registration ACI must assign `data-register-$DATA_REGISTER_RUN_ID` exactly once.")

    cleanup = re.search(
        r"(?ms)^\s*(?:function\s+)?cleanup_aci\s*(?:\(\))?\s*\{(?P<body>.*?)^\s*\}",
        text,
    )
    cleanup_definitions = re.findall(
        r"(?m)^\s*(?:function\s+)?cleanup_aci\s*(?:\(\))?\s*\{", text
    )
    cleanup_body = cleanup.group("body") if cleanup is not None else ""
    normalized_cleanup = "\n".join(
        _strip_shell_inline_comment(line).strip()
        for line in cleanup_body.splitlines()
        if _strip_shell_inline_comment(line).strip()
    )
    expected_cleanup = (
        r'if \[\[ "\$aci_created" == "1" \]\]; then\n'
        r'aci_owner="\$\(az container show --resource-group "\$RESOURCE_GROUP" '
        r'--name "\$aci_name" --query "tags\.hveRegisterRunId" --output tsv '
        r'2>/dev/null \|\| true\)"\n'
        r'if \[\[ "\$aci_owner" == "\$DATA_REGISTER_RUN_ID" \]\]; then\n'
        r'az container delete --resource-group "\$RESOURCE_GROUP" --name "\$aci_name" '
        r'--yes \|\| true\nfi\nfi'
    )
    if (
        len(cleanup_definitions) != 1
        or cleanup is None
        or re.fullmatch(expected_cleanup, normalized_cleanup) is None
    ):
        errors.append(
            "registration cleanup must only recheck `hveRegisterRunId` and delete "
            "the current Resource Group / aci_name."
        )
    if commands.count("trap cleanup_aci EXIT INT TERM") != 1:
        errors.append("registration ACI must register `cleanup_aci` for EXIT, INT, and TERM.")
    if any(
        re.search(r"\b(?:builtin\s+)?trap\b", command)
        and command != "trap cleanup_aci EXIT INT TERM"
        for command in normalized_commands
    ):
        errors.append("registration ACI must not remove or replace the `cleanup_aci` trap.")

    create_indexes = [
        index for index, command in enumerate(commands)
        if re.match(r"^az[ \t]+container[ \t]+create\b", command)
    ]
    if len(create_indexes) != 1:
        errors.append("registration ACI must execute exactly one direct `az container create`.")
        return errors
    create_index = create_indexes[0]
    create = commands[create_index]
    for option, variable in (("--resource-group", "RESOURCE_GROUP"), ("--name", "aci_name")):
        if not _command_option_references_variable(create, option, variable):
            errors.append(f"registration ACI `{option}` must reference `${variable}` directly.")
    if not re.search(
        rf"--tags[ \t]+hveRegisterRunId=[\"']?{_shell_variable_pattern('DATA_REGISTER_RUN_ID')}",
        create,
    ):
        errors.append("registration ACI create must tag `hveRegisterRunId=$DATA_REGISTER_RUN_ID`.")

    post_create = "\n".join(commands[create_index + 1:])
    if re.search(
        r"(?m)^\s*(?:export\s+|readonly\s+|declare\s+|typeset\s+)?"
        r"(?:RESOURCE_GROUP|DATA_REGISTER_RUN_ID|aci_name)(?:\[[^]\r\n]+\])?\s*(?:=|\+=)|"
        r"\b(?:printf\s+-v|read(?:\s+-[A-Za-z]+)?)\s+"
        r"(?:RESOURCE_GROUP|DATA_REGISTER_RUN_ID|aci_name)\b|"
        r"\bunset\s+(?:RESOURCE_GROUP|DATA_REGISTER_RUN_ID|aci_name)\b",
        post_create,
    ) or re.search(
        rf"\b(?:printf\s+-v|read|declare|typeset|unset|export|readonly)\b[^\n]*"
        rf"[\"']?{protected_owner_names}[\"']?",
        post_create,
    ) or re.search(
        rf"\bmapfile\b[^\n]*\b{protected_owner_names}\b",
        post_create,
    ) or re.search(
        r"\b(?:mapfile|printf\s+-v|read|declare|typeset|unset|export|readonly)\b"
        r"[^\n]*\$",
        post_create,
    ):
        errors.append(
            "registration ACI must not reassign Resource Group, run ID, or ACI name "
            "after create."
        )
    if re.search(rf"\bfor\s+{protected_owner_names}\b", post_create):
        errors.append(
            "registration ACI must not bind Resource Group, run ID, or ACI name as a loop variable."
        )

    guard = 'if az container show --resource-group "$RESOURCE_GROUP" --name "$aci_name" --only-show-errors; then'
    try:
        guard_index = commands.index(guard)
    except ValueError:
        guard_index = -1
    if not (
        0 <= guard_index < create_index
        and commands[guard_index + 1:guard_index + 3] == ["exit 1", "fi"]
    ):
        errors.append("registration ACI must fail closed on a pre-create name collision.")
    created_zero_indexes = [
        index for index, command in enumerate(commands) if command == "aci_created=0"
    ]
    created_one_indexes = [
        index for index, command in enumerate(commands) if command == "aci_created=1"
    ]
    if not (
        len(created_zero_indexes) == 1
        and len(created_one_indexes) == 1
        and created_zero_indexes[0] < create_index
        and created_one_indexes[0] == create_index + 1
    ):
        errors.append(
            "registration ACI must initialize `aci_created=0` before create and set "
            "`aci_created=1` as the immediately following logical statement."
        )

    if re.search(
        r"(?ms)\bif\b.*?\bthen\b.*?\baz\s+container\s+create\b.*?\bfi\b",
        generic_lifecycle_text,
    ):
        errors.append(
            "registration ACI lifecycle must not be placed in a conditional branch."
        )

    outside_cleanup = (
        generic_lifecycle_text
        if cleanup is None
        else generic_lifecycle_text[:cleanup.start()]
        + generic_lifecycle_text[cleanup.end():]
    )
    outside_commands = [
        _strip_shell_inline_comment(command)
        for command in _extract_shell_logical_commands(outside_cleanup)
    ]
    normalized_outside = "\n".join(
        command.replace('"', "").replace("'", "").replace("\\", "")
        for command in outside_commands
    )
    if re.search(r"\bdelete\b", normalized_outside, re.IGNORECASE):
        errors.append("registration ACI must not execute delete outside `cleanup_aci`.")
    if re.search(
        r"\b(?:eval|source)\b|(?m:^\s*command\b)|"
        r"[;&|]\s*command\b|\$\{!|`|[<>]\(",
        normalized_outside,
    ):
        errors.append("registration ACI lifecycle must not use dynamic command evaluation.")
    if re.search(
        r"\baz\s+(?:container|group)\s+(?:[^\s;|&]*\$|\$[^\s;|&]*)",
        outside_cleanup,
    ):
        errors.append(
            "registration ACI lifecycle must not reconstruct Azure command verbs with variables."
        )
    if re.search(r"\baz\s+[\"']?\$", normalized_outside):
        errors.append(
            "registration ACI lifecycle must not reconstruct Azure command groups with variables."
        )
    if re.search(
        r"(?m)^\s*(?:function\s+(?!cleanup_aci\b)[A-Za-z_][A-Za-z0-9_]*\s*(?:\(\))?|"
        r"(?!cleanup_aci\b)[A-Za-z_][A-Za-z0-9_]*\s*\(\))\s*\{",
        generic_lifecycle_text,
    ):
        errors.append("registration ACI lifecycle must not hide ownership commands in helper functions.")
    if any(
        re.search(r"(?:^|[;&|]\s*|\b(?:then|do)\s+)[\"']?\$", command)
        for command in normalized_commands
    ):
        errors.append("registration ACI lifecycle must not execute dynamically reconstructed commands.")
    return errors


# 表形式 1 行を抽出: `| AC-3 | 内容 | 状態 | 根拠 |` 形式。
# 状態欄に ❌ または NEEDS-VERIFICATION または ⏳ を含めばエラー。
_AC_TABLE_ROW = re.compile(
    r"^\s*\|\s*(?P<ac>AC-\d+|AC4B-\d+)\s*\|[^|]*\|(?P<status>[^|]*)\|"
)

_AGENT_PROVIDER_ROUTES = {
    "azure-ai-search-foundry-iq",
    "work-iq",
    "fabric-iq",
    "web-iq",
    "foundry-web-search",
    "remote-mcp",
}
_PROVIDER_PREFLIGHT_HEADING = "## Provider Pre-flight"
_PROVIDER_PREFLIGHT_HEADER = (
    "| Route | Status | Decision source | Permission | Data boundary | "
    "Smoke evidence | Inventory delta | Secret redaction | Evidence redaction |"
)
_PROVIDER_PREFLIGHT_SEPARATOR = "|---|---|---|---|---|---|---|---|---|"
_PROVIDER_PLACEHOLDERS = {"", "n/a", "tbd", "unknown", "不明", "要確認"}
_PROVIDER_INVENTORY_CATEGORIES = {
    "project-connection",
    "rbac-consent",
    "key-vault-reference",
    "package",
    "config-flag",
}
_PROVIDER_INVENTORY_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROVIDER_INVENTORY_GENERATOR = (
    "hve.artifact_validation.build_provider_inventory_snapshot/v1"
)
_PROVIDER_SECRET_VALUE = re.compile(
    r"(?:\bBearer\s+\S+|"
    r"(?:access[-_ ]?token|token|secret|api[-_ ]?key|password|credential|"
    r"authorization|cookie|client[-_ ]?secret)"
    r"\s*[:=]\s*(?!redacted\b|confirmed\b|none\b|n/a\b)\S+)",
    re.IGNORECASE,
)
_PROVIDER_SENSITIVE_SMOKE = re.compile(
    r"(?:\bquery|(?:document[_\s]+)?title|item[_\s]+id|"
    r"(?:response[_\s]+)?body)\s*[:=]",
    re.IGNORECASE,
)
_PROVIDER_URL = re.compile(r"https?://[^\s|<>]+", re.IGNORECASE)


def _is_meaningful_provider_evidence(value: str) -> bool:
    """Provider table cellが未記入・placeholderではないか判定する。"""
    normalized = value.strip().lower()
    if normalized in _PROVIDER_PLACEHOLDERS:
        return False
    return not ("<" in value and ">" in value)


def _strip_markdown_fenced_blocks(text: str) -> str:
    """Markdown fenced code blockを検証対象から除外する。"""
    visible: List[str] = []
    fence: Optional[tuple[str, int]] = None
    for line in text.splitlines():
        if fence is None:
            opening = _asdw_fence_opening(line)
            if opening is not None:
                fence = opening
                continue
        else:
            marker_char, minimum_length = fence
            closing = re.match(
                rf"^ {{0,3}}(?P<marker>{re.escape(marker_char)}"
                rf"{{{minimum_length},}})\s*$",
                line,
            )
            if closing:
                fence = None
            continue
        if fence is None:
            visible.append(line)
    return "\n".join(visible)


def build_provider_inventory_snapshot(
    raw_routes: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    """Raw identifierを保持せず、固定schemaのredacted inventoryを生成する。

    呼び出し側はAzure/設定inventoryをメモリ上で収集し、本関数へ渡す。各識別子は
    Unicode NFC + UTF-8へ正規化後にSHA-256化し、raw値は返却しない。
    """
    if set(raw_routes) != _AGENT_PROVIDER_ROUTES:
        raise ValueError("raw_routes must contain exactly the six fixed routes")

    routes: Dict[str, Dict[str, List[str]]] = {}
    for route in sorted(_AGENT_PROVIDER_ROUTES):
        categories = raw_routes[route]
        if set(categories) != _PROVIDER_INVENTORY_CATEGORIES:
            raise ValueError(
                f"route {route!r} must contain the five fixed categories"
            )
        routes[route] = {}
        for category in sorted(_PROVIDER_INVENTORY_CATEGORIES):
            values = categories[category]
            if isinstance(values, (str, bytes)):
                raise TypeError(f"route {route!r} category {category!r} must be iterable")
            hashed: List[str] = []
            for value in values:
                if not isinstance(value, str):
                    raise TypeError("provider inventory identifiers must be strings")
                normalized = unicodedata.normalize("NFC", value).encode("utf-8")
                hashed.append(hashlib.sha256(normalized).hexdigest())
            routes[route][category] = sorted(set(hashed))

    return {
        "schema_version": 1,
        "generator": _PROVIDER_INVENTORY_GENERATOR,
        "hash_algorithm": "sha256",
        "normalization": "unicode-nfc-utf8",
        "secret_values_included": False,
        "routes": routes,
    }


def _validate_provider_inventory_evidence(
    report_path: Path,
    route: str,
    expected_selection: str,
    inventory_cell: str,
) -> List[str]:
    """before/after inventoryのredacted JSON証跡を検証する。"""
    match = re.fullmatch(
        rf"{re.escape(expected_selection)};\s*evidence=(?P<path>[^\s;]+\.json)",
        inventory_cell,
        re.IGNORECASE,
    )
    if not match:
        return [
            "[Dev-Microservice-Azure-AgentDeploy] Provider Pre-flight route "
            f"{route!r} Inventory delta must be `{expected_selection}; "
            "evidence=<relative-json-path>`"
        ]

    relative = Path(match.group("path"))
    if relative.is_absolute() or ".." in relative.parts:
        return [
            "[Dev-Microservice-Azure-AgentDeploy] Provider inventory evidence path "
            f"must stay under the report directory: {relative}"
        ]
    evidence_path = (report_path.parent / relative).resolve()
    report_root = report_path.parent.resolve()
    try:
        evidence_path.relative_to(report_root)
    except ValueError:
        return [
            "[Dev-Microservice-Azure-AgentDeploy] Provider inventory evidence path "
            f"escapes the report directory: {relative}"
        ]
    if not evidence_path.is_file():
        return [
            "[Dev-Microservice-Azure-AgentDeploy] Provider inventory evidence not "
            f"found for route {route!r}: {relative}"
        ]

    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [
            "[Dev-Microservice-Azure-AgentDeploy] Provider inventory evidence is "
            f"unreadable for route {route!r}: {exc}"
        ]

    errors: List[str] = []
    expected_payload_keys = {
        "schema_version",
        "secret_values_included",
        "before_snapshot",
        "before_sha256",
        "after_snapshot",
        "after_sha256",
        "routes",
    }
    if not isinstance(payload, dict) or set(payload) != expected_payload_keys:
        errors.append("top-level fields must match the fixed evidence schema")
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if payload.get("secret_values_included") is not False:
        errors.append("secret_values_included must be false")

    snapshots: Dict[str, Any] = {}
    for phase in ("before", "after"):
        raw_snapshot_path = str(payload.get(f"{phase}_snapshot", ""))
        expected_digest = str(payload.get(f"{phase}_sha256", ""))
        snapshot_relative = Path(raw_snapshot_path)
        if (
            not raw_snapshot_path
            or snapshot_relative.is_absolute()
            or ".." in snapshot_relative.parts
        ):
            errors.append(f"{phase}_snapshot must be a relative path under the report directory")
            continue
        snapshot_path = (report_root / snapshot_relative).resolve()
        try:
            snapshot_path.relative_to(report_root)
        except ValueError:
            errors.append(f"{phase}_snapshot escapes the report directory")
            continue
        if not snapshot_path.is_file():
            errors.append(f"{phase}_snapshot not found: {snapshot_relative}")
            continue
        try:
            snapshot_bytes = snapshot_path.read_bytes()
            actual_digest = hashlib.sha256(snapshot_bytes).hexdigest()
            snapshot = json.loads(snapshot_bytes.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"{phase}_snapshot is unreadable: {exc}")
            continue
        if not _PROVIDER_INVENTORY_SHA256.fullmatch(expected_digest):
            errors.append(f"{phase}_sha256 must be a lowercase SHA-256 digest")
        elif actual_digest != expected_digest:
            errors.append(f"{phase}_sha256 does not match the snapshot file")
        if not isinstance(snapshot, dict) or set(snapshot) != {
            "schema_version", "generator", "hash_algorithm", "normalization",
            "secret_values_included", "routes"
        }:
            errors.append(f"{phase}_snapshot fields must match the fixed snapshot schema")
            continue
        if snapshot.get("schema_version") != 1:
            errors.append(f"{phase}_snapshot schema_version must be 1")
        if snapshot.get("generator") != _PROVIDER_INVENTORY_GENERATOR:
            errors.append(f"{phase}_snapshot must use the HVE inventory generator")
        if snapshot.get("hash_algorithm") != "sha256":
            errors.append(f"{phase}_snapshot hash_algorithm must be sha256")
        if snapshot.get("normalization") != "unicode-nfc-utf8":
            errors.append(f"{phase}_snapshot normalization must be unicode-nfc-utf8")
        if snapshot.get("secret_values_included") is not False:
            errors.append(f"{phase}_snapshot secret_values_included must be false")
        snapshot_routes = snapshot.get("routes")
        if not isinstance(snapshot_routes, dict) or set(snapshot_routes) != _AGENT_PROVIDER_ROUTES:
            errors.append(f"{phase}_snapshot must contain exactly the six fixed routes")
            continue
        valid_snapshot = True
        for snapshot_route, category_map in snapshot_routes.items():
            if not isinstance(category_map, dict) or set(category_map) != _PROVIDER_INVENTORY_CATEGORIES:
                errors.append(
                    f"{phase}_snapshot route {snapshot_route!r} must contain the five fixed categories"
                )
                valid_snapshot = False
                continue
            for category, identifiers in category_map.items():
                if (
                    not isinstance(identifiers, list)
                    or len(identifiers) != len(set(identifiers))
                    or any(
                        not isinstance(identifier, str)
                        or not _PROVIDER_INVENTORY_SHA256.fullmatch(identifier)
                        for identifier in identifiers
                    )
                ):
                    errors.append(
                        f"{phase}_snapshot route {snapshot_route!r} category {category!r} "
                        "must contain unique SHA-256 identifiers only"
                    )
                    valid_snapshot = False
        if valid_snapshot:
            snapshots[phase] = snapshot_routes

    routes_payload = payload.get("routes")
    if not isinstance(routes_payload, dict) or set(routes_payload) != _AGENT_PROVIDER_ROUTES:
        errors.append("evidence routes must contain exactly the six fixed routes")
        route_data = None
    else:
        route_data = routes_payload.get(route)

    if not isinstance(route_data, dict) or set(route_data) != {
        "selection", "changed_categories", "unexpected_categories"
    }:
        errors.append(f"route evidence {route!r} must match the fixed route schema")
    else:
        expected_status = "selected" if expected_selection == "expected-only" else "n/a"
        if route_data.get("selection") != expected_status:
            errors.append(f"selection must be {expected_status!r}")
        changed_value = route_data.get("changed_categories")
        unexpected = route_data.get("unexpected_categories")
        if not isinstance(changed_value, list) or not set(changed_value).issubset(_PROVIDER_INVENTORY_CATEGORIES):
            errors.append("changed_categories contains an unknown category")
            changed: List[str] = []
        else:
            changed = changed_value
        if not isinstance(unexpected, list) or unexpected:
            errors.append("unexpected_categories must be an empty list")
        if "before" in snapshots and "after" in snapshots:
            derived_changed = sorted(
                category
                for category in _PROVIDER_INVENTORY_CATEGORIES
                if snapshots["before"][route][category]
                != snapshots["after"][route][category]
            )
            if sorted(changed) != derived_changed:
                errors.append("changed_categories does not match the before/after snapshots")
            if expected_status == "n/a" and derived_changed:
                errors.append("N/A route must have zero inventory delta")

    return [
        "[Dev-Microservice-Azure-AgentDeploy] Provider inventory evidence "
        f"invalid for route {route!r}: {error}"
        for error in errors
    ]


def _validate_agent_provider_preflight(text: str, report_path: Path) -> List[str]:
    """AgentDeployの固定Provider Pre-flight表を検証する。

    Provider固有の値やAPI versionは解釈せず、選択状態、根拠、inventory差分、
    redaction証跡の決定的な最低契約だけを検査する。
    """
    visible_text = _strip_markdown_fenced_blocks(text)
    heading_matches = list(
        re.finditer(
            rf"^{re.escape(_PROVIDER_PREFLIGHT_HEADING)}\s*$",
            visible_text,
            re.MULTILINE,
        )
    )
    if not heading_matches:
        return [
            f"[Dev-Microservice-Azure-AgentDeploy] {_PROVIDER_PREFLIGHT_HEADING} "
            f"section not found in {report_path.name}"
        ]
    if len(heading_matches) != 1:
        return [
            f"[Dev-Microservice-Azure-AgentDeploy] {_PROVIDER_PREFLIGHT_HEADING} "
            f"must appear exactly once in {report_path.name}"
        ]

    section = visible_text[heading_matches[0].end():]
    next_heading = re.search(r"^##\s+", section, re.MULTILINE)
    if next_heading:
        section = section[: next_heading.start()]

    errors: List[str] = []
    section_lines = [line.strip() for line in section.splitlines()]
    if section_lines.count(_PROVIDER_PREFLIGHT_HEADER) != 1:
        errors.append(
            "[Dev-Microservice-Azure-AgentDeploy] Provider Pre-flight must contain "
            "the exact fixed 9-column header once"
        )
    if section_lines.count(_PROVIDER_PREFLIGHT_SEPARATOR) != 1:
        errors.append(
            "[Dev-Microservice-Azure-AgentDeploy] Provider Pre-flight must contain "
            "the exact fixed table separator once"
        )
    rows: Dict[str, List[str]] = {}
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or cells[0].lower() == "route":
            continue
        if all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            continue
        if len(cells) != 9:
            errors.append(
                "[Dev-Microservice-Azure-AgentDeploy] Provider Pre-flight row must "
                f"have 9 columns: {stripped}"
            )
            continue
        route = cells[0]
        if route not in _AGENT_PROVIDER_ROUTES:
            errors.append(
                "[Dev-Microservice-Azure-AgentDeploy] unknown Provider Pre-flight "
                f"route {route!r}"
            )
            continue
        if route in rows:
            errors.append(
                "[Dev-Microservice-Azure-AgentDeploy] duplicate Provider Pre-flight "
                f"route {route!r}"
            )
            continue
        rows[route] = cells

    for route in sorted(_AGENT_PROVIDER_ROUTES - rows.keys()):
        errors.append(
            "[Dev-Microservice-Azure-AgentDeploy] Provider Pre-flight route "
            f"{route!r} is missing"
        )

    for route, cells in rows.items():
        (
            _, status, decision_source, permission, data_boundary,
            smoke_evidence, inventory_delta, secret_redaction,
            evidence_redaction,
        ) = cells
        status_upper = status.upper()

        if not _is_meaningful_provider_evidence(decision_source):
            errors.append(
                "[Dev-Microservice-Azure-AgentDeploy] Provider Pre-flight route "
                f"{route!r} requires a concrete Decision source"
            )

        if secret_redaction.lower() != "confirmed":
            errors.append(
                "[Dev-Microservice-Azure-AgentDeploy] Provider Pre-flight route "
                f"{route!r} Secret redaction must be confirmed"
            )
        if evidence_redaction.lower() != "confirmed":
            errors.append(
                "[Dev-Microservice-Azure-AgentDeploy] Provider Pre-flight route "
                f"{route!r} Evidence redaction must be confirmed"
            )

        row_values = " | ".join(cells[1:])
        if _PROVIDER_SECRET_VALUE.search(row_values):
            errors.append(
                "[Dev-Microservice-Azure-AgentDeploy] Provider Pre-flight route "
                f"{route!r} contains secret-like material"
            )
        if _PROVIDER_SENSITIVE_SMOKE.search(smoke_evidence):
            errors.append(
                "[Dev-Microservice-Azure-AgentDeploy] selected Provider "
                f"Pre-flight route {route!r} Smoke evidence contains query/title/item/body data"
            )
        if _PROVIDER_URL.search(permission) or _PROVIDER_URL.search(data_boundary):
            errors.append(
                "[Dev-Microservice-Azure-AgentDeploy] Provider Pre-flight route "
                f"{route!r} Permission/Data boundary must not contain raw URLs"
            )
        if _PROVIDER_URL.search(row_values):
            errors.append(
                "[Dev-Microservice-Azure-AgentDeploy] Provider Pre-flight route "
                f"{route!r} must not contain raw URLs; record citation hashes instead"
            )

        if status_upper == "SELECTED-PASS":
            for label, value in (
                ("Permission", permission),
                ("Data boundary", data_boundary),
                ("Smoke evidence", smoke_evidence),
            ):
                if not _is_meaningful_provider_evidence(value):
                    errors.append(
                        "[Dev-Microservice-Azure-AgentDeploy] selected Provider "
                        f"Pre-flight route {route!r} requires {label} evidence"
                    )
            errors.extend(
                _validate_provider_inventory_evidence(
                    report_path, route, "expected-only", inventory_delta
                )
            )
        elif status_upper.startswith("N/A:"):
            reason = status.split(":", 1)[1].strip()
            if not _is_meaningful_provider_evidence(reason):
                errors.append(
                    "[Dev-Microservice-Azure-AgentDeploy] Provider Pre-flight route "
                    f"{route!r} N/A status requires a concrete reason"
                )
            errors.extend(
                _validate_provider_inventory_evidence(
                    report_path, route, "zero", inventory_delta
                )
            )
        else:
            errors.append(
                "[Dev-Microservice-Azure-AgentDeploy] Provider Pre-flight route "
                f"{route!r} must be SELECTED-PASS or reasoned N/A (status={status!r})"
            )

    return errors


def validate_deploy_ac_verification(
    report_path: "Path | str",
    agent_name: str,
    required_acs: "List[str] | None" = None,
) -> List[str]:
    """Deploy 系 Agent の ac-verification.md を検証する。

    Args:
        report_path: ac-verification.md のパス
        agent_name: Agent 名（custom_agent）
        required_acs: 実在系として GREEN を強制する AC-ID のリスト。
            registry の `StepDef.reality_gate_acs` から渡される。
            None または空リストの場合は、後方互換のため Agent 名ハードコード辞書
            `_DEPLOY_AGENT_REALITY_AC` にフォールバックする。

    Returns:
        エラー文字列のリスト。空 list なら問題なし。
        必須 AC が解決できない Agent（allowlist 外かつ宣言なし）は常に空 list
        （既存挙動を変えない）。
    """
    explicit_required_acs = bool(required_acs)
    if required_acs:
        resolved_acs: "List[str] | None" = required_acs
    else:
        resolved_acs = _DEPLOY_AGENT_REALITY_AC.get(agent_name)
    if not resolved_acs:
        return []
    required_acs = resolved_acs

    path = Path(report_path)
    if not path.exists():
        return [
            f"[{agent_name}] ac-verification.md not found: {path}"
        ]

    errors: List[str] = []
    seen: Dict[str, List[str]] = {}

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"[{agent_name}] ac-verification.md read error: {exc}"]

    visible_lines, visibility_error = _visible_asdw_design_lines(text)
    if visibility_error:
        detail = visibility_error.replace(
            "AuditRecord storage mode design document has ",
            "",
        )
        return [
            f"[{agent_name}] ac-verification.md visibility boundary is invalid: "
            f"{detail}"
        ]
    visible_text = "\n".join(visible_lines)

    for line in visible_lines:
        m = _AC_TABLE_ROW.match(line)
        if not m:
            continue
        ac = m.group("ac").strip()
        status = m.group("status").strip()
        seen.setdefault(ac, []).append(status)

    strict_green_acs = (
        {"AC-1", "AC-2", "AC-3"}
        if agent_name == "Dev-Microservice-Azure-DataDeploy"
        and explicit_required_acs
        else set()
    )

    for ac in required_acs:
        if ac not in seen:
            errors.append(
                f"[{agent_name}] AC {ac} not found as table row in {path.name} "
                f"(table 形式 `| {ac} | ... | 状態 | ... |` で記録すること)"
            )
            continue
        statuses = seen[ac]
        if ac in strict_green_acs:
            if len(statuses) != 1:
                errors.append(
                    f"[{agent_name}] AC {ac} must appear exactly once in "
                    f"{path.name} (found {len(statuses)} rows)."
                )
                continue
            status = statuses[0]
            if status != "✅":
                errors.append(
                    f"[{agent_name}] AC {ac} must be exactly `✅` "
                    f"(status={status!r})."
                )
            continue
        status = statuses[-1]
        # 非該当（N/A）は GREEN 扱い: 条件付き実在系 AC（例: AI/LLM 採用時のみの
        # AC-13）は、非該当時に状態欄へ `N/A` / `該当なし` を明記して記録する。
        # これにより「AC 行を丸ごと省く手抜き」（not found で fail）と
        # 「非該当を正しく N/A 記録」を区別できる。
        if "N/A" in status or "該当なし" in status:
            continue
        if "NEEDS-VERIFICATION" in status or "❌" in status or "⏳" in status:
            errors.append(
                f"[{agent_name}] AC {ac} is not GREEN (status={status!r}). "
                f"実 deploy 完了と verify GREEN ログを ac-verification.md に記録すること。"
            )

    if agent_name == "Dev-Microservice-Azure-AgentDeploy":
        errors.extend(_validate_agent_provider_preflight(visible_text, path))

    return errors


# ---------------------------------------------------------------------------
# TDD RED/GREEN test report gate
# ---------------------------------------------------------------------------

_TDD_REQUIRED_LABELS: List[str] = [
    "Schema-Version",
    "Workflow",
    "Step",
    "Agent",
    "Target-Key",
    "Phase",
    "Test-Code-Path",
    "Timestamp-UTC",
    "Evidence-Status",
    "TDD-Judgement",
    "Secret-Redaction",
    "Test-Files-Changed",
]

_TDD_REQUIRED_SECTIONS: List[str] = [
    "## Command",
    "## Expected Outcome",
    "## Actual Result",
    "## Evidence",
    "## Failure Analysis",
    "## Test Protection",
]


def _extract_markdown_label(text: str, label: str) -> str:
    """Extract a simple Markdown list label value: ``- Label: value``."""
    pattern = re.compile(rf"^\s*-\s*{re.escape(label)}\s*:\s*(?P<value>.*?)\s*$", re.MULTILINE)
    match = pattern.search(text)
    return match.group("value").strip() if match else ""


def validate_tdd_test_report(
    report_path: "Path | str",
    expected_phase: str,
    expected_workflow: Optional[str] = None,
    expected_target_key: Optional[str] = None,
    *,
    report_text: Optional[str] = None,
) -> List[str]:
    """Validate the minimal Markdown contract for a TDD RED/GREEN report.

    The validator intentionally checks only stable labels and section markers.
    It does not parse raw logs or infer test counts from runner-specific output.
    """
    path = Path(report_path)
    if report_text is None:
        if not path.exists():
            return [f"tdd-test-report.md not found: {path}"]

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return [f"tdd-test-report.md read error: {exc}"]
    else:
        text = report_text

    errors: List[str] = []
    try:
        from .split_fork import has_validation_marker
    except ImportError:  # pragma: no cover - フラット import 経路
        from split_fork import has_validation_marker  # type: ignore[no-redef]

    if not has_validation_marker(text, html_comment_only=True):
        errors.append("tdd-test-report.md missing <!-- validation-confirmed --> marker")

    for label in _TDD_REQUIRED_LABELS:
        if not _extract_markdown_label(text, label):
            errors.append(f"tdd-test-report.md missing required label: {label}")

    for section in _TDD_REQUIRED_SECTIONS:
        if section not in text:
            errors.append(f"tdd-test-report.md missing required section: {section}")

    expected = (expected_phase or "").strip().upper()
    actual_phase = _extract_markdown_label(text, "Phase").upper()
    if expected and actual_phase and actual_phase != expected:
        errors.append(
            f"tdd-test-report.md Phase mismatch: expected {expected}, actual {actual_phase}"
        )

    expected_workflow_norm = (expected_workflow or "").strip().lower()
    actual_workflow = _extract_markdown_label(text, "Workflow")
    if expected_workflow_norm and actual_workflow and actual_workflow.lower() != expected_workflow_norm:
        errors.append(
            f"tdd-test-report.md Workflow mismatch: expected {expected_workflow_norm}, actual {actual_workflow}"
        )

    expected_target = (expected_target_key or "").strip()
    actual_target = _extract_markdown_label(text, "Target-Key")
    if expected_target and actual_target and actual_target != expected_target:
        errors.append(
            f"tdd-test-report.md Target-Key mismatch: expected {expected_target}, actual {actual_target}"
        )

    secret_redaction = _extract_markdown_label(text, "Secret-Redaction").lower()
    if secret_redaction and secret_redaction != "confirmed":
        errors.append("tdd-test-report.md Secret-Redaction must be confirmed")

    if expected == "GREEN":
        judgement = _extract_markdown_label(text, "TDD-Judgement").upper()
        # PASS = テストが実際に GREEN。BLOCKED = テスト側/共有設定側の確定ブロッカーで
        # 実装だけでは GREEN 化不能なことを正直に記録した終端（Skill tdd-green-retry-strategy §4）。
        # FAIL（=この Step 自身の実装未達）は従来通りエラーとして扱う。
        if judgement and judgement not in ("PASS", "BLOCKED"):
            errors.append("tdd-test-report.md TDD-Judgement must be PASS or BLOCKED for GREEN")
        evidence_status = _extract_markdown_label(text, "Evidence-Status").upper()
        if evidence_status and evidence_status != "EXECUTED":
            errors.append("tdd-test-report.md Evidence-Status must be EXECUTED for GREEN")

    return errors


_ASDW_STEP12_EVIDENCE_LABELS = (
    "Artifact-Contract-Status",
    "Live-RED-Status",
    "Focused-Regression-Status",
)
_ASDW_STEP12_EVIDENCE_LOG_KEYS = {
    "Artifact-Contract-Status": "HVE-STEP12-ARTIFACT-CONTRACT-STATUS",
    "Live-RED-Status": "HVE-STEP12-LIVE-RED-STATUS",
    "Focused-Regression-Status": "HVE-STEP12-FOCUSED-REGRESSION-STATUS",
}
_ASDW_STEP12_EVIDENCE_ALLOWED = {
    "Artifact-Contract-Status": frozenset({"PASS", "FAIL"}),
    "Live-RED-Status": frozenset({"EXPECTED_FAIL", "NOT_RUN", "BLOCKED"}),
    "Focused-Regression-Status": frozenset({"PASS", "FAIL"}),
}


def _asdw_step12_report_label_values(text: str, label: str) -> List[str]:
    """Return every ``- Label: value`` list-item value for a Step 1.2 label."""
    pattern = re.compile(
        rf"^ {{0,3}}-[ \t]+{re.escape(label)}[ \t]*:[ \t]*"
        r"(?P<value>[^\r\n]*?)[ \t]*$",
        re.MULTILINE,
    )
    return [match.group("value").strip() for match in pattern.finditer(text)]


def _asdw_step12_log_line_values(text: str, key: str) -> List[str]:
    """Return every authoritative ``KEY: value`` machine-log line value."""
    pattern = re.compile(
        rf"^{re.escape(key)}[ \t]*:[ \t]*(?P<value>[^\r\n]*?)[ \t]*$",
        re.MULTILINE,
    )
    return [match.group("value").strip() for match in pattern.finditer(text)]


def validate_asdw_step12_evidence_report(
    report_text: str,
    machine_log_text: str,
) -> List[str]:
    """Machine-check the ASDW Step 1.2 three-state evidence contract.

    The three states are recorded separately so a static contract PASS is never
    presented as a live RED execution and a nonzero focused pytest is never
    folded into a single PASS. Each Agent-visible report label must match the
    HVE-owned authoritative machine-log line for that state; the machine log,
    produced by the Runner from tool events, is the source of truth.
    """
    errors: List[str] = []

    # The report is Agent-authored, so parse only its visible lines: a status
    # hidden inside a code fence or HTML comment must not satisfy the contract.
    # The machine log is HVE-owned and trusted, so it is parsed as-is.
    visible_lines, visibility_error = _visible_asdw_design_lines(report_text)
    if visibility_error:
        return [
            "ASDW Step 1.2 evidence report visibility boundary is invalid: "
            f"{visibility_error}"
        ]
    visible_report = "\n".join(visible_lines)

    report_values: Dict[str, str] = {}
    for label in _ASDW_STEP12_EVIDENCE_LABELS:
        found = _asdw_step12_report_label_values(visible_report, label)
        if len(found) != 1:
            errors.append(
                "ASDW Step 1.2 evidence report requires exactly one visible "
                f"{label} label (found {len(found)})."
            )
            continue
        value = found[0]
        if value not in _ASDW_STEP12_EVIDENCE_ALLOWED[label]:
            errors.append(
                f"ASDW Step 1.2 evidence report {label} must be one of "
                f"{sorted(_ASDW_STEP12_EVIDENCE_ALLOWED[label])} (got {value!r})."
            )
            continue
        report_values[label] = value

    log_values: Dict[str, str] = {}
    for label, key in _ASDW_STEP12_EVIDENCE_LOG_KEYS.items():
        found = _asdw_step12_log_line_values(machine_log_text, key)
        if len(found) != 1:
            errors.append(
                "ASDW Step 1.2 machine log requires exactly one authoritative "
                f"{key} line (found {len(found)})."
            )
            continue
        value = found[0]
        if value not in _ASDW_STEP12_EVIDENCE_ALLOWED[label]:
            errors.append(
                f"ASDW Step 1.2 machine log {key} must be one of "
                f"{sorted(_ASDW_STEP12_EVIDENCE_ALLOWED[label])} (got {value!r})."
            )
            continue
        log_values[label] = value

    for label in _ASDW_STEP12_EVIDENCE_LABELS:
        if label in report_values and label in log_values:
            if report_values[label] != log_values[label]:
                errors.append(
                    f"ASDW Step 1.2 evidence report {label} "
                    f"({report_values[label]}) must match the HVE-owned machine "
                    f"log ({log_values[label]}); the machine log is the source of "
                    "truth."
                )

    return errors


def build_asdw_step12_machine_log(
    *,
    bash_syntax_ok: bool,
    shellcheck_ok: bool,
    artifact_validator_errors: List[str],
    lf_bom_ok: bool,
    focused_pytest_exit_code: int,
    live_red_status: str = "NOT_RUN",
) -> str:
    """Derive the ASDW Step 1.2 three-state statuses and render the machine log.

    This is the HVE-owned side of the evidence contract: it turns the fixed
    local checks into the authoritative status lines that
    ``validate_asdw_step12_evidence_report`` treats as the source of truth. The
    derivation is pure and deterministic so the Runner can produce the same log
    from tool results without a generic command runner, Azure, or network.

    A nonzero focused pytest is never folded into a PASS, and the live RED state
    defaults to ``NOT_RUN`` because Step 1.2 does not execute the live Azure
    verifier; a caller that actually ran it passes ``EXPECTED_FAIL``/``BLOCKED``.
    """
    if live_red_status not in _ASDW_STEP12_EVIDENCE_ALLOWED["Live-RED-Status"]:
        raise ValueError(
            "ASDW Step 1.2 live RED status must be one of "
            f"{sorted(_ASDW_STEP12_EVIDENCE_ALLOWED['Live-RED-Status'])} "
            f"(got {live_red_status!r})."
        )

    artifact_pass = (
        bool(bash_syntax_ok)
        and bool(shellcheck_ok)
        and not artifact_validator_errors
        and bool(lf_bom_ok)
    )
    artifact_status = "PASS" if artifact_pass else "FAIL"
    focused_status = "PASS" if focused_pytest_exit_code == 0 else "FAIL"

    return (
        f"{_ASDW_STEP12_EVIDENCE_LOG_KEYS['Artifact-Contract-Status']}: "
        f"{artifact_status}\n"
        f"{_ASDW_STEP12_EVIDENCE_LOG_KEYS['Live-RED-Status']}: "
        f"{live_red_status}\n"
        f"{_ASDW_STEP12_EVIDENCE_LOG_KEYS['Focused-Regression-Status']}: "
        f"{focused_status}\n"
    )


def validate_asdw_ui_red_tests_no_unresolved_contracts(test_path: "Path | str") -> List[str]:
    """Reject executable unresolved TBD contracts in ASDW-WEB UI RED tests.

    This guard is intentionally narrow: it scans generated JavaScript UI RED
    tests and ignores comment-only lines. Unresolved contracts should be
    recorded as blockers, not as GREEN-required executable assertions.
    """
    root = Path(test_path)
    if not root.exists():
        return []

    files = [root] if root.is_file() else sorted(root.rglob("*.js"))
    errors: List[str] = []
    for file_path in files:
        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            errors.append(f"UI RED test read error: {file_path}: {exc}")
            continue
        for line_no, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("//", "/*", "*")):
                continue
            code = line.split("//", 1)[0]
            if "TBD（要確認" in code:
                errors.append(
                    f"UI RED test contains executable unresolved TBD contract: "
                    f"{file_path}:{line_no}"
                )
    return errors


# ---------------------------------------------------------------------------
# AI Agent capability artifact gate (AAG Step 3 / AAGD Step 2.3)
# ---------------------------------------------------------------------------

_AI_AGENT_CONTRACT_HEADINGS = {
    "AG-CAP-01": "Goal Contract",
    "AG-CAP-02": "Runtime Goal Loop",
    "AG-CAP-03": "Knowledge & Structured Data Routing",
    "AG-CAP-04": "REST CRUD Matrix",
    "AG-CAP-05": "MCP Integration Plan",
    "AG-CAP-06": "Skill Packaging Decision",
    "AG-CAP-07": "Agent Identity & Authorization",
    "AG-CAP-08": "Observability Contract",
    "AG-CAP-09": "Distribution & Packaging",
    "AG-CAP-10": "Evaluation & Route Right-sizing",
}
# Skill `agentic-retrieval-contract` の AR-CAP-01〜05。
# AG-CAP-03 で Foundry IQ / Azure AI Search Agentic Retrieval を選んだ場合だけ必須になる。
_AGENTIC_RETRIEVAL_CONTRACT_HEADINGS = {
    "AR-CAP-01": "Knowledge Base Contract",
    "AR-CAP-02": "Knowledge Source Matrix",
    "AR-CAP-03": "Retrieval Budget",
    "AR-CAP-04": "Evidence & Observability",
    "AR-CAP-05": "MCP Exposure",
}
_AGENTIC_RETRIEVAL_EFFORTS = {"minimal", "low", "medium"}
_AGENTIC_RETRIEVAL_OUTPUT_MODES = {"extractivedata", "answersynthesis"}
# Learn: minimal は KB あたり最大 10 Knowledge Source。low / medium も tier 依存で同値のため
# 設計時の上限として 10 を用い、実行時に再確認する運用とする。
_AGENTIC_RETRIEVAL_MAX_KNOWLEDGE_SOURCES = 10
# FR-WF-AAG-04: 1 件の Knowledge Source だけの Knowledge Base は
# クラシックな単一クエリ検索と等価で、横断検索の前提を満たさない。
_AGENTIC_RETRIEVAL_MIN_KNOWLEDGE_SOURCES = 2
_AGENTIC_RETRIEVAL_ALLOWED_MCP_TOOL = "knowledge_base_retrieve"
# FR-WF-AAG-03: 生成 AI Agent の Agentic Retrieval 方針。3 値以外は推測で丸めない。
_AGENTIC_RETRIEVAL_POLICIES = ("auto", "yes", "no")
# Agent Skills 仕様（<https://agentskills.io/specification>、2026-08-16 確認）の frontmatter 長さ制約。
_AGENT_SKILL_MAX_NAME_LENGTH = 64
_AGENT_SKILL_MAX_DESCRIPTION_LENGTH = 1024
# Agent Plugins Specification 1.0.0（<https://github.com/agentplugins/agent-plugins-spec>、2026-08-16 確認）。
_AGENT_PLUGIN_MANIFEST_FILE = "plugin.json"
_AGENT_PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
# 仕様 §5.2 が許容する top-level フィールド（closed schema）。
_AGENT_PLUGIN_ALLOWED_FIELDS = frozenset(
    {
        "$schema",
        "name",
        "version",
        "description",
        "author",
        "homepage",
        "repository",
        "license",
        "keywords",
        "extensions",
    }
)
# 仕様 §5.5 の name 制約（plugin.schema.json の pattern と同じ）。
_AGENT_PLUGIN_NAME = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
_AGENT_PLUGIN_MAX_NAME_LENGTH = 64
# 仕様 §7.2 の MCP server 設定。plugin root 固定で、`plugin.json` へインラインできない。
_AGENT_PLUGIN_MCP_FILE = "mcp.json"
_AGENT_PLUGIN_MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
_AGENT_PLUGIN_MCP_TRANSPORTS = frozenset({"stdio", "streamable-http", "sse"})
_AGENT_PLUGIN_MCP_SERVER_FIELDS = frozenset(
    {"type", "command", "args", "env", "url", "headers"}
)
# 仕様 §7.2.1: `${PLUGIN_ROOT}` / `${PLUGIN_DATA}` は client が解決する予約変数。
_AGENT_PLUGIN_RESERVED_VARS = frozenset({"PLUGIN_ROOT", "PLUGIN_DATA"})
# `headers` / `env` は可視のパッケージデータであり、資格情報を書けない（仕様 §7.2.1 / §9.2）。
_AGENT_PLUGIN_CREDENTIAL_KEY = re.compile(
    r"(?:authorization|api[_-]?key|secret|token|password|credential|connection[_-]?string)",
    re.IGNORECASE,
)
# Skill `foundry-toolbox-contract` の TB-CAP-01〜05。
# Tool 総数が閾値を超えた場合だけ必須になる。
_TOOLBOX_CONTRACT_HEADINGS = {
    "TB-CAP-01": "Tool Inventory",
    "TB-CAP-02": "Toolbox Decision",
    "TB-CAP-03": "Pinning Policy",
    "TB-CAP-04": "Search Metadata",
    "TB-CAP-05": "Discovery Budget",
}
# Learn / Command Line ブログが一致して示す閾値。16 以上で tool search を既定とする。
_TOOLBOX_TOOL_COUNT_THRESHOLD = 15
# FR-WF-AAG-01: 生成 Agent の Tool Search 方針。3値以外は推測で丸めない。
_TOOL_SEARCH_POLICIES = ("auto", "yes", "no")
# Learn: tool_search の limit は既定 5・最大 10。
_TOOLBOX_MAX_SEARCH_LIMIT = 10
_TOOLBOX_TOPOLOGIES = {"direct-kb", "via-toolbox"}
_AGENTIC_RETRIEVAL_UNBOUNDED = re.compile(
    r"\b(?:unlimited|unbounded|infinite|no\s+limit)\b|無制限|上限なし",
    re.IGNORECASE,
)

_AI_AGENT_PLACEHOLDERS = {
    "",
    "-",
    "n/a",
    "na",
    "none",
    "not applicable",
    "null",
    "tbd",
    "unknown",
    "不明",
    "要確認",
    "該当なし",
    "不要",
}
_AI_AGENT_EVALUATOR_TYPES = {
    "schema",
    "rule",
    "tool-result",
    "test",
    "human-approval",
}
_AI_AGENT_REQUEST_CLASSES = {
    "public-web",
    "microsoft-365",
    "fabric-business-data",
    "enterprise-unstructured",
    "structured-numeric",
    "operational-api-read",
}
_AI_AGENT_DESIGN_STATUSES = {
    "supported",
    "preview",
    "limited-access",
    "unavailable",
    "unknown",
}
_AI_AGENT_REST_OPERATIONS = {"create", "read", "update", "delete"}
_AI_AGENT_REST_METHODS = {"POST", "GET", "PUT", "PATCH", "DELETE"}
_AI_AGENT_STOP_STATES = {
    "DONE",
    "PARTIAL",
    "BLOCKED",
    "HANDOFF",
    "MAX_ITERATIONS",
    "DEADLINE",
    "POLICY_STOP",
    "USER_CANCELLED",
    "DEGRADATION",
}
_AI_AGENT_TEXT_SUFFIXES = {
    ".cs",
    ".env",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
_AI_AGENT_IGNORED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "bin",
    "node_modules",
    "obj",
}
_AI_AGENT_SECRET_ASSIGNMENT = re.compile(
    r"(?ix)"
    r"[\"']?(?P<label>api[-_]?key|access[-_]?token|client[-_]?secret|"
    r"connection[-_]?string|password|secret|token)[\"']?\s*[:=]\s*"
    r"(?P<value>[\"'][^\"'\r\n]*[\"'])"
)
_AI_AGENT_BEARER = re.compile(r"\bBearer\s+(?P<value>[^\s|]+)", re.IGNORECASE)
_AI_AGENT_KNOWN_SECRET = re.compile(
    r"(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\bAccountKey=[A-Za-z0-9+/=]{16,}|"
    r"\bgh[pousr]_[A-Za-z0-9]{20,}|"
    r"\bsk-[A-Za-z0-9_-]{20,}|"
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"
)


def _normalize_ai_agent_label(value: str) -> str:
    """Markdown table/field labelsを比較用ASCII keyへ正規化する。"""
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _strip_ai_agent_markdown_code(text: str) -> str:
    """fenced/4-space code block内の見出し・table spoofを除外する。"""
    visible = _strip_markdown_fenced_blocks(text)
    return "\n".join(
        "" if line.startswith(("    ", "\t")) else line
        for line in visible.splitlines()
    )


def _ai_agent_table_cells(line: str) -> List[str]:
    """単純なMarkdown table rowをcellへ分割する。"""
    stripped = line.strip()
    if not stripped.startswith("|"):
        return []
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def _parse_ai_agent_tables(section: str) -> List[List[Dict[str, str]]]:
    """Markdown table群を正規化header付きrow mappingとして返す。"""
    lines = section.splitlines()
    tables: List[List[Dict[str, str]]] = []
    index = 0
    while index + 1 < len(lines):
        headers = _ai_agent_table_cells(lines[index])
        separator = _ai_agent_table_cells(lines[index + 1])
        if (
            len(headers) >= 2
            and len(headers) == len(separator)
            and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in separator)
        ):
            normalized_headers = [_normalize_ai_agent_label(cell) for cell in headers]
            rows: List[Dict[str, str]] = []
            index += 2
            while index < len(lines):
                cells = _ai_agent_table_cells(lines[index])
                if not cells:
                    break
                if len(cells) == len(headers):
                    rows.append(dict(zip(normalized_headers, cells)))
                index += 1
            tables.append(rows)
            continue
        index += 1
    return tables


def _find_ai_agent_table(
    section: str,
    required_headers: Iterable[str],
) -> Optional[List[Dict[str, str]]]:
    required = {_normalize_ai_agent_label(header) for header in required_headers}
    for rows in _parse_ai_agent_tables(section):
        if rows and required.issubset(rows[0]):
            return rows
    return None


def _ai_agent_field(section: str, *labels: str) -> str:
    """bullet/plain/tableの固定labelから最初の値を抽出する。"""
    normalized_labels = {_normalize_ai_agent_label(label) for label in labels}
    for line in section.splitlines():
        cells = _ai_agent_table_cells(line)
        if len(cells) >= 2 and _normalize_ai_agent_label(cells[0]) in normalized_labels:
            return cells[1].strip()
        stripped = line.strip()
        stripped = re.sub(r"^[-*]\s+", "", stripped)
        stripped = stripped.replace("**", "")
        match = re.match(r"^(?P<label>[^:：]+)\s*[:：]\s*(?P<value>.*)$", stripped)
        if match and _normalize_ai_agent_label(match.group("label")) in normalized_labels:
            return match.group("value").strip()
    return ""


def _is_meaningful_ai_agent_value(value: str) -> bool:
    normalized = value.strip().strip("`*_ ").casefold()
    if normalized in _AI_AGENT_PLACEHOLDERS:
        return False
    if normalized.startswith(("tbd", "要確認", "<")):
        return False
    return len(normalized) >= 3


def _has_reasoned_none(value: str) -> bool:
    normalized = value.strip().casefold()
    if not normalized.startswith(("none", "n/a", "該当なし")):
        return _is_meaningful_ai_agent_value(value)
    _, separator, reason = value.partition(":")
    if not separator:
        _, separator, reason = value.partition("：")
    return bool(separator and _is_meaningful_ai_agent_value(reason))


def _extract_ai_agent_contract_section(
    visible_text: str,
    contract_id: str,
    fixed_heading: str,
) -> tuple[str, List[str]]:
    """固定見出しとContract IDが一致する単一sectionを抽出する。"""
    heading_re = re.compile(r"^(?P<marks>#{1,6})\s+(?P<title>.+?)\s*$", re.MULTILINE)
    candidates: List[tuple[re.Match[str], int]] = []
    for match in heading_re.finditer(visible_text):
        title = re.sub(
            r"^\d+(?:\.\d+)*[.)]?\s*",
            "",
            match.group("title").strip(),
        )
        if title.casefold().startswith(fixed_heading.casefold()) and contract_id in title:
            candidates.append((match, len(match.group("marks"))))
    if not candidates:
        return "", [f"[{contract_id}] {fixed_heading} section not found"]
    if len(candidates) != 1:
        return "", [f"[{contract_id}] {fixed_heading} section must appear exactly once"]

    match, level = candidates[0]
    end = len(visible_text)
    for next_match in heading_re.finditer(visible_text, match.end()):
        if len(next_match.group("marks")) <= level:
            end = next_match.start()
            break
    return visible_text[match.end():end].strip(), []


def _reasoned_ai_agent_na(section: str, contract_id: str) -> tuple[bool, List[str]]:
    """Contract全体のN/A判定と理由・根拠・再判定条件を検証する。"""
    status = _ai_agent_field(section, "Status", "Decision")
    is_na = status.strip().casefold() in {"n/a", "na", "not-applicable", "該当なし"}
    if not is_na:
        return False, []

    errors: List[str] = []
    reason = _ai_agent_field(section, "Reason", "N/A reason")
    source = _ai_agent_field(section, "Decision source", "Justification")
    recheck = _ai_agent_field(
        section,
        "Recheck condition",
        "Reconsider condition",
        "Re-evaluation condition",
    )
    if not _is_meaningful_ai_agent_value(reason):
        errors.append(f"[{contract_id}] reasoned N/A requires a concrete Reason")
    if not _is_meaningful_ai_agent_value(source) or not re.search(
        r"(?:^|\s)(?:docs|users-guide|knowledge|\.github)/[^\s]+|"
        r"user decision\s*[:：]\s*\S+|"
        r"(?:requirement|issue)\s*(?:#|[:：])\s*\S+|"
        r"(?:要件|設計)\s*[:：]\s*\S+",
        source,
        re.IGNORECASE,
    ):
        errors.append(f"[{contract_id}] reasoned N/A requires a Decision source")
    if not _is_meaningful_ai_agent_value(recheck):
        errors.append(f"[{contract_id}] reasoned N/A requires a Recheck condition")
    return True, errors


def _safe_ai_agent_secret_value(value: str) -> bool:
    value = value.strip().strip("\"'`,; ")
    normalized = value.casefold()
    if normalized in {"", "redacted", "[redacted]", "***", "none", "n/a", "null"}:
        return True
    if (
        (value.startswith("${") and value.endswith("}"))
        or (value.startswith("%") and value.endswith("%"))
        or (value.startswith("<") and value.endswith(">"))
        or (value.startswith("{") and "}" in value)
        or re.fullmatch(r"[A-Z][A-Z0-9_]{3,}", value)
    ):
        return True
    return any(
        marker in normalized
        for marker in (
            "getenv(",
            "os.environ",
            "environment.getenvironmentvariable",
            "configuration[",
            "secretclient",
            "key vault",
        )
    )


def _ai_agent_secret_errors(path: Path, text: str) -> List[str]:
    """secret値を出力せず、高確度なhard-codeだけを報告する。"""
    errors: List[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if _AI_AGENT_KNOWN_SECRET.search(line):
            errors.append(f"secret-like material found in {path}:{line_number}")
            continue
        bearer = _AI_AGENT_BEARER.search(line)
        if bearer and not _safe_ai_agent_secret_value(bearer.group("value")):
            errors.append(f"secret-like Bearer value found in {path}:{line_number}")
            continue
        assignment = _AI_AGENT_SECRET_ASSIGNMENT.search(line)
        if assignment and not _safe_ai_agent_secret_value(assignment.group("value")):
            errors.append(
                f"secret-like {assignment.group('label')} value found in "
                f"{path}:{line_number}"
            )
    return errors


def _validate_ai_agent_goal(section: str, metadata: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    contract_id = "AG-CAP-01"
    for label in ("Mission", "Failure conditions", "Partial success", "Handoff"):
        if not _is_meaningful_ai_agent_value(_ai_agent_field(section, label)):
            errors.append(f"[{contract_id}] missing meaningful {label}")
    mutation_intent = _ai_agent_field(section, "Mutation Intent").strip().casefold()
    if mutation_intent not in {"required", "none"}:
        errors.append(f"[{contract_id}] Mutation Intent must be required or none")
    metadata["mutation_intent"] = mutation_intent

    required_headers = (
        "Criterion ID",
        "Description",
        "Required for Done",
        "Evaluator type",
        "Evaluation procedure",
        "Evidence required",
        "Failure action",
        "Contract source",
    )
    rows = _find_ai_agent_table(section, required_headers)
    if not rows:
        errors.append(f"[{contract_id}] criterion table is missing or empty")
        return errors

    seen: set[str] = set()
    criterion_ids: List[str] = []
    for row in rows:
        criterion_id = row[_normalize_ai_agent_label("Criterion ID")]
        if not _is_meaningful_ai_agent_value(criterion_id):
            errors.append(f"[{contract_id}] Criterion ID must be concrete")
        elif criterion_id in seen:
            errors.append(f"[{contract_id}] duplicate Criterion ID {criterion_id!r}")
        else:
            seen.add(criterion_id)
            criterion_ids.append(criterion_id)
        required = row[_normalize_ai_agent_label("Required for Done")].casefold()
        if required not in {"yes", "no"}:
            errors.append(f"[{contract_id}] Required for Done must be yes or no")
        evaluator = row[_normalize_ai_agent_label("Evaluator type")].casefold()
        if evaluator not in _AI_AGENT_EVALUATOR_TYPES:
            errors.append(f"[{contract_id}] unsupported Evaluator type {evaluator!r}")
        for label in (
            "Description",
            "Evaluation procedure",
            "Evidence required",
            "Failure action",
            "Contract source",
        ):
            if not _is_meaningful_ai_agent_value(row[_normalize_ai_agent_label(label)]):
                errors.append(f"[{contract_id}] criterion {criterion_id!r} missing {label}")
    metadata["criterion_ids"] = criterion_ids
    return errors


def _validate_ai_agent_runtime(section: str, metadata: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    contract_id = "AG-CAP-02"
    max_iterations = _ai_agent_field(section, "Max iterations")
    match = re.search(r"\b([1-9]\d*)\b", max_iterations)
    if not match:
        errors.append(f"[{contract_id}] Max iterations must be a positive finite integer")
    else:
        metadata["max_iterations"] = int(match.group(1))
    for label in (
        "Operation deadline",
        "Tool budget",
        "Cost budget",
        "Action fingerprint",
        "Evidence",
    ):
        value = _ai_agent_field(section, label)
        if not _is_meaningful_ai_agent_value(value) or re.search(
            r"\b(?:unlimited|infinite|無制限)\b",
            value,
            re.IGNORECASE,
        ):
            errors.append(f"[{contract_id}] missing finite {label}")
    upper = section.upper()
    for state in ("PLAN", "ACT", "OBSERVE", "EVALUATE", "REPLAN"):
        if not re.search(rf"\b{state}\b", upper):
            errors.append(f"[{contract_id}] runtime state {state} is missing")
    for state in sorted(_AI_AGENT_STOP_STATES):
        if not re.search(rf"\b{state}\b", upper):
            errors.append(f"[{contract_id}] stop condition {state} is missing")
    return errors


def _validate_ai_agent_routing(section: str, metadata: Dict[str, Any]) -> List[str]:
    contract_id = "AG-CAP-03"
    is_na, errors = _reasoned_ai_agent_na(section, contract_id)
    metadata["routing_na"] = is_na
    metadata["routes"] = []
    if is_na:
        return errors

    required_headers = (
        "Request class",
        "Data source",
        "Required for Done",
        "Preferred route",
        "Design status",
        "Checked at",
        "Runtime probe",
        "Fallback route",
        "Blocked condition",
        "Permission boundary",
        "Citation requirement",
        "Decision source",
    )
    rows = _find_ai_agent_table(section, required_headers)
    if not rows:
        return [f"[{contract_id}] routing table is missing or empty"]

    for row in rows:
        request_class = row[_normalize_ai_agent_label("Request class")].casefold()
        if request_class not in _AI_AGENT_REQUEST_CLASSES:
            errors.append(f"[{contract_id}] unsupported Request class {request_class!r}")
        required = row[_normalize_ai_agent_label("Required for Done")].casefold()
        if required not in {"yes", "no"}:
            errors.append(f"[{contract_id}] Required for Done must be yes or no")
        status = row[_normalize_ai_agent_label("Design status")].casefold()
        if status not in _AI_AGENT_DESIGN_STATUSES:
            errors.append(f"[{contract_id}] invalid Design status {status!r}")
        checked_at = row[_normalize_ai_agent_label("Checked at")]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", checked_at):
            errors.append(f"[{contract_id}] Checked at must use YYYY-MM-DD")
        for label in (
            "Data source",
            "Preferred route",
            "Runtime probe",
            "Blocked condition",
            "Permission boundary",
            "Citation requirement",
            "Decision source",
        ):
            if not _is_meaningful_ai_agent_value(row[_normalize_ai_agent_label(label)]):
                errors.append(f"[{contract_id}] route {request_class!r} missing {label}")
        fallback = row[_normalize_ai_agent_label("Fallback route")]
        if not _has_reasoned_none(fallback):
            errors.append(
                f"[{contract_id}] route {request_class!r} requires a concrete or reasoned Fallback route"
            )
    metadata["routes"] = rows
    return errors


def _validate_ai_agent_crud(section: str, metadata: Dict[str, Any]) -> List[str]:
    contract_id = "AG-CAP-04"
    is_na, errors = _reasoned_ai_agent_na(section, contract_id)
    metadata["crud_na"] = is_na
    metadata["crud_rows"] = []
    if is_na:
        return errors

    required_headers = (
        "Tool ID",
        "Operation",
        "Required",
        "REST method",
        "REST path",
        "Request schema",
        "Response schema",
        "Authentication",
        "Authorization",
        "Approval",
        "Idempotency",
        "Retry",
        "Error class",
        "Audit evidence",
        "Contract source",
    )
    rows = _find_ai_agent_table(section, required_headers)
    if not rows:
        return [f"[{contract_id}] REST CRUD table is missing or empty"]

    operations: set[str] = set()
    active_rows: List[Dict[str, str]] = []
    seen_tools: set[str] = set()
    for row in rows:
        operation = row[_normalize_ai_agent_label("Operation")].casefold()
        operations.add(operation)
        if operation not in _AI_AGENT_REST_OPERATIONS:
            errors.append(f"[{contract_id}] unsupported Operation {operation!r}")
        tool_id = row[_normalize_ai_agent_label("Tool ID")]
        if not _is_meaningful_ai_agent_value(tool_id) or tool_id in seen_tools:
            errors.append(f"[{contract_id}] Tool ID must be concrete and unique ({tool_id!r})")
        seen_tools.add(tool_id)
        required = row[_normalize_ai_agent_label("Required")].casefold()
        if required not in {"yes", "no"}:
            errors.append(f"[{contract_id}] Required must be yes or no for {tool_id!r}")
            continue
        if required == "no":
            if not _has_reasoned_none(row[_normalize_ai_agent_label("REST method")]):
                errors.append(f"[{contract_id}] non-required Tool {tool_id!r} needs a reason")
            continue

        active_rows.append(row)
        method = row[_normalize_ai_agent_label("REST method")].upper()
        path = row[_normalize_ai_agent_label("REST path")]
        if method not in _AI_AGENT_REST_METHODS:
            errors.append(f"[{contract_id}] invalid REST method for {tool_id!r}")
        if not path.startswith("/") or any(part == ".." for part in Path(path).parts):
            errors.append(f"[{contract_id}] REST path must be an absolute API path for {tool_id!r}")
        for label in (
            "Request schema",
            "Response schema",
            "Authentication",
            "Authorization",
            "Approval",
            "Idempotency",
            "Retry",
            "Error class",
            "Audit evidence",
            "Contract source",
        ):
            if not _is_meaningful_ai_agent_value(row[_normalize_ai_agent_label(label)]):
                errors.append(f"[{contract_id}] Tool {tool_id!r} missing {label}")
        if operation in {"create", "update", "delete"}:
            approval = row[_normalize_ai_agent_label("Approval")].casefold()
            if "required" not in approval and "hitl" not in approval:
                errors.append(f"[{contract_id}] mutation Tool {tool_id!r} requires HITL approval")
            if method == "GET":
                errors.append(f"[{contract_id}] mutation Tool {tool_id!r} cannot use GET")
    missing = sorted(_AI_AGENT_REST_OPERATIONS - operations)
    if missing:
        errors.append(f"[{contract_id}] missing operation decisions: {', '.join(missing)}")
    metadata["crud_rows"] = active_rows
    return errors


def _validate_ai_agent_mcp(section: str, metadata: Dict[str, Any]) -> List[str]:
    contract_id = "AG-CAP-05"
    is_na, errors = _reasoned_ai_agent_na(section, contract_id)
    metadata["mcp_na"] = is_na
    metadata["mcp_rows"] = []
    if is_na:
        return errors

    required_headers = (
        "Server label",
        "Purpose",
        "Transport / endpoint",
        "Authentication",
        "Tool allowlist",
        "Approval",
        "Timeout / retry",
        "Input trust",
        "Failure behavior",
        "Evidence",
        "Remote adapter owner",
        "Decision source",
    )
    rows = _find_ai_agent_table(section, required_headers)
    if not rows:
        return [f"[{contract_id}] MCP plan table is missing or empty"]
    for row in rows:
        label = row[_normalize_ai_agent_label("Server label")]
        for field in required_headers:
            if not _is_meaningful_ai_agent_value(row[_normalize_ai_agent_label(field)]):
                errors.append(f"[{contract_id}] MCP server {label!r} missing {field}")
        allowlist = row[_normalize_ai_agent_label("Tool allowlist")]
        if re.search(r"(?:^|[,\s])\*(?:$|[,\s])", allowlist):
            errors.append(f"[{contract_id}] MCP server {label!r} uses wildcard Tool allowlist")
    metadata["mcp_rows"] = rows
    return errors


def _parse_ai_agent_resources(value: str) -> List[str]:
    return sorted(
        set(
            re.findall(
                r"(?:scripts|references|assets)/[A-Za-z0-9_.\-/]+",
                value.replace("`", ""),
            )
        )
    )


def _validate_ai_agent_skill(
    section: str,
    metadata: Dict[str, Any],
    agent_key: str,
) -> List[str]:
    contract_id = "AG-CAP-06"
    errors: List[str] = []
    decision = _ai_agent_field(section, "Decision").strip().casefold()
    if decision not in {"required", "not-required"}:
        return [f"[{contract_id}] Decision must be required or not-required"]
    metadata["skill_decision"] = decision

    count_value = _ai_agent_field(section, "Repeated procedure count")
    count_match = re.search(r"\b(\d+)\b", count_value)
    if not count_match:
        errors.append(f"[{contract_id}] Repeated procedure count must be an integer")
        count = -1
    else:
        count = int(count_match.group(1))
    for label in ("Reuse evidence", "Decision source"):
        if not _is_meaningful_ai_agent_value(_ai_agent_field(section, label)):
            errors.append(f"[{contract_id}] missing meaningful {label}")

    metadata["skill_resources"] = []
    if decision == "not-required":
        if count >= 3:
            errors.append(f"[{contract_id}] not-required conflicts with procedure count >= 3")
        return errors

    name = _ai_agent_field(section, "Skill name")
    location = _ai_agent_field(section, "Location").replace("\\", "/")
    resources = _ai_agent_field(section, "Bundled resources")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        errors.append(f"[{contract_id}] Skill name must be kebab-case")
    expected_location = f"src/agent/{agent_key}/skills/{name}/"
    if location.rstrip("/") + "/" != expected_location:
        errors.append(f"[{contract_id}] Skill Location must be {expected_location}")
    for label in ("Runtime loading", "Validation"):
        if not _is_meaningful_ai_agent_value(_ai_agent_field(section, label)):
            errors.append(f"[{contract_id}] required Skill missing {label}")
    if not _is_meaningful_ai_agent_value(resources):
        errors.append(f"[{contract_id}] Bundled resources needs a list or reasoned none")
    metadata["skill_name"] = name
    metadata["skill_location"] = expected_location
    metadata["skill_resources"] = _parse_ai_agent_resources(resources)
    return errors


def _validate_ai_agent_distribution(
    section: str,
    metadata: Dict[str, Any],
) -> List[str]:
    """AG-CAP-09 の配布契約を検証し、`mcp.json` の要否を metadata へ残す。"""
    contract_id = "AG-CAP-09"
    metadata["mcp_config_required"] = False

    is_na, errors = _reasoned_ai_agent_na(section, contract_id)
    if is_na:
        return errors

    for label in (
        "Channels",
        "Plugin manifest",
        "Plugin components",
        "Metadata visibility",
        "Decision source",
    ):
        if not _is_meaningful_ai_agent_value(_ai_agent_field(section, label)):
            errors.append(f"[{contract_id}] missing meaningful {label}")

    # ラベル正規化は非 ASCII を落とすため、否定語（日本語の「不要」等）は判定に使えない。
    # 採用は肯定語の閉じた語彙が明示されたときだけとし、既定を not-required にする。
    components = _normalize_ai_agent_label(_ai_agent_field(section, "Plugin components"))
    mcp_required = any(
        token in components for token in ("mcpjsonrequired", "mcpjsonyes")
    )
    metadata["mcp_config_required"] = mcp_required
    if mcp_required and not _is_meaningful_ai_agent_value(_ai_agent_field(section, "MCP exposure")):
        errors.append(f"[{contract_id}] mcp.json requires a meaningful MCP exposure")

    channels = _normalize_ai_agent_label(_ai_agent_field(section, "Channels"))
    m365_selected = (
        "microsoft365" in channels or "teams" in channels
    ) and "notselected" not in channels
    if m365_selected and not _is_meaningful_ai_agent_value(
        _ai_agent_field(section, "M365 publish")
    ):
        errors.append(f"[{contract_id}] Microsoft 365 channel requires a meaningful M365 publish")
    return errors


def _agentic_retrieval_route_selected(routes: List[Dict[str, str]]) -> bool:
    """AG-CAP-03のPreferred / FallbackにFoundry IQ経路が含まれるかを判定する。"""
    preferred_key = _normalize_ai_agent_label("Preferred route")
    fallback_key = _normalize_ai_agent_label("Fallback route")
    for row in routes:
        for key in (preferred_key, fallback_key):
            token = _normalize_ai_agent_label(row.get(key, ""))
            if "foundryiq" in token or "agenticretrieval" in token:
                return True
            if "azureaisearch" in token and "knowledgebase" in token:
                return True
    return False


def _is_declared_absent_route(value: str) -> bool:
    """`none: ...` / `n/a: ...` のように「経路なし」を宣言した値かを判定する。"""
    head = re.split(r"[:：]", value.strip(), maxsplit=1)[0].strip().casefold()
    return head in {"none", "n/a", "na", "not applicable", "なし", "無し"}


def _agent_tool_ids(metadata: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """AG-CAP-03/04/05から`正規化ID -> 表示名`を重複排除して収集する。

    TB-CAP-01のTool総数とTB-CAP-04のTool表を同じ実データから導き、
    件数だけ合って中身がずれる状態を作らせない。
    Preferred / Fallbackは同じ経路が複数行に現れるため重複排除する。
    """
    rest: Dict[str, str] = {}
    tool_id_key = _normalize_ai_agent_label("Tool ID")
    for row in metadata.get("crud_rows") or []:
        display = row.get(tool_id_key, "").strip()
        if display:
            rest.setdefault(_normalize_ai_agent_label(display), display)

    mcp: Dict[str, str] = {}
    allowlist_key = _normalize_ai_agent_label("Tool allowlist")
    for row in metadata.get("mcp_rows") or []:
        for token in re.split(r"[,\s]+", row.get(allowlist_key, "")):
            token = token.strip().strip("`")
            if token and token != "*":
                mcp.setdefault(_normalize_ai_agent_label(token), token)

    routes: Dict[str, str] = {}
    for label in ("Preferred route", "Fallback route"):
        key = _normalize_ai_agent_label(label)
        for row in metadata.get("routes") or []:
            raw = row.get(key, "")
            if not _is_meaningful_ai_agent_value(raw) or _is_declared_absent_route(raw):
                continue
            display = raw.strip()
            routes.setdefault(_normalize_ai_agent_label(display), display)
    return {"rest": rest, "mcp": mcp, "routes": routes}


def _count_agent_tools(metadata: Dict[str, Any]) -> Dict[str, int]:
    """TB-CAP-01のTool総数と内訳を実データから算出する。"""
    ids = _agent_tool_ids(metadata)
    counts = {key: len(value) for key, value in ids.items()}
    counts["total"] = sum(counts.values())
    return counts


def _validate_toolbox_inventory(
    section: str, counts: Dict[str, int], metadata: Dict[str, Any]
) -> List[str]:
    contract_id = "TB-CAP-01"
    errors: List[str] = []
    declared: Dict[str, int] = {}
    for label, key in (
        ("Total tools", "total"),
        ("REST tools", "rest"),
        ("MCP allowlist tools", "mcp"),
        ("Distinct search routes", "routes"),
    ):
        raw = _ai_agent_field(section, label)
        match = re.search(r"\d+", raw)
        if not match:
            errors.append(f"[{contract_id}] missing numeric {label}")
            continue
        declared[key] = int(match.group())
    if len(declared) == 4:
        breakdown = declared["rest"] + declared["mcp"] + declared["routes"]
        if breakdown != declared["total"]:
            errors.append(
                f"[{contract_id}] breakdown sum {breakdown} does not match "
                f"Total tools {declared['total']}"
            )
        elif declared["total"] != counts["total"]:
            # 宣言値とAG-CAPからの算出値がずれると、閾値判定の根拠が崩れる。
            errors.append(
                f"[{contract_id}] Total tools {declared['total']} does not match the "
                f"{counts['total']} tools counted from AG-CAP-03/04/05 "
                f"(REST {counts['rest']} + MCP {counts['mcp']} + routes {counts['routes']})"
            )
    if not _is_meaningful_ai_agent_value(_ai_agent_field(section, "Counting source")):
        errors.append(f"[{contract_id}] missing Counting source")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", _ai_agent_field(section, "Checked at")):
        errors.append(f"[{contract_id}] Checked at must use YYYY-MM-DD")
    metadata["toolbox_declared_counts"] = declared
    metadata["toolbox_actual_counts"] = counts
    return errors


def _validate_toolbox_decision(
    section: str, counts: Dict[str, int], metadata: Dict[str, Any], policy: str
) -> List[str]:
    contract_id = "TB-CAP-02"
    errors: List[str] = []
    tool_search = _ai_agent_field(section, "Tool search").strip().casefold()
    if tool_search not in {"enabled", "disabled"}:
        errors.append(f"[{contract_id}] Tool search must be enabled or disabled")
    elif policy == "yes" and tool_search != "enabled":
        errors.append(
            f"[{contract_id}] tool search policy yes requires Tool search: enabled"
        )
    elif policy == "no" and tool_search != "disabled":
        errors.append(
            f"[{contract_id}] tool search policy no requires Tool search: disabled"
        )
    elif tool_search == "disabled" and counts["total"] > _TOOLBOX_TOOL_COUNT_THRESHOLD:
        if not _is_meaningful_ai_agent_value(_ai_agent_field(section, "Reason")):
            errors.append(
                f"[{contract_id}] Tool search disabled with {counts['total']} tools "
                f"requires a Reason"
            )
    topology = _ai_agent_field(section, "Connection topology").strip().casefold()
    if topology not in _TOOLBOX_TOPOLOGIES:
        errors.append(
            f"[{contract_id}] Connection topology must be one of "
            f"{sorted(_TOOLBOX_TOPOLOGIES)}"
        )
    metadata["toolbox_tool_search"] = tool_search
    metadata["toolbox_topology"] = topology
    return errors


def _validate_toolbox_pinning(section: str, metadata: Dict[str, Any]) -> List[str]:
    contract_id = "TB-CAP-03"
    errors: List[str] = []
    pinned = _ai_agent_field(section, "Pinned tools")
    if not _has_reasoned_none(pinned):
        errors.append(
            f"[{contract_id}] Pinned tools requires concrete tools or a reasoned none"
        )
    wildcard = _ai_agent_field(section, "Wildcard pin")
    uses_wildcard = "*" in wildcard and "not used" not in wildcard.casefold()
    if uses_wildcard and metadata.get("toolbox_tool_search") == "enabled":
        errors.append(
            f"[{contract_id}] wildcard pin disables tool search; "
            "remove it or set Tool search to disabled"
        )
    pinned_ids: set[str] = set()
    if not _is_declared_absent_route(pinned):
        pinned_ids = {
            token.strip().strip("`")
            for token in re.split(r"[,\s]+", pinned)
            if token.strip()
        }
    metadata["toolbox_pinned"] = pinned_ids
    return errors


def _validate_toolbox_search_metadata(
    section: str, metadata: Dict[str, Any], expected: Dict[str, str]
) -> List[str]:
    contract_id = "TB-CAP-04"
    errors: List[str] = []
    header = ["Tool ID", "Pinned", "Additional search text"]
    rows = _find_ai_agent_table(section, header)
    if rows is None:
        return [f"[{contract_id}] missing Search Metadata table"]
    text_key = _normalize_ai_agent_label("Additional search text")
    pinned_key = _normalize_ai_agent_label("Pinned")
    id_key = _normalize_ai_agent_label("Tool ID")
    declared: set[str] = set()
    declared_pinned: set[str] = set()
    for row in rows:
        tool_id = row.get(id_key, "").strip()
        normalized = _normalize_ai_agent_label(tool_id)
        if normalized in declared:
            errors.append(f"[{contract_id}] duplicate Tool row {tool_id!r}")
        declared.add(normalized)
        if row.get(pinned_key, "").strip().casefold() == "yes":
            declared_pinned.add(normalized)
            continue
        text = row.get(text_key, "").strip()
        if not text:
            errors.append(
                f"[{contract_id}] unpinned Tool {tool_id!r} missing Additional search text"
            )
    missing = sorted(expected[key] for key in expected.keys() - declared)
    if missing:
        errors.append(f"[{contract_id}] missing Tool rows: {', '.join(missing)}")
    unknown = sorted(declared - expected.keys())
    if unknown:
        errors.append(
            f"[{contract_id}] unknown Tool rows not declared in AG-CAP-03/04/05: "
            f"{', '.join(unknown)}"
        )
    pinned = metadata.get("toolbox_pinned")
    if pinned is not None:
        expected_pinned = {_normalize_ai_agent_label(value) for value in pinned}
        if declared_pinned != expected_pinned:
            errors.append(
                f"[{contract_id}] Pinned column does not match the TB-CAP-03 pin list "
                f"(TB-CAP-03 {sorted(expected_pinned)}, TB-CAP-04 {sorted(declared_pinned)})"
            )
    return errors


def _validate_toolbox_budget(section: str, metadata: Dict[str, Any]) -> List[str]:
    contract_id = "TB-CAP-05"
    errors: List[str] = []
    raw = _ai_agent_field(section, "limit")
    match = re.search(r"\d+", raw)
    if not match:
        errors.append(f"[{contract_id}] missing numeric limit")
    else:
        limit = int(match.group())
        if not 1 <= limit <= _TOOLBOX_MAX_SEARCH_LIMIT:
            errors.append(
                f"[{contract_id}] limit {limit} is outside 1-{_TOOLBOX_MAX_SEARCH_LIMIT}"
            )
        metadata["toolbox_limit"] = limit
    for label in ("Expected tool_search calls per turn", "Overflow behavior"):
        if not _is_meaningful_ai_agent_value(_ai_agent_field(section, label)):
            errors.append(f"[{contract_id}] missing {label}")
    return errors


def _validate_toolbox_contracts(
    visible: str, metadata: Dict[str, Any], policy: str = "auto"
) -> List[str]:
    """Tool Search方針とTool総数に応じてTB-CAP-01〜05を検証する。"""
    normalized_policy = (policy or "auto").strip().casefold()
    if normalized_policy not in _TOOL_SEARCH_POLICIES:
        # 未知値を既定へ丸めると利用者の指定が黙って別方針に変わる。
        return [
            f"[TB-CAP] unknown tool search policy {policy!r}; expected one of "
            f"{', '.join(_TOOL_SEARCH_POLICIES)}"
        ]
    counts = _count_agent_tools(metadata)
    metadata["toolbox"] = {"selected": False}
    over_threshold = counts["total"] > _TOOLBOX_TOOL_COUNT_THRESHOLD
    if normalized_policy == "auto" and not over_threshold:
        return []
    if normalized_policy == "auto":
        cause = (
            f"the design declares {counts['total']} tools "
            f"(threshold {_TOOLBOX_TOOL_COUNT_THRESHOLD})"
        )
    else:
        cause = f"the tool search policy is {normalized_policy}"
    na_only = {"TB-CAP-03", "TB-CAP-04", "TB-CAP-05"} if normalized_policy == "no" else set()

    errors: List[str] = []
    sections: Dict[str, str] = {}
    for contract_id, heading in _TOOLBOX_CONTRACT_HEADINGS.items():
        section, section_errors = _extract_ai_agent_contract_section(
            visible,
            contract_id,
            heading,
        )
        if section_errors:
            errors.append(f"[{contract_id}] {heading} is required because {cause}")
            continue
        if contract_id in na_only:
            is_na, na_errors = _reasoned_ai_agent_na(section, contract_id)
            if not is_na:
                errors.append(
                    f"[{contract_id}] tool search policy no requires a reasoned N/A"
                )
            errors.extend(na_errors)
            continue
        sections[contract_id] = section
    if "TB-CAP-01" in sections:
        errors.extend(_validate_toolbox_inventory(sections["TB-CAP-01"], counts, metadata))
    if "TB-CAP-02" in sections:
        errors.extend(
            _validate_toolbox_decision(
                sections["TB-CAP-02"], counts, metadata, normalized_policy
            )
        )
    if "TB-CAP-03" in sections:
        errors.extend(_validate_toolbox_pinning(sections["TB-CAP-03"], metadata))
    if "TB-CAP-04" in sections:
        expected = {
            key: display
            for group in _agent_tool_ids(metadata).values()
            for key, display in group.items()
        }
        errors.extend(
            _validate_toolbox_search_metadata(sections["TB-CAP-04"], metadata, expected)
        )
    if "TB-CAP-05" in sections:
        errors.extend(_validate_toolbox_budget(sections["TB-CAP-05"], metadata))
    pinned = {
        _normalize_ai_agent_label(value) for value in metadata.get("toolbox_pinned") or ()
    }
    metadata["toolbox"] = {
        "selected": True,
        "policy": normalized_policy,
        "tool_search": metadata.get("toolbox_tool_search", ""),
        "topology": metadata.get("toolbox_topology", ""),
        "pinned": pinned,
        "unpinned": {
            key
            for group in _agent_tool_ids(metadata).values()
            for key in group
            if key not in pinned
        },
        "limit": metadata.get("toolbox_limit"),
    }
    return errors


def _agentic_retrieval_reasoned_flag(value: str, allowed: set[str]) -> bool:
    """`<許可語>: 理由` 形式であることを検証する。"""
    head, separator, reason = value.partition(":")
    if not separator:
        head, separator, reason = value.partition("：")
    if head.strip().casefold() not in allowed:
        return False
    return bool(separator and _is_meaningful_ai_agent_value(reason))


def _agentic_retrieval_finite(value: str) -> bool:
    return _is_meaningful_ai_agent_value(value) and not _AGENTIC_RETRIEVAL_UNBOUNDED.search(value)


def _validate_agentic_retrieval_knowledge_base(
    section: str,
    contract: Dict[str, Any],
) -> tuple[List[str], str]:
    contract_id = "AR-CAP-01"
    is_na, errors = _reasoned_ai_agent_na(section, contract_id)
    if is_na:
        errors.append(
            f"[{contract_id}] Knowledge Base Contract must not be N/A "
            "while an Agentic Retrieval route is selected in AG-CAP-03"
        )
        return errors, ""

    for label in (
        "Knowledge base name",
        "Knowledge domain",
        "Query planning LLM",
        "Effort rationale",
        "Retrieval instructions",
        "Index semantic configuration",
        "Decision source",
    ):
        if not _is_meaningful_ai_agent_value(_ai_agent_field(section, label)):
            errors.append(f"[{contract_id}] missing {label}")

    effort = _ai_agent_field(section, "Retrieval reasoning effort").strip().casefold()
    if effort not in _AGENTIC_RETRIEVAL_EFFORTS:
        errors.append(
            f"[{contract_id}] Retrieval reasoning effort must be minimal, low, or medium"
        )
        effort = ""

    output_mode_raw = _ai_agent_field(section, "Output mode")
    output_mode = _normalize_ai_agent_label(output_mode_raw)
    if output_mode not in _AGENTIC_RETRIEVAL_OUTPUT_MODES:
        errors.append(f"[{contract_id}] Output mode must be extractiveData or answerSynthesis")
    elif effort == "minimal" and output_mode != "extractivedata":
        errors.append(
            f"[{contract_id}] minimal retrieval reasoning effort requires Output mode extractiveData"
        )

    status = _ai_agent_field(section, "Design status").strip().casefold()
    if status not in _AI_AGENT_DESIGN_STATUSES:
        errors.append(f"[{contract_id}] invalid Design status {status!r}")

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", _ai_agent_field(section, "Checked at")):
        errors.append(f"[{contract_id}] Checked at must use YYYY-MM-DD")

    count_match = re.search(r"\d+", _ai_agent_field(section, "Knowledge source count"))
    if not count_match:
        errors.append(f"[{contract_id}] Knowledge source count must be an integer")
    else:
        contract["knowledge_source_count"] = int(count_match.group())

    if effort == "medium" and not _is_meaningful_ai_agent_value(
        _ai_agent_field(section, "Region availability")
    ):
        errors.append(
            f"[{contract_id}] medium retrieval reasoning effort requires Region availability"
        )

    contract["reasoning_effort"] = effort
    contract["knowledge_base_name"] = _ai_agent_field(section, "Knowledge base name")
    return errors, effort


def _validate_agentic_retrieval_sources(
    section: str,
    effort: str,
    contract: Dict[str, Any],
) -> tuple[List[str], List[Dict[str, str]]]:
    contract_id = "AR-CAP-02"
    required_headers = (
        "KS name",
        "Kind",
        "Locality",
        "Always query",
        "Selection description",
        "Ingestion",
        "Freshness SLO",
        "Permission boundary",
        "Required for Done",
        "Design status",
        "Checked at",
        "Decision source",
    )
    rows = _find_ai_agent_table(section, required_headers)
    if not rows:
        return [f"[{contract_id}] Knowledge Source Matrix is missing or empty"], []

    errors: List[str] = []
    if len(rows) > _AGENTIC_RETRIEVAL_MAX_KNOWLEDGE_SOURCES:
        errors.append(
            f"[{contract_id}] a knowledge base allows at most "
            f"{_AGENTIC_RETRIEVAL_MAX_KNOWLEDGE_SOURCES} knowledge sources, found {len(rows)}"
        )
    if len(rows) < _AGENTIC_RETRIEVAL_MIN_KNOWLEDGE_SOURCES:
        errors.append(
            f"[{contract_id}] agentic retrieval needs at least "
            f"{_AGENTIC_RETRIEVAL_MIN_KNOWLEDGE_SOURCES} knowledge sources to search "
            f"across sources in one request, found {len(rows)}"
        )

    names: List[str] = []
    for row in rows:
        name = row[_normalize_ai_agent_label("KS name")]
        names.append(name)
        for label in (
            "KS name",
            "Kind",
            "Ingestion",
            "Freshness SLO",
            "Permission boundary",
            "Decision source",
        ):
            if not _is_meaningful_ai_agent_value(row[_normalize_ai_agent_label(label)]):
                errors.append(f"[{contract_id}] knowledge source {name!r} missing {label}")

        locality = row[_normalize_ai_agent_label("Locality")].strip().casefold()
        if locality not in {"indexed", "remote"}:
            errors.append(
                f"[{contract_id}] knowledge source {name!r} Locality must be indexed or remote"
            )
        if not _agentic_retrieval_reasoned_flag(
            row[_normalize_ai_agent_label("Always query")], {"true", "false"}
        ):
            errors.append(
                f"[{contract_id}] knowledge source {name!r} Always query must be "
                "true or false with a reason"
            )
        if row[_normalize_ai_agent_label("Required for Done")].strip().casefold() not in {"yes", "no"}:
            errors.append(
                f"[{contract_id}] knowledge source {name!r} Required for Done must be yes or no"
            )
        status = row[_normalize_ai_agent_label("Design status")].strip().casefold()
        if status not in _AI_AGENT_DESIGN_STATUSES:
            errors.append(
                f"[{contract_id}] knowledge source {name!r} invalid Design status {status!r}"
            )
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[_normalize_ai_agent_label("Checked at")]):
            errors.append(
                f"[{contract_id}] knowledge source {name!r} Checked at must use YYYY-MM-DD"
            )
        if effort in {"low", "medium"} and not _is_meaningful_ai_agent_value(
            row[_normalize_ai_agent_label("Selection description")]
        ):
            errors.append(
                f"[{contract_id}] knowledge source {name!r} requires Selection description "
                f"at {effort} retrieval reasoning effort"
            )
        if effort == "minimal" and _normalize_ai_agent_label(
            row[_normalize_ai_agent_label("Kind")]
        ) == "web":
            errors.append(
                f"[{contract_id}] minimal retrieval reasoning effort does not support "
                f"the web knowledge source {name!r}"
            )

    contract["knowledge_sources"] = names
    return errors, rows


def _validate_agentic_retrieval_budget(section: str) -> List[str]:
    contract_id = "AR-CAP-03"
    errors: List[str] = []
    for label in (
        "Expected subqueries per request",
        "Retrieval token budget",
        "LLM token budget",
        "Latency target p50",
        "Latency target p95",
        "Max runtime",
        "Max output size",
        "Degradation policy",
        "Measurement method",
    ):
        value = _ai_agent_field(section, label)
        if not _is_meaningful_ai_agent_value(value):
            errors.append(f"[{contract_id}] missing {label}")
        elif not _agentic_retrieval_finite(value):
            errors.append(f"[{contract_id}] {label} must be a finite value")
    if _ai_agent_field(section, "Retrieval reasoning effort"):
        errors.append(
            f"[{contract_id}] retrieval reasoning effort must be declared only in AR-CAP-01"
        )
    return errors


def _validate_agentic_retrieval_evidence(
    section: str,
    contract: Dict[str, Any],
) -> List[str]:
    contract_id = "AR-CAP-04"
    errors: List[str] = []
    for label in ("Source references", "Activity log"):
        value = _ai_agent_field(section, label)
        if not _agentic_retrieval_reasoned_flag(value, {"enabled", "disabled"}):
            errors.append(f"[{contract_id}] {label} must be enabled or disabled with a reason")
    for label in ("Citation fields", "Blocked condition", "Secret handling", "Decision source"):
        if not _is_meaningful_ai_agent_value(_ai_agent_field(section, label)):
            errors.append(f"[{contract_id}] missing {label}")
    return errors


def _validate_agentic_retrieval_mcp(
    section: str,
    contract: Dict[str, Any],
) -> List[str]:
    contract_id = "AR-CAP-05"
    is_na, errors = _reasoned_ai_agent_na(section, contract_id)
    if is_na:
        contract["mcp_exposure"] = None
        return errors

    for label in ("Consumer", "Auth type", "Approval mode", "Decision source"):
        if not _is_meaningful_ai_agent_value(_ai_agent_field(section, label)):
            errors.append(f"[{contract_id}] missing {label}")
    status = _ai_agent_field(section, "Design status").strip().casefold()
    if status not in _AI_AGENT_DESIGN_STATUSES:
        errors.append(f"[{contract_id}] invalid Design status {status!r}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", _ai_agent_field(section, "Checked at")):
        errors.append(f"[{contract_id}] Checked at must use YYYY-MM-DD")

    is_foundry_agent_service = "foundryagentservice" in _normalize_ai_agent_label(
        _ai_agent_field(section, "Consumer")
    )
    tools = [
        token.strip()
        for token in re.split(r"[,、/]|\band\b", _ai_agent_field(section, "Tool allowlist"))
        if token.strip()
    ]
    if not tools:
        errors.append(f"[{contract_id}] missing Tool allowlist")
    elif is_foundry_agent_service and tools != [_AGENTIC_RETRIEVAL_ALLOWED_MCP_TOOL]:
        errors.append(
            f"[{contract_id}] Foundry Agent Service Tool allowlist must contain only "
            f"{_AGENTIC_RETRIEVAL_ALLOWED_MCP_TOOL}"
        )

    per_user = _ai_agent_field(section, "Per-user authorization")
    if not _agentic_retrieval_reasoned_flag(per_user, {"required", "not-required"}):
        errors.append(
            f"[{contract_id}] Per-user authorization must be required or not-required with a reason"
        )
    elif (
        per_user.partition(":")[0].strip().casefold() == "required"
        and is_foundry_agent_service
    ):
        errors.append(
            f"[{contract_id}] Per-user authorization required cannot be satisfied through "
            "Foundry Agent Service because per-request MCP headers are unsupported"
        )

    contract["mcp_exposure"] = {"foundry_agent_service": is_foundry_agent_service, "tools": tools}
    return errors


def _validate_agentic_retrieval_policy(
    policy: str,
    routes: List[Dict[str, str]],
    selected: bool,
) -> List[str]:
    """FR-WF-AAG-04: 方針値と AG-CAP-03 の経路選択の整合を検証する。"""
    normalized = str(policy).strip().casefold()
    if normalized not in _AGENTIC_RETRIEVAL_POLICIES:
        return [
            f"[AR-CAP-01] unknown agentic retrieval policy {policy!r}; "
            "expected auto, yes, or no"
        ]
    if normalized == "yes" and not selected:
        request_class_key = _normalize_ai_agent_label("Request class")
        needs_agentic = any(
            _normalize_ai_agent_label(row.get(request_class_key, ""))
            == "enterpriseunstructured"
            for row in routes
        )
        if needs_agentic:
            return [
                "[AR-CAP-01] agentic retrieval policy yes requires a Foundry IQ or "
                "Azure AI Search agentic retrieval route for enterprise-unstructured"
            ]
    if normalized == "no" and selected:
        return [
            "[AR-CAP-01] agentic retrieval policy no forbids the Foundry IQ or "
            "Azure AI Search agentic retrieval route"
        ]
    return []


def _validate_agentic_retrieval_contracts(
    visible: str,
    metadata: Dict[str, Any],
) -> List[str]:
    """AG-CAP-03でFoundry IQ経路を選んだ場合のAR-CAP-01〜05を検証する。"""
    errors: List[str] = []
    sections: Dict[str, str] = {}
    for contract_id, heading in _AGENTIC_RETRIEVAL_CONTRACT_HEADINGS.items():
        section, section_errors = _extract_ai_agent_contract_section(
            visible,
            contract_id,
            heading,
        )
        errors.extend(section_errors)
        sections[contract_id] = section

    contract: Dict[str, Any] = {"selected": True}
    effort = ""
    rows: List[Dict[str, str]] = []

    if sections["AR-CAP-01"]:
        kb_errors, effort = _validate_agentic_retrieval_knowledge_base(
            sections["AR-CAP-01"],
            contract,
        )
        errors.extend(kb_errors)
    if sections["AR-CAP-02"]:
        source_errors, rows = _validate_agentic_retrieval_sources(
            sections["AR-CAP-02"],
            effort,
            contract,
        )
        errors.extend(source_errors)
    if sections["AR-CAP-03"]:
        errors.extend(_validate_agentic_retrieval_budget(sections["AR-CAP-03"]))
    if sections["AR-CAP-04"]:
        errors.extend(_validate_agentic_retrieval_evidence(sections["AR-CAP-04"], contract))
    if sections["AR-CAP-05"]:
        errors.extend(_validate_agentic_retrieval_mcp(sections["AR-CAP-05"], contract))

    declared_count = contract.get("knowledge_source_count")
    if sections["AR-CAP-01"] and rows and declared_count is not None and declared_count != len(rows):
        errors.append(
            f"[AR-CAP-01] Knowledge source count {declared_count} does not match "
            f"{len(rows)} Knowledge Source Matrix rows"
        )

    metadata["agentic_retrieval"] = contract
    return errors


def _validate_agentic_retrieval_implementation(
    contract: Dict[str, Any],
    config: Any,
    source: str,
) -> List[str]:
    """AR-CAP-01 / 02 / 05 の設計値が実装設定とコードへ反映されているかを検証する。"""
    errors: List[str] = []

    knowledge_base_name = str(contract.get("knowledge_base_name") or "").strip()
    if knowledge_base_name and (
        config is None or not _ai_agent_config_contains(config, knowledge_base_name)
    ):
        errors.append(
            f"[AR-CAP-01] knowledge base name missing from configuration: {knowledge_base_name}"
        )

    effort = str(contract.get("reasoning_effort") or "").strip()
    if effort:
        configured = {
            str(value).strip().casefold()
            for value in _ai_agent_json_key_values(config, "retrieval_reasoning_effort")
            if not isinstance(value, (Mapping, list))
        }
        if effort not in configured:
            errors.append(
                f"[AR-CAP-01] configuration must set retrieval_reasoning_effort to {effort}"
            )

    for name in contract.get("knowledge_sources") or []:
        cleaned = str(name).strip()
        if cleaned and (config is None or not _ai_agent_config_contains(config, cleaned)):
            errors.append(
                f"[AR-CAP-02] knowledge source missing from configuration: {cleaned}"
            )

    exposure = contract.get("mcp_exposure")
    if isinstance(exposure, Mapping) and exposure.get("foundry_agent_service"):
        entries = _ai_agent_json_key_values(config, "tool_allowlist")
        entries += _ai_agent_json_key_values(config, "allowed_tools")
        declared = {
            str(tool).strip()
            for entry in entries
            for tool in (entry if isinstance(entry, list) else [entry])
        }
        if _AGENTIC_RETRIEVAL_ALLOWED_MCP_TOOL not in declared:
            errors.append(
                "[AR-CAP-05] configuration must expose the knowledge base through "
                f"{_AGENTIC_RETRIEVAL_ALLOWED_MCP_TOOL}"
            )
        # Learn: Foundry Agent Service が対応する MCP ツールは knowledge_base_retrieve のみ。
        # 許可リストに他のツールが混ざると実行時に解決できないため、実装時点で拒否する。
        extra_tools = sorted(
            tool for tool in declared if tool and tool != _AGENTIC_RETRIEVAL_ALLOWED_MCP_TOOL
        )
        if extra_tools:
            errors.append(
                "[AR-CAP-05] Foundry Agent Service supports only "
                f"{_AGENTIC_RETRIEVAL_ALLOWED_MCP_TOOL}; remove: "
                + ", ".join(extra_tools)
            )
        if _AGENTIC_RETRIEVAL_ALLOWED_MCP_TOOL not in source:
            errors.append(
                f"[AR-CAP-05] source does not reference {_AGENTIC_RETRIEVAL_ALLOWED_MCP_TOOL}"
            )
    return errors


def _parse_ai_agent_design(
    path: Path,
    tool_search_policy: str = "auto",
    agentic_retrieval_policy: str = "auto",
) -> tuple[List[str], Dict[str, Any]]:
    metadata: Dict[str, Any] = {"agent_key": ""}
    if not path.is_file():
        return [f"AI Agent design artifact not found: {path}"], metadata
    if path.is_symlink():
        return [f"AI Agent design artifact must not be a symlink: {path}"], metadata
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"AI Agent design artifact read error: {exc}"], metadata

    match = re.fullmatch(r"agent-detail-(?P<key>.+)\.md", path.name)
    if not match:
        return [f"AI Agent design filename must be agent-detail-{{key}}.md: {path.name}"], metadata
    agent_key = match.group("key")
    metadata["agent_key"] = agent_key
    visible = _strip_ai_agent_markdown_code(text)
    errors = _ai_agent_secret_errors(path, text)
    sections: Dict[str, str] = {}
    for contract_id, heading in _AI_AGENT_CONTRACT_HEADINGS.items():
        section, section_errors = _extract_ai_agent_contract_section(
            visible,
            contract_id,
            heading,
        )
        errors.extend(section_errors)
        sections[contract_id] = section

    if sections["AG-CAP-01"]:
        errors.extend(_validate_ai_agent_goal(sections["AG-CAP-01"], metadata))
    if sections["AG-CAP-02"]:
        errors.extend(_validate_ai_agent_runtime(sections["AG-CAP-02"], metadata))
    if sections["AG-CAP-03"]:
        errors.extend(_validate_ai_agent_routing(sections["AG-CAP-03"], metadata))
    if sections["AG-CAP-04"]:
        errors.extend(_validate_ai_agent_crud(sections["AG-CAP-04"], metadata))
    if sections["AG-CAP-05"]:
        errors.extend(_validate_ai_agent_mcp(sections["AG-CAP-05"], metadata))
    if sections["AG-CAP-06"]:
        errors.extend(
            _validate_ai_agent_skill(
                sections["AG-CAP-06"],
                metadata,
                agent_key,
            )
        )
    if sections["AG-CAP-09"]:
        errors.extend(_validate_ai_agent_distribution(sections["AG-CAP-09"], metadata))

    if _agentic_retrieval_route_selected(metadata.get("routes", [])):
        errors.extend(_validate_agentic_retrieval_contracts(visible, metadata))
        agentic_selected = True
    else:
        agentic_selected = False
    errors.extend(
        _validate_agentic_retrieval_policy(
            agentic_retrieval_policy,
            metadata.get("routes", []),
            agentic_selected,
        )
    )

    errors.extend(_validate_toolbox_contracts(visible, metadata, tool_search_policy))

    mutation_intent = metadata.get("mutation_intent")
    active_mutations = [
        row
        for row in metadata.get("crud_rows", [])
        if row.get(_normalize_ai_agent_label("Operation"), "").casefold()
        in {"create", "update", "delete"}
    ]
    if mutation_intent == "required" and not active_mutations:
        errors.append("[AG-CAP-01/04] Mutation Intent required needs a required REST C/U/D Tool")
    if mutation_intent == "none" and active_mutations:
        errors.append("[AG-CAP-01/04] Mutation Intent none conflicts with required REST C/U/D")
    return errors, metadata


def validate_ai_agent_design_artifact(
    path: "Path | str",
    tool_search_policy: str = "auto",
    agentic_retrieval_policy: str = "auto",
) -> List[str]:
    """AAG Step 3のAG-CAP-01〜10設計成果物を決定的に検証する。"""
    errors, _ = _parse_ai_agent_design(
        Path(path), tool_search_policy, agentic_retrieval_policy
    )
    return errors


def _ai_agent_json_values(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for child in value.values():
            yield from _ai_agent_json_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _ai_agent_json_values(child)
    elif value is not None:
        yield str(value)


def _ai_agent_json_key_values(value: Any, wanted_key: str) -> List[Any]:
    wanted = _normalize_ai_agent_label(wanted_key)
    found: List[Any] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _normalize_ai_agent_label(str(key)) == wanted:
                found.append(child)
            found.extend(_ai_agent_json_key_values(child, wanted_key))
    elif isinstance(value, list):
        for child in value:
            found.extend(_ai_agent_json_key_values(child, wanted_key))
    return found


def _ai_agent_config_contains(config: Any, expected: str) -> bool:
    normalized = expected.strip().casefold()
    if any(value.strip().casefold() == normalized for value in _ai_agent_json_values(config)):
        return True

    def has_structured_key(value: Any) -> bool:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if (
                    str(key).strip().casefold() == normalized
                    and isinstance(child, (Mapping, list))
                    and bool(child)
                ):
                    return True
                if has_structured_key(child):
                    return True
        elif isinstance(value, list):
            return any(has_structured_key(child) for child in value)
        return False

    return has_structured_key(config)


def _strip_ai_agent_source_comments_and_strings(source: str) -> str:
    """callable宣言検査用にPython/C#のcomment/docstringを保守的に除外する。"""
    stripped = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    stripped = re.sub(r"(?:'''|\"\"\").*?(?:'''|\"\"\")", "", stripped, flags=re.DOTALL)
    visible: List[str] = []
    for line in stripped.splitlines():
        if line.lstrip().startswith(("#", "//")):
            visible.append("")
            continue
        line = re.sub(r"\s+//.*$", "", line)
        visible.append(line)
    return "\n".join(visible)


def _ai_agent_source_has_callable(source: str, name: str) -> bool:
    visible = _strip_ai_agent_source_comments_and_strings(source)
    compact_name = name.replace("_", "")
    return bool(
        re.search(
            rf"^\s*(?:async\s+)?def\s+{name}\s*\(",
            visible,
            re.IGNORECASE | re.MULTILINE,
        )
        or re.search(
            rf"^\s*(?:(?:public|private|protected|internal|static|virtual|"
            rf"override|sealed|async)\s+)*[A-Za-z_][A-Za-z0-9_<>,.?\[\]]*\s+"
            rf"{compact_name}(?:Async)?\s*\(",
            visible,
            re.IGNORECASE | re.MULTILINE,
        )
    )


def _collect_ai_agent_files(agent_dir: Path) -> tuple[List[Path], List[str]]:
    files: List[Path] = []
    errors: List[str] = []
    for path in sorted(agent_dir.rglob("*")):
        if any(part in _AI_AGENT_IGNORED_DIRS for part in path.relative_to(agent_dir).parts):
            continue
        if path.is_symlink():
            errors.append(f"AAGD agent artifact must not be a symlink: {path}")
            continue
        if path.is_file() and path.suffix.casefold() in _AI_AGENT_TEXT_SUFFIXES:
            files.append(path)
    return files, errors


def _ai_agent_system_prompt_candidates(agent_dir: Path) -> List[Path]:
    return sorted(
        path
        for path in agent_dir.rglob("*.md")
        if "system" in path.name.casefold() and "prompt" in path.name.casefold()
    )


def _agent_toolbox_settings(config: Any) -> "Dict[str, Any] | None":
    """Agent 設定から toolbox ブロックを取り出し、キーを正規化して返す。"""
    for value in _ai_agent_json_key_values(config, "toolbox"):
        if isinstance(value, Mapping):
            return {
                _normalize_ai_agent_label(str(key)): item for key, item in value.items()
            }
    return None


def _validate_toolbox_implementation(
    toolbox: Mapping[str, Any],
    config: Any,
    agent_dir: Path,
    test_spec: Path,
) -> List[str]:
    """設計 TB-CAP と Agent 設定・System Prompt・test trace の一致を検証する。

    SDK シンボル名や API version は変動するため見ない。設定契約だけを照合する。
    """
    settings = _agent_toolbox_settings(config)
    if toolbox.get("tool_search") != "enabled":
        if settings is None:
            return []
        return [
            "[TB-CAP-02] tool search is disabled in the design; the Agent "
            "configuration must not declare a toolbox block"
        ]
    if settings is None:
        return ["[TB-CAP-02] Agent configuration is missing the toolbox block"]

    errors: List[str] = []
    declared_search = str(settings.get(_normalize_ai_agent_label("tool search"), "")).casefold()
    if declared_search != "enabled":
        errors.append("[TB-CAP-02] Agent configuration must set tool search to enabled")
    topology = str(toolbox.get("topology") or "")
    declared_topology = str(
        settings.get(_normalize_ai_agent_label("connection topology"), "")
    ).casefold()
    if topology and declared_topology != topology:
        errors.append(
            f"[TB-CAP-02] configuration connection topology {declared_topology!r} "
            f"does not match the design {topology!r}"
        )

    limit = toolbox.get("limit")
    declared_limit = settings.get(_normalize_ai_agent_label("tool search limit"))
    if limit is not None and declared_limit != limit:
        errors.append(
            f"[TB-CAP-05] configuration tool search limit {declared_limit!r} "
            f"does not match the design limit {limit}"
        )

    raw_pins = settings.get(_normalize_ai_agent_label("pinned tools")) or []
    if not isinstance(raw_pins, list):
        raw_pins = [raw_pins]
    if any(str(pin).strip() == "*" for pin in raw_pins):
        errors.append(
            "[TB-CAP-03] wildcard pin disables tool search; remove it from the "
            "Agent configuration"
        )
    else:
        declared_pins = {_normalize_ai_agent_label(str(pin)) for pin in raw_pins if str(pin).strip()}
        expected_pins = set(toolbox.get("pinned") or ())
        if declared_pins != expected_pins:
            errors.append(
                f"[TB-CAP-03] configuration pinned tools {sorted(declared_pins)} "
                f"do not match the design {sorted(expected_pins)}"
            )

    search_text = settings.get(_normalize_ai_agent_label("additional search text")) or {}
    described = (
        {
            _normalize_ai_agent_label(str(key))
            for key, value in search_text.items()
            if str(value).strip()
        }
        if isinstance(search_text, Mapping)
        else set()
    )
    missing_text = sorted(set(toolbox.get("unpinned") or ()) - described)
    if missing_text:
        errors.append(
            "[TB-CAP-04] configuration is missing additional search text for: "
            + ", ".join(missing_text)
        )

    candidates = _ai_agent_system_prompt_candidates(agent_dir)
    if len(candidates) == 1:
        prompt_text = candidates[0].read_text(encoding="utf-8", errors="replace")
        if "tool_search" not in prompt_text or not re.search(
            r"結論|conclud", prompt_text, re.IGNORECASE
        ):
            errors.append(
                "[TB-CAP-05] Agent System Prompt must require calling tool_search "
                "before concluding that a capability is missing"
            )

    errors.extend(_validate_toolbox_test_trace(test_spec))
    return errors


def _validate_toolbox_test_trace(path: Path) -> List[str]:
    if not path.is_file():
        return [f"[TB-CAP-01] Agent test specification not found: {path}"]
    text = path.read_text(encoding="utf-8", errors="replace")
    rows = _find_ai_agent_table(text, ("Test Case ID", "Contract ID", "Evidence")) or []
    errors: List[str] = []
    for contract_id in _TOOLBOX_CONTRACT_HEADINGS:
        traced = any(
            row[_normalize_ai_agent_label("Contract ID")].strip() == contract_id
            and _is_meaningful_ai_agent_value(row[_normalize_ai_agent_label("Evidence")])
            for row in rows
        )
        if not traced:
            errors.append(
                f"[{contract_id}] test specification is missing a Test Case ID trace"
            )
    return errors


def _validate_ai_agent_system_prompt(agent_dir: Path) -> List[str]:
    candidates = _ai_agent_system_prompt_candidates(agent_dir)
    if not candidates:
        return ["AAGD System Prompt file not found"]
    if len(candidates) != 1:
        return ["AAGD System Prompt must be managed in exactly one file"]
    try:
        text = candidates[0].read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"AAGD System Prompt read error: {exc}"]
    errors: List[str] = []
    heading_matches = list(
        re.finditer(r"^(?P<marks>#{1,6})\s+(?P<title>.+?)\s*$", text, re.MULTILINE)
    )
    for heading in (
        "Role",
        "Goals",
        "Non-Goals",
        "Inputs",
        "Tools",
        "Runtime Goal Loop",
        "Routing",
        "Procedure",
        "Output format",
        "Safeguards",
    ):
        match = next(
            (
                candidate
                for candidate in heading_matches
                if candidate.group("title").strip().casefold() == heading.casefold()
            ),
            None,
        )
        if match is None:
            errors.append(f"AAGD System Prompt missing heading: {heading}")
            continue
        level = len(match.group("marks"))
        end = len(text)
        for candidate in heading_matches:
            if candidate.start() > match.start() and len(candidate.group("marks")) <= level:
                end = candidate.start()
                break
        if not _is_meaningful_ai_agent_value(text[match.end():end]):
            errors.append(f"AAGD System Prompt heading has no meaningful body: {heading}")
    return errors


def _validate_ai_agent_test_trace(path: Path) -> List[str]:
    if not path.is_file():
        return [f"AAGD Agent test specification not found: {path}"]
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"AAGD Agent test specification read error: {exc}"]
    errors = _ai_agent_secret_errors(path, text)
    rows = _find_ai_agent_table(
        text,
        ("Test Case ID", "Contract ID", "Evidence"),
    )
    if not rows:
        errors.append("AAGD test specification capability trace table is missing or empty")
        return errors
    for contract_id in _AI_AGENT_CONTRACT_HEADINGS:
        matching_rows = [
            row
            for row in rows
            if row[_normalize_ai_agent_label("Contract ID")].strip() == contract_id
            and re.fullmatch(
                r"(?:TEST|TC)[-_A-Z0-9]+",
                row[_normalize_ai_agent_label("Test Case ID")],
                re.IGNORECASE,
            )
            and _is_meaningful_ai_agent_value(row[_normalize_ai_agent_label("Evidence")])
        ]
        if not matching_rows:
            errors.append(f"AAGD test specification missing Test Case ID trace for {contract_id}")
    return errors


def _validate_ai_agent_skill_artifacts(
    agent_dir: Path,
    source: str,
    metadata: Mapping[str, Any],
) -> List[str]:
    errors: List[str] = []
    skills_root = agent_dir / "skills"
    decision = metadata.get("skill_decision")
    if decision == "not-required":
        if skills_root.exists() and any(skills_root.rglob("*")):
            errors.append("[AG-CAP-06] not-required must not create Skill artifacts")
        return errors
    if decision != "required":
        return ["[AG-CAP-06] implementation cannot proceed with an unresolved Skill decision"]

    name = str(metadata.get("skill_name", ""))
    skill_dir = skills_root / name
    skill_path = skill_dir / "SKILL.md"
    if not skill_path.is_file():
        return [f"[AG-CAP-06] required SKILL.md not found: {skill_path}"]
    try:
        text = skill_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"[AG-CAP-06] SKILL.md read error: {exc}"]
    frontmatter = re.match(r"\A---\s*\n(?P<body>.*?)\n---\s*\n", text, re.DOTALL)
    if not frontmatter:
        errors.append("[AG-CAP-06] SKILL.md requires YAML frontmatter")
    else:
        header = frontmatter.group("body")
        name_match = re.search(r"^name:\s*(.+)$", header, re.MULTILINE)
        description_match = re.search(r"^description:\s*(.+)$", header, re.MULTILINE)
        if not name_match or name_match.group(1).strip() != name:
            errors.append("[AG-CAP-06] SKILL.md frontmatter name must match the design")
        elif len(name_match.group(1).strip()) > _AGENT_SKILL_MAX_NAME_LENGTH:
            errors.append(
                f"[AG-CAP-06] SKILL.md name must be at most "
                f"{_AGENT_SKILL_MAX_NAME_LENGTH} characters"
            )
        if not description_match or not _is_meaningful_ai_agent_value(description_match.group(1)):
            errors.append("[AG-CAP-06] SKILL.md requires a meaningful description")
        elif len(description_match.group(1).strip()) > _AGENT_SKILL_MAX_DESCRIPTION_LENGTH:
            errors.append(
                f"[AG-CAP-06] SKILL.md description must be at most "
                f"{_AGENT_SKILL_MAX_DESCRIPTION_LENGTH} characters"
            )
    for heading in ("Procedure", "Input", "Output", "Errors", "Completion"):
        if not re.search(rf"^#{{1,6}}\s+{heading}\s*$", text, re.MULTILINE):
            errors.append(f"[AG-CAP-06] SKILL.md missing heading: {heading}")
    for resource in metadata.get("skill_resources", []):
        resource_path = skill_dir / resource
        if not resource_path.is_file() or resource_path.is_symlink():
            errors.append(f"[AG-CAP-06] required Skill resource not found: {resource}")
    normalized_source = source.replace("\\", "/").casefold()
    if (
        name.casefold() not in normalized_source
        or not _ai_agent_source_has_callable(source, "load_skill")
    ):
        errors.append("[AG-CAP-06] required Skill has no explicit runtime loading trace")
    return errors


def validate_agent_plugin_manifest(
    agent_dir: "Path | str", agent_key: str
) -> List[str]:
    """AAGD Step 2.3 の Agent Plugins マニフェストを検証する（FR-WF-AAGD-06）。"""
    path = Path(agent_dir) / _AGENT_PLUGIN_MANIFEST_FILE
    if not path.is_file():
        return [f"[AGENT-PLUGIN] manifest not found: {path}"]
    # 仕様 §4.1: plugin root 外へ解決されるパッケージパスは拒否する。
    if path.is_symlink():
        return [f"[AGENT-PLUGIN] manifest must not be a symlink: {path}"]
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"[AGENT-PLUGIN] manifest read error ({path}): {exc}"]
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [f"[AGENT-PLUGIN] manifest is not valid JSON ({path}): {exc}"]
    if not isinstance(manifest, dict):
        return [f"[AGENT-PLUGIN] manifest must be a JSON object: {path}"]

    errors: List[str] = []
    unknown = sorted(set(manifest) - _AGENT_PLUGIN_ALLOWED_FIELDS)
    if unknown:
        errors.append(
            "[AGENT-PLUGIN] manifest has fields outside the Agent Plugins 1.0.0 "
            "schema: " + ", ".join(unknown)
        )
    if manifest.get("$schema") != _AGENT_PLUGIN_SCHEMA:
        errors.append(f"[AGENT-PLUGIN] $schema must be {_AGENT_PLUGIN_SCHEMA}")

    expected_name = str(agent_key).strip().casefold()
    name = manifest.get("name")
    if not isinstance(name, str) or name != expected_name:
        errors.append(
            f"[AGENT-PLUGIN] name must be the lowercased fan-out key {expected_name!r}"
        )
    elif len(name) > _AGENT_PLUGIN_MAX_NAME_LENGTH or not _AGENT_PLUGIN_NAME.fullmatch(name):
        errors.append(
            f"[AGENT-PLUGIN] name {name!r} violates the Agent Plugins name constraints"
        )

    for field in ("description", "version"):
        value = manifest.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"[AGENT-PLUGIN] {field} must be a non-empty string")
    return errors


def _agent_plugin_mcp_env_errors(
    server_name: str, field: str, mapping: Any
) -> List[str]:
    errors: List[str] = []
    if mapping is None:
        return errors
    if not isinstance(mapping, dict):
        return [f"[AGENT-PLUGIN] {server_name}.{field} must be an object"]
    for key, value in mapping.items():
        if not isinstance(value, str):
            errors.append(f"[AGENT-PLUGIN] {server_name}.{field}.{key} must be a string")
            continue
        if key in _AGENT_PLUGIN_RESERVED_VARS:
            errors.append(
                f"[AGENT-PLUGIN] {server_name}.{field} must not redefine the reserved "
                f"variable {key}"
            )
        if _AGENT_PLUGIN_CREDENTIAL_KEY.search(key) and "${" not in value:
            errors.append(
                f"[AGENT-PLUGIN] {server_name}.{field}.{key} must not embed a credential "
                "value (Agent Plugins 1.0.0 §7.2.1)"
            )
    return errors


def _agent_plugin_mcp_url_errors(server_name: str, url: Any) -> List[str]:
    if not isinstance(url, str) or not url.strip():
        return [f"[AGENT-PLUGIN] {server_name}.url must be a non-empty string"]
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold()
    except ValueError as exc:
        return [f"[AGENT-PLUGIN] {server_name}.url is not a parsable URL: {exc}"]
    if parsed.scheme not in {"http", "https"}:
        return [f"[AGENT-PLUGIN] {server_name}.url must be an absolute http(s) URL"]
    errors: List[str] = []
    if not host:
        errors.append(f"[AGENT-PLUGIN] {server_name}.url must declare a host")
    if parsed.username or parsed.password:
        errors.append(f"[AGENT-PLUGIN] {server_name}.url must not contain user info")
    if parsed.fragment:
        errors.append(f"[AGENT-PLUGIN] {server_name}.url must not contain a fragment")
    # loopback は仕様例外のため、別名を広げず代表的な 3 形式だけを認める。
    is_loopback = host in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme == "http" and host and not is_loopback:
        errors.append(
            f"[AGENT-PLUGIN] {server_name}.url must use HTTPS for a non-loopback host"
        )
    return errors


def validate_agent_plugin_mcp_config(
    agent_dir: "Path | str", required: bool
) -> List[str]:
    """AG-CAP-09 が採用した場合の `mcp.json` を検証する（Agent Plugins 1.0.0 §7.2）。"""
    path = Path(agent_dir) / _AGENT_PLUGIN_MCP_FILE
    if not path.is_file():
        if required:
            return [f"[AGENT-PLUGIN] mcp.json not found: {path}"]
        return []
    if not required:
        return [
            "[AGENT-PLUGIN] mcp.json exists but AG-CAP-09 Plugin components does not "
            f"select it: {path}"
        ]
    if path.is_symlink():
        return [f"[AGENT-PLUGIN] mcp.json must not be a symlink: {path}"]
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"[AGENT-PLUGIN] mcp.json read error ({path}): {exc}"]
    try:
        config = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [f"[AGENT-PLUGIN] mcp.json is not valid JSON ({path}): {exc}"]
    if not isinstance(config, dict):
        return [f"[AGENT-PLUGIN] mcp.json must be a JSON object: {path}"]

    errors: List[str] = []
    # キー名だけでは値側のリテラルを見逃すため、既存の secret 検出を本文へ適用する。
    errors.extend(_ai_agent_secret_errors(path, raw))
    unknown = sorted(set(config) - {"$schema", "mcpServers"})
    if unknown:
        errors.append(
            "[AGENT-PLUGIN] mcp.json has fields outside the Agent Plugins 1.0.0 "
            "schema: " + ", ".join(unknown)
        )
    if config.get("$schema") != _AGENT_PLUGIN_MCP_SCHEMA:
        errors.append(f"[AGENT-PLUGIN] mcp.json $schema must be {_AGENT_PLUGIN_MCP_SCHEMA}")

    servers = config.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        errors.append("[AGENT-PLUGIN] mcp.json mcpServers must be a non-empty object")
        return errors

    for server_name, server in servers.items():
        if not isinstance(server, dict):
            errors.append(f"[AGENT-PLUGIN] {server_name} must be an object")
            continue
        extra = sorted(set(server) - _AGENT_PLUGIN_MCP_SERVER_FIELDS)
        if extra:
            errors.append(
                f"[AGENT-PLUGIN] {server_name} has fields outside the MCP server "
                "schema: " + ", ".join(extra)
            )
        transport = server.get("type")
        if transport not in _AGENT_PLUGIN_MCP_TRANSPORTS:
            errors.append(
                f"[AGENT-PLUGIN] {server_name}.type must be one of "
                + ", ".join(sorted(_AGENT_PLUGIN_MCP_TRANSPORTS))
            )
            continue
        if transport == "stdio":
            command = server.get("command")
            if not isinstance(command, str) or not command.strip():
                errors.append(f"[AGENT-PLUGIN] {server_name}.command must be a non-empty string")
            args = server.get("args", [])
            if not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
                errors.append(f"[AGENT-PLUGIN] {server_name}.args must be a list of strings")
            if "url" in server or "headers" in server:
                errors.append(f"[AGENT-PLUGIN] {server_name} stdio must not declare url or headers")
        else:
            errors.extend(_agent_plugin_mcp_url_errors(server_name, server.get("url")))
            if "command" in server or "args" in server or "env" in server:
                errors.append(
                    f"[AGENT-PLUGIN] {server_name} remote transport must not declare "
                    "command, args, or env"
                )
        errors.extend(_agent_plugin_mcp_env_errors(server_name, "env", server.get("env")))
        errors.extend(
            _agent_plugin_mcp_env_errors(server_name, "headers", server.get("headers"))
        )
    return errors


def validate_ai_agent_implementation_artifacts(
    design_path: "Path | str",
    agent_dir: "Path | str",
    test_spec_path: "Path | str | None" = None,
    tool_search_policy: str = "auto",
    agentic_retrieval_policy: str = "auto",
) -> List[str]:
    """AAGD Step 2.3の設計・code・config・test traceを相互検証する。"""
    detail_path = Path(design_path)
    root = Path(agent_dir)
    design_errors, metadata = _parse_ai_agent_design(
        detail_path, tool_search_policy, agentic_retrieval_policy
    )
    errors = [f"AAGD design prerequisite: {error}" for error in design_errors]

    if test_spec_path is None:
        key = str(metadata.get("agent_key", ""))
        test_spec = detail_path.parent.parent / "test-specs" / f"{key}-test-spec.md"
    else:
        test_spec = Path(test_spec_path)
    errors.extend(_validate_ai_agent_test_trace(test_spec))

    if not root.is_dir():
        errors.append(f"AAGD agent directory not found: {root}")
        return errors
    if root.is_symlink():
        errors.append(f"AAGD agent directory must not be a symlink: {root}")
        return errors
    key = str(metadata.get("agent_key", ""))
    if key and root.name != key:
        errors.append(f"AAGD agent directory key mismatch: expected {key}, actual {root.name}")
    errors.extend(validate_agent_plugin_manifest(root, key))
    errors.extend(
        validate_agent_plugin_mcp_config(root, bool(metadata.get("mcp_config_required")))
    )

    files, file_errors = _collect_ai_agent_files(root)
    errors.extend(file_errors)
    text_by_path: Dict[Path, str] = {}
    for path in files:
        try:
            text_by_path[path] = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"AAGD agent artifact read error ({path}): {exc}")
            continue
        errors.extend(_ai_agent_secret_errors(path, text_by_path[path]))

    errors.extend(_validate_ai_agent_system_prompt(root))
    source_files = [path for path in files if path.suffix.casefold() in {".py", ".cs"}]
    if not source_files:
        errors.append("AAGD Agent implementation requires Python or C# source files")
        source = ""
    else:
        source = "\n".join(text_by_path.get(path, "") for path in source_files)

    config_candidates = [
        path for path in (root / "agent-config.json", root / "appsettings.json")
        if path.is_file()
    ]
    config: Any = None
    if len(config_candidates) != 1:
        errors.append("AAGD Agent configuration requires exactly one agent-config.json or appsettings.json")
    else:
        try:
            config = json.loads(config_candidates[0].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"AAGD Agent configuration is unreadable: {exc}")

    for contract_id in ("AG-CAP-01", "AG-CAP-02"):
        if contract_id not in source:
            errors.append(f"[{contract_id}] source implementation trace is missing")
    for name in ("plan", "act", "observe", "evaluate"):
        if not _ai_agent_source_has_callable(source, name):
            errors.append(f"[AG-CAP-02] Runtime Goal Loop callable {name} is missing")
    if not re.search(r"\b(?:for|while)\b", source):
        errors.append("[AG-CAP-02] Runtime Goal Loop has no finite iteration control")
    normalized_source = _normalize_ai_agent_label(source)
    if "maxiterations" not in normalized_source:
        errors.append("[AG-CAP-02] source does not consume Max iterations")
    max_values = _ai_agent_json_key_values(config, "max_iterations") if config is not None else []
    if not any(isinstance(value, int) and value > 0 for value in max_values):
        errors.append("[AG-CAP-02] configuration requires a positive max_iterations")
    for state in sorted(_AI_AGENT_STOP_STATES):
        if not re.search(rf"\b{state}\b", source, re.IGNORECASE):
            errors.append(f"[AG-CAP-02] source stop state {state} is missing")
    for marker in ("criterion", "evidence", "fingerprint"):
        if marker not in source.casefold():
            errors.append(f"[AG-CAP-02] source lacks {marker} evaluation trace")

    routes = metadata.get("routes", [])
    if routes:
        if "AG-CAP-03" not in source:
            errors.append("[AG-CAP-03] source implementation trace is missing")
        for row in routes:
            request_class = row[_normalize_ai_agent_label("Request class")]
            preferred = row[_normalize_ai_agent_label("Preferred route")]
            if config is None or not _ai_agent_config_contains(config, request_class):
                errors.append(f"[AG-CAP-03] selected Request class missing from configuration: {request_class}")
            if config is None or not _ai_agent_config_contains(config, preferred):
                errors.append(f"[AG-CAP-03] selected route missing from configuration: {preferred}")
            if preferred.casefold() not in source.casefold():
                errors.append(f"[AG-CAP-03] selected route missing from source: {preferred}")
        if not any(
            _ai_agent_source_has_callable(source, name)
            for name in ("route", "route_request", "retrieve", "search", "fetch")
        ):
            errors.append("[AG-CAP-03] selected route has no executable route adapter")
    elif config is not None:
        selected = _ai_agent_json_key_values(config, "selected_routes")
        if any(bool(value) for value in selected):
            errors.append("[AG-CAP-03] reasoned N/A conflicts with selected route configuration")

    agentic_retrieval = metadata.get("agentic_retrieval") or {}
    if agentic_retrieval.get("selected"):
        errors.extend(
            _validate_agentic_retrieval_implementation(agentic_retrieval, config, source)
        )

    toolbox = metadata.get("toolbox") or {}
    if toolbox.get("selected"):
        errors.extend(
            _validate_toolbox_implementation(toolbox, config, root, test_spec)
        )

    crud_rows = metadata.get("crud_rows", [])
    if crud_rows:
        if "AG-CAP-04" not in source:
            errors.append("[AG-CAP-04] source implementation trace is missing")
        if not re.search(r"http[_ ]?client|HttpClient|requests\.|httpx\.|aiohttp|urllib", source):
            errors.append("[AG-CAP-04] REST adapter implementation is missing")
        for row in crud_rows:
            tool_id = row[_normalize_ai_agent_label("Tool ID")]
            method = row[_normalize_ai_agent_label("REST method")]
            rest_path = row[_normalize_ai_agent_label("REST path")]
            for value, label in (
                (tool_id, "Tool ID"),
                (method, "method"),
                (rest_path, "path"),
            ):
                if config is None or not _ai_agent_config_contains(config, value):
                    errors.append(f"[AG-CAP-04] REST {label} missing from configuration: {value}")
                if value.casefold() not in source.casefold():
                    errors.append(f"[AG-CAP-04] REST {label} missing from source: {value}")
        for marker in ("approval", "idempotency", "audit", "auth", "error", "retry"):
            if marker not in source.casefold():
                errors.append(f"[AG-CAP-04] REST adapter lacks {marker} handling")
        if re.search(
            r"(?i)(?:execute|executenonquery|query)\s*\(\s*[\"']\s*"
            r"(?:INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER)\b",
            source,
        ):
            errors.append("[AG-CAP-04] direct SQL mutation is forbidden")
    elif config is not None:
        configured = _ai_agent_json_key_values(config, "rest_tools")
        if any(bool(value) for value in configured):
            errors.append("[AG-CAP-04] reasoned N/A conflicts with REST Tool configuration")

    mcp_rows = metadata.get("mcp_rows", [])
    if mcp_rows:
        if "AG-CAP-05" not in source:
            errors.append("[AG-CAP-05] source implementation trace is missing")
        for row in mcp_rows:
            server = row[_normalize_ai_agent_label("Server label")]
            tools = [
                value.strip()
                for value in re.split(r"[,\s]+", row[_normalize_ai_agent_label("Tool allowlist")])
                if value.strip()
            ]
            if config is None or not _ai_agent_config_contains(config, server):
                errors.append(f"[AG-CAP-05] MCP server missing from configuration: {server}")
            if server.casefold() not in source.casefold():
                errors.append(f"[AG-CAP-05] MCP server missing from source: {server}")
            for tool in tools:
                if config is None or not _ai_agent_config_contains(config, tool):
                    errors.append(f"[AG-CAP-05] MCP Tool missing from configuration: {tool}")
                if tool.casefold() not in source.casefold():
                    errors.append(f"[AG-CAP-05] MCP Tool missing from source: {tool}")
        for marker in ("mcp", "allowlist", "auth", "timeout", "failure"):
            if marker not in source.casefold():
                errors.append(f"[AG-CAP-05] MCP client lacks {marker} handling")
    else:
        if config is not None:
            configured = _ai_agent_json_key_values(config, "mcp_servers")
            if any(bool(value) for value in configured):
                errors.append("[AG-CAP-05] reasoned N/A conflicts with MCP configuration")
        if any("mcp" in path.name.casefold() for path in source_files):
            errors.append("[AG-CAP-05] reasoned N/A conflicts with MCP source artifacts")

    errors.extend(_validate_ai_agent_skill_artifacts(root, source, metadata))
    return errors


_TOOLBOX_TOKEN_SCOPE = "https://ai.azure.com/.default"
_TOOLBOX_RESOURCE_MARKER = re.compile(r"/toolboxes/|toolbox_search|call_tool")
_TOOLBOX_AGENT_REGISTRATION = re.compile(r"/assistants\b|/agents\b")
# verify script が実測値と設計値を突き合わせるための環境変数（ハードコード禁止）。
_TOOLBOX_VERIFY_MARKERS = (
    ("TB-CAP-02", "tools/list", "must read the initial tools/list"),
    ("TB-CAP-03", "PINNED_TOOLS", "must compare tools/list against ${PINNED_TOOLS}"),
    ("TB-CAP-04", "tool_search", "must discover a hidden Tool through tool_search"),
    ("TB-CAP-04", "call_tool", "must execute the discovered Tool through call_tool"),
    ("TB-CAP-05", "TOOL_SEARCH_LIMIT", "must bound results by ${TOOL_SEARCH_LIMIT}"),
    ("TB-CAP-02", "TOOLBOX_VERSION", "must assert the deployed ${TOOLBOX_VERSION}"),
)


def _read_deploy_script(path: Path) -> "str | None":
    if not path.is_file() or path.is_symlink():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _validate_agentic_retrieval_deploy(
    contract: Mapping[str, Any], infra_dir: Path
) -> List[str]:
    """AR-CAP-01 / 02 の設計値が deploy スクリプトから追跡できるかを照合する。

    Azure へは接続しない。実リソースとの一致確認は Prompt 側の AC 検証が担う。
    """
    if not infra_dir.is_dir() or infra_dir.is_symlink():
        return [f"[AR-CAP-01] Azure infrastructure directory not found: {infra_dir}"]

    scripts = "\n".join(
        text
        for path in sorted(infra_dir.rglob("*"))
        if (text := _read_deploy_script(path)) is not None
    )

    errors: List[str] = []
    knowledge_base_name = str(contract.get("knowledge_base_name") or "").strip()
    if knowledge_base_name and knowledge_base_name not in scripts:
        errors.append(
            "[AR-CAP-01] knowledge base name is not referenced by any deploy script "
            f"under {infra_dir.name}: {knowledge_base_name}"
        )
    for name in contract.get("knowledge_sources") or []:
        cleaned = str(name).strip()
        if cleaned and cleaned not in scripts:
            errors.append(
                "[AR-CAP-02] knowledge source is not referenced by any deploy script "
                f"under {infra_dir.name}: {cleaned}"
            )
    return errors


def _validate_toolbox_deploy_scripts(
    toolbox: Mapping[str, Any], infra_dir: Path
) -> List[str]:
    """deploy / verify scriptがTB-CAPどおりかを静的に照合する。

    shellを構文解析せず、必要な契約の存在と作成順序だけを見る。
    """
    create_path = infra_dir / "create-azure-agent-resources.sh"
    verify_path = infra_dir / "verify-agent-resources.sh"
    create = _read_deploy_script(create_path)
    verify = _read_deploy_script(verify_path)

    if toolbox.get("tool_search") != "enabled":
        return [
            f"[TB-CAP-02] tool search is disabled in the design; {path.name} "
            "must not create or verify a Toolbox"
            for path, text in ((create_path, create), (verify_path, verify))
            if text and _TOOLBOX_RESOURCE_MARKER.search(text)
        ]

    errors: List[str] = []
    if create is None:
        errors.append(f"[TB-CAP-02] Toolbox create script not found: {create_path.name}")
    else:
        if "toolbox_search" not in create:
            errors.append("[TB-CAP-02] create script must register the toolbox_search tool")
        if "Foundry-Features" not in create:
            errors.append(
                "[TB-CAP-02] create script must send the Foundry-Features preview header"
            )
        if _TOOLBOX_TOKEN_SCOPE not in create:
            errors.append(
                f"[TB-CAP-02] create script must request a token for the "
                f"{_TOOLBOX_TOKEN_SCOPE} scope"
            )
        version_at = create.find("/versions")
        if version_at < 0:
            errors.append(
                "[TB-CAP-02] create script must use the version-specific toolbox "
                "endpoint /toolboxes/{name}/versions"
            )
        else:
            registration = _TOOLBOX_AGENT_REGISTRATION.search(create)
            if registration and registration.start() < version_at:
                # Agent が参照する時点で version が無いと登録が壊れる。
                errors.append(
                    "[TB-CAP-02] create script registers the Agent before creating "
                    "the toolbox version"
                )

    if verify is None:
        errors.append(f"[TB-CAP-02] Toolbox verify script not found: {verify_path.name}")
    else:
        for contract_id, marker, message in _TOOLBOX_VERIFY_MARKERS:
            if marker not in verify:
                errors.append(f"[{contract_id}] verify script {message}")
        if "set -euo pipefail" not in verify:
            errors.append(
                "[TB-CAP-02] verify script must be fail-closed (set -euo pipefail)"
            )
    return errors


def validate_ai_agent_deploy_artifacts(
    design_path: "Path | str",
    infra_dir: "Path | str",
    tool_search_policy: str = "auto",
    agentic_retrieval_policy: str = "auto",
) -> List[str]:
    """AAGD Step 3のdeploy/verify scriptを設計TB-CAP / AR-CAPと照合する。"""
    detail_path = Path(design_path)
    design_errors, metadata = _parse_ai_agent_design(
        detail_path, tool_search_policy, agentic_retrieval_policy
    )
    errors = [f"AAGD design prerequisite: {error}" for error in design_errors]
    root = Path(infra_dir)

    agentic_retrieval = metadata.get("agentic_retrieval") or {}
    if agentic_retrieval.get("selected"):
        errors.extend(_validate_agentic_retrieval_deploy(agentic_retrieval, root))

    toolbox = metadata.get("toolbox") or {}
    if not toolbox.get("selected"):
        return errors

    if not root.is_dir() or root.is_symlink():
        errors.append(f"[TB-CAP-02] Azure infrastructure directory not found: {root}")
        return errors
    errors.extend(_validate_toolbox_deploy_scripts(toolbox, root))
    return errors


_TOOL_SEARCH_EVAL_MIN_QUERIES = 10
_TOOL_SEARCH_EVAL_MIN_MULTI_TOOL = 3
_TOOL_SEARCH_EVAL_BENCHMARK = re.compile(r"toolret|公開ベンチマーク|ベンチマーク公表値", re.IGNORECASE)
_TOOL_SEARCH_EVAL_UNMEASURED = re.compile(r"未測定|not measured|unmeasured", re.IGNORECASE)


def _tool_search_eval_query_errors(text: str) -> List[str]:
    contract_id = "TB-CAP-05"
    header = ("Query ID", "Query", "Expected tools", "Multi tool")
    rows = _find_ai_agent_table(text, header)
    if not rows:
        return [f"[{contract_id}] evaluation query table is missing"]

    errors: List[str] = []
    if len(rows) < _TOOL_SEARCH_EVAL_MIN_QUERIES:
        errors.append(
            f"[{contract_id}] evaluation needs at least "
            f"{_TOOL_SEARCH_EVAL_MIN_QUERIES} queries, found {len(rows)}"
        )
    multi_key = _normalize_ai_agent_label("Multi tool")
    multi = sum(1 for row in rows if row.get(multi_key, "").strip().casefold() == "yes")
    if multi < _TOOL_SEARCH_EVAL_MIN_MULTI_TOOL:
        errors.append(
            f"[{contract_id}] evaluation needs at least "
            f"{_TOOL_SEARCH_EVAL_MIN_MULTI_TOOL} multi-tool queries, found {multi}"
        )
    expected_key = _normalize_ai_agent_label("Expected tools")
    missing = [
        row.get(_normalize_ai_agent_label("Query ID"), "?").strip()
        for row in rows
        if not _is_meaningful_ai_agent_value(row.get(expected_key, ""))
    ]
    if missing:
        errors.append(
            f"[{contract_id}] queries without an expected Tool set: {', '.join(missing)}"
        )
    return errors


def _tool_search_eval_metric_errors(text: str) -> List[str]:
    contract_id = "TB-CAP-02"
    header = ("Metric", "Measured off", "Measured on", "Evidence")
    rows = _find_ai_agent_table(text, header)
    if not rows:
        return [
            f"[{contract_id}] metrics table with measured on/off columns is missing"
        ]

    errors: List[str] = []
    off_key = _normalize_ai_agent_label("Measured off")
    on_key = _normalize_ai_agent_label("Measured on")
    evidence_key = _normalize_ai_agent_label("Evidence")
    for row in rows:
        name = row.get(_normalize_ai_agent_label("Metric"), "?").strip()
        values = [row.get(off_key, "").strip(), row.get(on_key, "").strip()]
        if not all(values):
            errors.append(
                f"[{contract_id}] metric {name!r} is blank; record the value or "
                "未測定（理由）"
            )
            continue
        if any(_TOOL_SEARCH_EVAL_UNMEASURED.search(value) for value in values):
            if not all(
                _TOOL_SEARCH_EVAL_UNMEASURED.search(value)
                and re.search(r"[（(].+[)）]", value)
                for value in values
            ):
                errors.append(
                    f"[{contract_id}] metric {name!r} marked 未測定 without a reason"
                )
            continue
        if _TOOL_SEARCH_EVAL_BENCHMARK.search(row.get(evidence_key, "")):
            # 公開ベンチマーク値は自社カタログの効果ではない。
            errors.append(
                f"[{contract_id}] metric {name!r} cites a published benchmark as a "
                "measured value"
            )
    return errors


def validate_tool_search_eval_report(
    design_path: "Path | str",
    report_path: "Path | str",
    tool_search_policy: str = "auto",
) -> List[str]:
    """AAGD Step 4のtool search実測レポートを検証する。

    数値の正しさは判定せず、測定構造と証跡・未測定理由の存在だけを見る。
    """
    detail_path = Path(design_path)
    design_errors, metadata = _parse_ai_agent_design(detail_path, tool_search_policy)
    errors = [f"AAGD design prerequisite: {error}" for error in design_errors]

    path = Path(report_path)
    if not path.is_file() or path.is_symlink():
        errors.append(f"[TB-CAP-02] tool search evaluation report not found: {path}")
        return errors
    text = _strip_ai_agent_markdown_code(
        path.read_text(encoding="utf-8", errors="replace")
    )

    toolbox = metadata.get("toolbox") or {}
    measurable = toolbox.get("tool_search") == "enabled"
    is_na, na_errors = _reasoned_ai_agent_na(text, "TB-CAP-02")
    if is_na:
        if measurable:
            errors.append(
                "[TB-CAP-02] tool search is enabled in the design; the report "
                "must contain measurements instead of a reasoned N/A"
            )
        errors.extend(na_errors)
        if not measurable:
            return errors
    elif not measurable:
        errors.append(
            "[TB-CAP-02] no Toolbox is deployed; the report must record a reasoned "
            "N/A instead of being omitted"
        )
        return errors

    for label in ("Toolbox version", "Pinned tools", "Measured at"):
        if not _is_meaningful_ai_agent_value(_ai_agent_field(text, label)):
            errors.append(f"[TB-CAP-01] measurement condition {label!r} is missing")
    if not re.search(r"\d", _ai_agent_field(text, "limit")):
        errors.append("[TB-CAP-01] measurement condition 'limit' is missing")
    errors.extend(_tool_search_eval_query_errors(text))
    errors.extend(_tool_search_eval_metric_errors(text))
    if not _ai_agent_field(text, "Conclusion").strip() or not _is_meaningful_ai_agent_value(
        _ai_agent_field(text, "Rationale")
    ):
        errors.append(
            "[TB-CAP-02] report must state a Conclusion and Rationale for the "
            "TB-CAP-02 decision"
        )
    return errors


# --- 要件適合実測レポート（ASDW-WEB 5.3 / ADFDV 4.3 / AAGD 5 / AAR 7）---
_CONFORMANCE_LABELS = (
    "Schema-Version",
    "Workflow",
    "Step",
    "Agent",
    "Measured-At",
    "Target-Environment",
    "Measurement-Tool",
    "Secret-Redaction",
)
_CONFORMANCE_TABLE_HEADER = (
    "Req ID",
    "Kind",
    "Target",
    "Threshold",
    "Measured",
    "Judgement",
    "Headroom",
    "Evidence",
)
_CONFORMANCE_KINDS = ("FR", "NFR")
_CONFORMANCE_JUDGEMENTS = ("PASS", "FAIL", "NOT_MEASURED", "NO_TARGET")
_CONFORMANCE_NEED_MEASURED = ("PASS", "FAIL", "NO_TARGET")


def _requirements_conformance_table_errors(text: str) -> List[str]:
    rows = _find_ai_agent_table(text, _CONFORMANCE_TABLE_HEADER)
    if not rows:
        return ["[FR-WF-CONF-02] measurement table is missing or has no rows"]

    errors: List[str] = []
    req_key = _normalize_ai_agent_label("Req ID")
    kind_key = _normalize_ai_agent_label("Kind")
    target_key = _normalize_ai_agent_label("Target")
    threshold_key = _normalize_ai_agent_label("Threshold")
    judgement_key = _normalize_ai_agent_label("Judgement")
    measured_key = _normalize_ai_agent_label("Measured")
    headroom_key = _normalize_ai_agent_label("Headroom")
    evidence_key = _normalize_ai_agent_label("Evidence")
    seen_req_ids: set = set()
    for row in rows:
        req = row.get(req_key, "").strip() or "?"
        if req in seen_req_ids:
            # 同じ要件を複数行に分けて都合のよい行だけ PASS にさせない。
            errors.append(f"[FR-WF-CONF-02] duplicate 'Req ID': {req!r}")
        seen_req_ids.add(req)
        kind = row.get(kind_key, "").strip().upper()
        if kind not in _CONFORMANCE_KINDS:
            found = kind or "(blank)"
            errors.append(
                f"[FR-WF-CONF-02] {req}: 'Kind' must be FR or NFR, found {found!r}"
            )
        judgement = row.get(judgement_key, "").strip().upper()
        if judgement not in _CONFORMANCE_JUDGEMENTS:
            found = judgement or "(blank)"
            errors.append(
                f"[FR-WF-CONF-03] {req}: 'Judgement' must be one of "
                f"{', '.join(_CONFORMANCE_JUDGEMENTS)}, found {found!r}"
            )
            continue
        measured = row.get(measured_key, "").strip()
        if judgement in _CONFORMANCE_NEED_MEASURED and not measured:
            # 測っていない値を根拠に合否・目標未定義を主張させない。
            errors.append(
                f"[FR-WF-CONF-03] {req}: {judgement} requires a measured value"
            )
        if judgement in ("PASS", "FAIL"):
            # 合否は「目標に対する差」でしか主張できない。証跡と余裕度も欠かせない。
            for label, key in (
                ("Target", target_key),
                ("Threshold", threshold_key),
                ("Headroom", headroom_key),
                ("Evidence", evidence_key),
            ):
                if not row.get(key, "").strip():
                    errors.append(
                        f"[FR-WF-CONF-05] {req}: {judgement} requires {label!r}"
                    )
        if judgement == "NOT_MEASURED" and not row.get(evidence_key, "").strip():
            errors.append(
                f"[FR-WF-CONF-03] {req}: NOT_MEASURED requires a reason in 'Evidence'"
            )
    return errors


def validate_requirements_conformance_report(
    report_path: "Path | str",
    *,
    workflow_id: str,
    step_id: str,
) -> List[str]:
    """要件適合実測レポートを検証する（FR-WF-CONF-02 / 03 / 05）。

    測定値の妥当性は判定しない。未測定を PASS へ畳み込む経路と、
    目標未定義を測定済みと偽る経路だけを塞ぐ。
    """
    path = Path(report_path)
    if not path.is_file() or path.is_symlink():
        return [f"[FR-WF-CONF-02] conformance report not found: {path}"]
    text = _strip_ai_agent_markdown_code(
        path.read_text(encoding="utf-8", errors="replace")
    )

    errors: List[str] = []
    values = {label: _ai_agent_field(text, label) for label in _CONFORMANCE_LABELS}
    for label in _CONFORMANCE_LABELS:
        if not values[label].strip():
            errors.append(
                f"[FR-WF-CONF-02] measurement condition {label!r} is missing"
            )

    expected = {
        "Workflow": str(workflow_id).strip(),
        "Step": str(step_id).strip(),
        "Agent": "QA-RequirementsConformanceEval",
    }
    for label, want in expected.items():
        found = values[label].strip()
        if found and found != want:
            errors.append(
                f"[FR-WF-CONF-02] {label!r} must be {want!r}, found {found!r}"
            )
    redaction = values["Secret-Redaction"].strip()
    if redaction and redaction.casefold() != "confirmed":
        errors.append(
            f"[FR-WF-CONF-02] 'Secret-Redaction' must be confirmed, found {redaction!r}"
        )

    errors.extend(_requirements_conformance_table_errors(text))

    for label in ("Conclusion", "Rationale"):
        if not _is_meaningful_ai_agent_value(_ai_agent_field(text, label)):
            errors.append(f"[FR-WF-CONF-02] {label!r} is missing")
    # 該当なしは none と書かせる。空欄は判断の放棄と区別できない。
    if not _ai_agent_field(text, "Simplification-Candidate").strip():
        errors.append(
            "[FR-WF-CONF-05] 'Simplification-Candidate' is missing; "
            "write none when there is no candidate"
        )
    return errors


# --- 検索経路の適正化実測レポート（AAGD 6、AG-CAP-10）---
_ROUTE_RIGHTSIZING_LABELS = (
    "Schema-Version",
    "Workflow",
    "Step",
    "Agent",
    "Measured-At",
    "Dataset",
    "Dataset-Size",
    "Secret-Redaction",
)
_ROUTE_RIGHTSIZING_TABLE_HEADER = (
    "Rung",
    "Route",
    "Accuracy",
    "Tokens",
    "Latency",
    "Judgement",
    "Evidence",
)
_ROUTE_RIGHTSIZING_JUDGEMENTS = ("KEEP", "DOWNGRADE", "INSUFFICIENT", "NOT_MEASURED")
_ROUTE_RIGHTSIZING_NEED_METRICS = ("KEEP", "DOWNGRADE")

# --- Microsoft 365 / Teams 公開レポート（AAGD 7、AG-CAP-09）---
_M365_PUBLISH_LABELS = (
    "Schema-Version",
    "Workflow",
    "Step",
    "Agent",
    "Published-At",
    "Publish-Scope",
    "Auth-Scheme",
    "Secret-Redaction",
)
_M365_PUBLISH_TABLE_HEADER = (
    "Agent Key",
    "Channel",
    "Publish Scope",
    "App Version",
    "Judgement",
    "Approval",
    "Evidence",
)
_M365_PUBLISH_JUDGEMENTS = ("PUBLISHED", "PENDING_APPROVAL", "NOT_SELECTED", "FAILED")


def _fixed_report_condition_errors(
    text: str,
    labels: Tuple[str, ...],
    expected: Dict[str, str],
    contract_id: str,
) -> List[str]:
    """測定条件ラベルの存在と、workflow / step / agent の一致を検証する。"""
    errors: List[str] = []
    values = {label: _ai_agent_field(text, label) for label in labels}
    for label in labels:
        if not values[label].strip():
            errors.append(f"[{contract_id}] report condition {label!r} is missing")
    for label, want in expected.items():
        found = values.get(label, "").strip()
        if found and found != want:
            errors.append(f"[{contract_id}] {label!r} must be {want!r}, found {found!r}")
    redaction = values.get("Secret-Redaction", "").strip()
    if redaction and redaction.casefold() != "confirmed":
        errors.append(
            f"[{contract_id}] 'Secret-Redaction' must be confirmed, found {redaction!r}"
        )
    return errors


def validate_route_rightsizing_report(
    report_path: "Path | str",
    *,
    workflow_id: str,
    step_id: str,
) -> List[str]:
    """検索経路の適正化実測レポートを検証する（AG-CAP-10）。

    測定値そのものは判定しない。1 段だけの比較を「適正」と結論する経路と、
    未実測を判定値へ畳み込む経路を塞ぐ。
    """
    contract_id = "AG-CAP-10"
    path = Path(report_path)
    if not path.is_file() or path.is_symlink():
        return [f"[{contract_id}] route rightsizing report not found: {path}"]
    text = _strip_ai_agent_markdown_code(path.read_text(encoding="utf-8", errors="replace"))

    errors = _fixed_report_condition_errors(
        text,
        _ROUTE_RIGHTSIZING_LABELS,
        {
            "Workflow": str(workflow_id).strip(),
            "Step": str(step_id).strip(),
            "Agent": "QA-AgentRouteRightsizingEval",
        },
        contract_id,
    )

    rows = _find_ai_agent_table(text, _ROUTE_RIGHTSIZING_TABLE_HEADER)
    if rows is None:
        # ヘッダーのみの表もここへ落ちるため、列と行の両方を示す。
        errors.append(
            f"[{contract_id}] comparison table needs the columns "
            + " | ".join(_ROUTE_RIGHTSIZING_TABLE_HEADER)
            + " and at least 2 data rows"
        )
        return errors
    if len(rows) < 2:
        # 1 段だけの測定は比較ではない。AG-CAP-10 は 2 段以上の実測を要求する。
        errors.append(
            f"[{contract_id}] comparison table needs 2 or more rungs, found {len(rows)}"
        )

    judgement_key = _normalize_ai_agent_label("Judgement")
    evidence_key = _normalize_ai_agent_label("Evidence")
    metric_keys = [_normalize_ai_agent_label(name) for name in ("Accuracy", "Tokens", "Latency")]
    for row in rows:
        rung = row.get(_normalize_ai_agent_label("Rung"), "").strip() or "?"
        judgement = row.get(judgement_key, "").strip().upper()
        if judgement not in _ROUTE_RIGHTSIZING_JUDGEMENTS:
            found = judgement or "(blank)"
            errors.append(
                f"[{contract_id}] {rung}: 'Judgement' must be one of "
                f"{', '.join(_ROUTE_RIGHTSIZING_JUDGEMENTS)}, found {found!r}"
            )
            continue
        if judgement in _ROUTE_RIGHTSIZING_NEED_METRICS:
            missing = [
                name
                for name, key in zip(("Accuracy", "Tokens", "Latency"), metric_keys)
                if not row.get(key, "").strip()
            ]
            if missing:
                errors.append(
                    f"[{contract_id}] {rung}: {judgement} requires measured "
                    + ", ".join(missing)
                )
        if judgement == "NOT_MEASURED" and not row.get(evidence_key, "").strip():
            errors.append(
                f"[{contract_id}] {rung}: NOT_MEASURED requires a reason in 'Evidence'"
            )

    for label in ("Conclusion", "Rationale", "Recommended-Route"):
        if not _is_meaningful_ai_agent_value(_ai_agent_field(text, label)):
            errors.append(f"[{contract_id}] {label!r} is missing")
    conclusion = _ai_agent_field(text, "Conclusion").strip().upper()
    if conclusion and conclusion not in _ROUTE_RIGHTSIZING_JUDGEMENTS:
        errors.append(
            f"[{contract_id}] 'Conclusion' must be one of "
            f"{', '.join(_ROUTE_RIGHTSIZING_JUDGEMENTS)}, found {conclusion!r}"
        )
    return errors


def validate_m365_publish_report(
    report_path: "Path | str",
    *,
    workflow_id: str,
    step_id: str,
) -> List[str]:
    """Microsoft 365 / Teams 公開レポートを検証する（AG-CAP-09）。

    公開そのものの成否は判定しない。公開していないのに公開済みと書く経路と、
    公開メタデータへ資格情報を書く経路を塞ぐ。
    """
    contract_id = "AG-CAP-09"
    path = Path(report_path)
    if not path.is_file() or path.is_symlink():
        return [f"[{contract_id}] M365 publish report not found: {path}"]
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = _strip_ai_agent_markdown_code(raw)

    errors = _fixed_report_condition_errors(
        text,
        _M365_PUBLISH_LABELS,
        {
            "Workflow": str(workflow_id).strip(),
            "Step": str(step_id).strip(),
            "Agent": "Dev-Agent-M365Publish",
        },
        contract_id,
    )
    # 公開メタデータは利用者に見えるため、レポートにも生の資格情報を残させない。
    errors.extend(_ai_agent_secret_errors(path, raw))

    rows = _find_ai_agent_table(text, _M365_PUBLISH_TABLE_HEADER)
    if rows is None:
        # ヘッダーのみの表もここへ落ちるため、列と行の両方を示す。
        errors.append(
            f"[{contract_id}] publish table needs the columns "
            + " | ".join(_M365_PUBLISH_TABLE_HEADER)
            + " and at least 1 data row"
        )
        return errors

    judgement_key = _normalize_ai_agent_label("Judgement")
    version_key = _normalize_ai_agent_label("App Version")
    evidence_key = _normalize_ai_agent_label("Evidence")
    for row in rows:
        agent_key = row.get(_normalize_ai_agent_label("Agent Key"), "").strip() or "?"
        judgement = row.get(judgement_key, "").strip().upper()
        if judgement not in _M365_PUBLISH_JUDGEMENTS:
            found = judgement or "(blank)"
            errors.append(
                f"[{contract_id}] {agent_key}: 'Judgement' must be one of "
                f"{', '.join(_M365_PUBLISH_JUDGEMENTS)}, found {found!r}"
            )
            continue
        if judgement in ("PUBLISHED", "PENDING_APPROVAL") and not row.get(
            version_key, ""
        ).strip():
            errors.append(
                f"[{contract_id}] {agent_key}: {judgement} requires an App Version"
            )
        if judgement in ("NOT_SELECTED", "FAILED") and not row.get(evidence_key, "").strip():
            errors.append(
                f"[{contract_id}] {agent_key}: {judgement} requires a reason in 'Evidence'"
            )

    for label in ("Conclusion", "Rationale", "Consumer-Setup"):
        if not _is_meaningful_ai_agent_value(_ai_agent_field(text, label)):
            errors.append(f"[{contract_id}] {label!r} is missing")
    return errors


def validate_ai_agent_capability_artifacts(
    workflow_id: str,
    design_path: "Path | str",
    *,
    agent_dir: "Path | str | None" = None,
    test_spec_path: "Path | str | None" = None,
    tool_search_policy: str = "auto",
    agentic_retrieval_policy: str = "auto",
) -> List[str]:
    """AAG/AAGDだけをallowlistし、他workflowではno-opにするdispatcher。"""
    workflow = (workflow_id or "").strip().casefold()
    if workflow == "aag":
        return validate_ai_agent_design_artifact(
            design_path, tool_search_policy, agentic_retrieval_policy
        )
    if workflow == "aagd":
        if agent_dir is None:
            return ["AAGD agent directory is required for capability validation"]
        return validate_ai_agent_implementation_artifacts(
            design_path,
            agent_dir,
            test_spec_path,
            tool_search_policy,
            agentic_retrieval_policy,
        )
    return []
