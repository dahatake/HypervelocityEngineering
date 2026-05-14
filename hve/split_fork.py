"""hve/split_fork.py — SPLIT_REQUIRED 発生時の subissues.md パース & サブタスク fork ロジック。

`runner.py` から呼ばれる純粋関数群。SDK 依存を持たず、副作用は
ファイル I/O とログのみ。SDK セッション生成・実行は呼び出し側 (runner) の責務。

== 設計根拠 ==

- subissues.md フォーマット: `.github/skills/task-dag-planning/references/subissues-template.md`
- 配置規則: `.github/skills/work-artifacts-layout/SKILL.md` §「work/ ディレクトリ構造（2系統）」
- 完了報告: `.github/copilot-instructions.md` §7.1 / §7.3
- 検証マーカー: 同 §0「タスク完了報告の検証マーカー必須記載書式」

== 公開 API ==

- `SubIssueDef` — パース結果のデータクラス
- `discover_subissues_md(work_root, agent_name, parent_step_id)` — subissues.md 探索
- `parse_subissues_md(path)` — subissues.md パース
- `build_subtask_prompt(subissue, parent_step_id, parent_custom_agent)` — サブタスク用プロンプト構築
- `check_subtask_completion(work_dir)` — 完了判定（completion-report.md + 検証マーカー）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SubIssueDef:
    """subissues.md の 1 ブロックを表すデータ。

    Attributes:
        index: 1-based ブロック番号（subissues.md 内の出現順）。
        title: `<!-- title: ... -->` の値。空・プレースホルダ禁止。
        labels: `<!-- labels: a,b -->` を CSV パースしたリスト。なければ空。
        custom_agent: `<!-- custom_agent: ... -->` の値。なければ None。
        depends_on: `<!-- depends_on: 1,2 -->` を 1-indexed の int リストに変換。なければ空。
        body: H2 見出し以降のサブタスク本文（タイトル行含む）。
    """
    index: int
    title: str
    labels: List[str] = field(default_factory=list)
    custom_agent: Optional[str] = None
    depends_on: List[int] = field(default_factory=list)
    body: str = ""


class SubIssuesParseError(ValueError):
    """subissues.md パース失敗時に送出される例外。"""


# ---------------------------------------------------------------------------
# 検証マーカー（copilot-instructions.md §0 と一致させる）
# ---------------------------------------------------------------------------

_VALIDATION_MARKER_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"<!--\s*validation-confirmed\s*-->", re.IGNORECASE),
    re.compile(r"^#+\s*(検証|検証結果|Validation)\b", re.MULTILINE),
    re.compile(r"^\s*[-*]\s*\*?\*?(検証|Validation)\*?\*?\s*[:：]", re.MULTILINE),
]

_PLACEHOLDER_PATTERN = re.compile(r"REPLACE_ME", re.IGNORECASE)


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------

def discover_subissues_md(
    work_root: Path,
    custom_agent: Optional[str],
    parent_step_id: str,
) -> Optional[Path]:
    """親 Step の Agent が SPLIT_REQUIRED 時に出力した subissues.md を探索する。

    探索順序:
      1. work/<custom_agent>/Issue-*/subissues.md   （Custom Agent モード）
      2. work/Issue-*/subissues.md                  （非 Custom Agent モード）

    候補が複数ある場合は **最終更新時刻が最も新しいもの** を返す（並列実行で
    複数の Issue-* が存在する場合を許容するため）。

    Args:
        work_root: リポジトリルートの `work/` ディレクトリ Path
        custom_agent: 親 Step の Custom Agent 名。None / 空文字なら非 Agent モードのみ探索。
        parent_step_id: 親 Step ID（ログ用。探索キーには未使用）。

    Returns:
        見つかった subissues.md の Path。見つからなければ None。
    """
    candidates: List[Path] = []

    if custom_agent:
        agent_dir = work_root / custom_agent
        if agent_dir.is_dir():
            candidates.extend(agent_dir.glob("Issue-*/subissues.md"))

    candidates.extend(work_root.glob("Issue-*/subissues.md"))

    # ファイル実在のみ通す（glob は通常 file のみだが念のため）
    existing = [p for p in candidates if p.is_file()]
    if not existing:
        return None

    # 最終更新が最新のものを返す
    existing.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return existing[0]


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------

_SUBISSUE_MARKER = "<!-- subissue -->"
_TITLE_RE = re.compile(r"<!--\s*title:\s*(.*?)\s*-->", re.IGNORECASE)
_LABELS_RE = re.compile(r"<!--\s*labels:\s*(.*?)\s*-->", re.IGNORECASE)
_CUSTOM_AGENT_RE = re.compile(r"<!--\s*custom_agent:\s*(.*?)\s*-->", re.IGNORECASE)
_DEPENDS_ON_RE = re.compile(r"<!--\s*depends_on:\s*(.*?)\s*-->", re.IGNORECASE)


def parse_subissues_md(path: Path) -> List[SubIssueDef]:
    """subissues.md をパースして SubIssueDef のリストを返す。

    `<!-- subissue -->` マーカーで分割し、各ブロック内の
    `<!-- title / labels / custom_agent / depends_on -->` メタを抽出する。

    Args:
        path: subissues.md の Path

    Returns:
        ブロック出現順の SubIssueDef リスト。

    Raises:
        SubIssuesParseError:
          - ファイル不在
          - subissue ブロックが 0 件
          - title が空 / プレースホルダ (`REPLACE_ME` を含む)
          - depends_on の値が int に変換できない
          - depends_on の値が自身以上のブロック番号を指す（前方参照）
    """
    if not path.is_file():
        raise SubIssuesParseError(f"subissues.md が見つかりません: {path}")

    # CRLF / LF / CR の混在に対応（ユーザーログでも CRLF 問題が観測されている）
    raw = path.read_text(encoding="utf-8")
    text = raw.replace("\r\n", "\n").replace("\r", "\n")

    # ブロック分割: マーカー行の直前で split
    # 最初のマーカーより前 (ファイルヘッダ <!-- parent_issue --> 部) は捨てる
    chunks = text.split(_SUBISSUE_MARKER)
    if len(chunks) <= 1:
        raise SubIssuesParseError(
            f"`{_SUBISSUE_MARKER}` ブロックが 0 件: {path}"
        )

    blocks = chunks[1:]  # ヘッダ部を除く
    result: List[SubIssueDef] = []

    for idx, block in enumerate(blocks, start=1):
        # title 抽出（必須）
        m_title = _TITLE_RE.search(block)
        if not m_title:
            raise SubIssuesParseError(
                f"ブロック #{idx}: `<!-- title: ... -->` が見つかりません ({path})"
            )
        title = m_title.group(1).strip()
        if not title:
            raise SubIssuesParseError(
                f"ブロック #{idx}: title が空 ({path})"
            )
        if _PLACEHOLDER_PATTERN.search(title):
            raise SubIssuesParseError(
                f"ブロック #{idx}: title にプレースホルダ ({title!r}) が残存 ({path})"
            )

        # labels 抽出（任意）
        labels: List[str] = []
        m_labels = _LABELS_RE.search(block)
        if m_labels:
            labels = [s.strip() for s in m_labels.group(1).split(",") if s.strip()]

        # custom_agent 抽出（任意）
        custom_agent: Optional[str] = None
        m_ca = _CUSTOM_AGENT_RE.search(block)
        if m_ca:
            ca_val = m_ca.group(1).strip()
            if ca_val and not _PLACEHOLDER_PATTERN.search(ca_val):
                custom_agent = ca_val

        # depends_on 抽出（任意・1-indexed）
        depends_on: List[int] = []
        m_dep = _DEPENDS_ON_RE.search(block)
        if m_dep:
            raw_dep = m_dep.group(1).strip()
            if raw_dep:
                try:
                    depends_on = [int(s.strip()) for s in raw_dep.split(",") if s.strip()]
                except ValueError as exc:
                    raise SubIssuesParseError(
                        f"ブロック #{idx}: depends_on の値が int でない "
                        f"({raw_dep!r}) ({path}): {exc}"
                    ) from exc
                # 前方参照禁止（自身 idx 以上）
                for d in depends_on:
                    if d < 1:
                        raise SubIssuesParseError(
                            f"ブロック #{idx}: depends_on={d} は 1 以上である必要があります ({path})"
                        )
                    if d >= idx:
                        raise SubIssuesParseError(
                            f"ブロック #{idx}: depends_on={d} は自身以上のブロックを参照しています "
                            f"（前方参照禁止）({path})"
                        )

        # body: コメントマーカー行をすべて除外し、本文 (H2 以降) を残す
        body_lines: List[str] = []
        for line in block.splitlines():
            stripped = line.strip()
            # メタコメント行 (HTML コメントだけの行) は除外
            if (stripped.startswith("<!--") and stripped.endswith("-->")
                    and "subissue" not in stripped.lower()):
                # title/labels/custom_agent/depends_on はメタなので除外
                if any(k in stripped.lower() for k in ("title:", "labels:", "custom_agent:", "depends_on:")):
                    continue
            body_lines.append(line)
        body = "\n".join(body_lines).strip()

        result.append(SubIssueDef(
            index=idx,
            title=title,
            labels=labels,
            custom_agent=custom_agent,
            depends_on=depends_on,
            body=body,
        ))

    return result


# ---------------------------------------------------------------------------
# build_subtask_prompt
# ---------------------------------------------------------------------------

_SUBTASK_PROMPT_TEMPLATE = """\
あなたは親 Step.{parent_step_id} (Custom Agent: {parent_custom_agent}) の SPLIT_REQUIRED
判定により分割された **サブタスク Sub-{index:03d}** を実行します。

== 重要ルール ==
- これは単一責務サブタスクです。**SPLIT_REQUIRED を再発させてはなりません**。
- 親タスクの context_size 制約により分割されたため、本タスクは self-contained に完遂すること。
- 完了時は以下を必ず作成すること:
  1. work/{work_subdir}/completion-report.md
  2. completion-report.md 内に検証マーカー `<!-- validation-confirmed -->` を含める
  3. completion-report.md 内に「## 検証」または「## 検証結果」セクションを含める

== サブタスク定義 ==
- index: Sub-{index:03d}
- title: {title}
- depends_on: {depends_on_str}
- labels: {labels_str}

== サブタスク本文 ==
{body}

== 出力先 ==
work/{work_subdir}/

上記を遵守してサブタスクを完遂してください。
"""


def build_subtask_prompt(
    subissue: SubIssueDef,
    parent_step_id: str,
    parent_custom_agent: Optional[str],
    work_subdir: str,
) -> str:
    """サブタスク実行用のプロンプト文字列を構築する。

    Args:
        subissue: 対象サブタスク定義
        parent_step_id: 親 Step ID（例 "2.1"）
        parent_custom_agent: 親 Step の Custom Agent 名
        work_subdir: サブタスクの出力 work ディレクトリ（例
            "Arch-UI-Detail/Issue-screen-detail/sub-001"）

    Returns:
        プロンプト文字列。
    """
    return _SUBTASK_PROMPT_TEMPLATE.format(
        parent_step_id=parent_step_id,
        parent_custom_agent=parent_custom_agent or "(none)",
        index=subissue.index,
        title=subissue.title,
        depends_on_str=", ".join(f"Sub-{d:03d}" for d in subissue.depends_on) or "なし",
        labels_str=", ".join(subissue.labels) or "なし",
        body=subissue.body or "(本文なし)",
        work_subdir=work_subdir,
    )


def make_subtask_work_subdir(
    parent_custom_agent: Optional[str],
    parent_work_identifier: str,
    subissue_index: int,
) -> str:
    """サブタスク用の work ディレクトリ相対パスを生成する。

    Returns:
        Custom Agent あり: "<agent>/Issue-<id>/sub-<NNN>"
        Custom Agent なし: "Issue-<id>/sub-<NNN>"
    """
    sub = f"sub-{subissue_index:03d}"
    issue_part = f"Issue-{parent_work_identifier}"
    if parent_custom_agent:
        return f"{parent_custom_agent}/{issue_part}/{sub}"
    return f"{issue_part}/{sub}"


# ---------------------------------------------------------------------------
# check_subtask_completion
# ---------------------------------------------------------------------------

def check_subtask_completion(
    work_root: Path,
    work_subdir: str,
) -> tuple[bool, str]:
    """サブタスクの完了判定。

    判定基準:
      1. `work/<work_subdir>/completion-report.md` が存在
      2. ファイル内に検証マーカー（`<!-- validation-confirmed -->` 等）が含まれる

    Args:
        work_root: リポジトリルートの `work/` Path
        work_subdir: `make_subtask_work_subdir` の戻り値

    Returns:
        (成功フラグ, 理由文字列)。成功時は理由は "OK"。
    """
    report_path = work_root / work_subdir / "completion-report.md"
    if not report_path.is_file():
        return False, f"completion-report.md が存在しない: {report_path}"

    try:
        content = report_path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"completion-report.md 読み込み失敗: {exc}"

    for pat in _VALIDATION_MARKER_PATTERNS:
        if pat.search(content):
            return True, "OK"

    return False, f"検証マーカーが見つからない: {report_path}"


# ---------------------------------------------------------------------------
# compute_waves — depends_on を解釈して並列実行可能な wave 列に分割
# ---------------------------------------------------------------------------

def compute_waves(subissues: List[SubIssueDef]) -> List[List[SubIssueDef]]:
    """`depends_on` を解釈して topological wave 列に分割する。

    各 wave 内のサブタスクは並列実行可能（互いに依存しない）。
    後の wave のサブタスクは前の wave 群すべての完了を必要とする。

    Args:
        subissues: `parse_subissues_md` の戻り値。index は 1-based。

    Returns:
        wave のリスト。各 wave は SubIssueDef のリスト。元のリストの index 順を保持。

    Raises:
        SubIssuesParseError: depends_on に未知 index・自己参照・循環依存を検出した場合。
    """
    if not subissues:
        return []

    by_index: Dict[int, SubIssueDef] = {s.index: s for s in subissues}
    remaining: Dict[int, set[int]] = {}
    for s in subissues:
        deps = set(s.depends_on)
        if s.index in deps:
            raise SubIssuesParseError(
                f"sub-{s.index:03d}: depends_on に自己参照が含まれています"
            )
        unknown = deps - set(by_index)
        if unknown:
            raise SubIssuesParseError(
                f"sub-{s.index:03d}: depends_on に未知 index: {sorted(unknown)}"
            )
        remaining[s.index] = deps

    waves: List[List[SubIssueDef]] = []
    completed: set[int] = set()
    while remaining:
        ready = [
            by_index[i]
            for i in sorted(remaining.keys())
            if not remaining[i] - completed
        ]
        if not ready:
            raise SubIssuesParseError(
                f"depends_on に循環依存があります: 未解決={sorted(remaining.keys())}"
            )
        waves.append(ready)
        for s in ready:
            completed.add(s.index)
            del remaining[s.index]
    return waves
