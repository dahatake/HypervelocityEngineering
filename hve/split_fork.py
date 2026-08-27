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
import os

try:
    from .prompt_loader import load_prompt_file
except ImportError:  # pragma: no cover - top-level / standalone-file compatibility
    # `.github/scripts/check_validation_marker.py` は本モジュールを単独ファイルとして
    # ロードするため、パッケージ未初期化でも兄弟モジュールを解決できるようにする。
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from prompt_loader import load_prompt_file  # type: ignore[import-not-found,no-redef]


# ---------------------------------------------------------------------------
# run-id / work_root 解決
# ---------------------------------------------------------------------------

WORK_DIRNAME = "work"
WORK_RUN_DIRNAME = "run"

# プロセス内で 1 度だけ採番した run-id をキャッシュする。
# env / Cloud 検出が無いときに `resolve_run_id()` を複数回呼んでも
# 同じ ID を返すことを保証する。
_RESOLVED_RUN_ID: Optional[str] = None


def _detect_cloud_run_id() -> Optional[str]:
    """GitHub Issue 起動時に ``"issue-<N>"`` を返す。それ以外は None。

    検出順:
      1. 環境変数 ``GITHUB_ISSUE_NUMBER``
      2. ``GITHUB_EVENT_PATH`` JSON 内の ``issue.number``
    """
    issue_num = os.environ.get("GITHUB_ISSUE_NUMBER", "").strip()
    if issue_num.isdigit():
        return f"issue-{issue_num}"
    event_path = os.environ.get("GITHUB_EVENT_PATH", "").strip()
    if event_path and os.path.isfile(event_path):
        try:
            import json
            with open(event_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            issue = data.get("issue") or {}
            num = issue.get("number")
            if isinstance(num, int) and num > 0:
                return f"issue-{num}"
        except (OSError, ValueError, TypeError):
            return None
    return None


def resolve_run_id() -> str:
    """`work/run/<run-id>/` の ``<run-id>`` を解決する。

    解決順序（先勝ち）:
      1. 環境変数 ``HVE_RUN_ID``（明示指定）
      2. GitHub Issue 起動検出 → ``"issue-<N>"``
      3. ``generate_run_id()`` で新規採番（プロセス内キャッシュ）

    プロセス内では 1 度だけ採番し、以降は同じ ID を返す。
    """
    global _RESOLVED_RUN_ID
    env_id = os.environ.get("HVE_RUN_ID", "").strip()
    if env_id:
        return env_id
    cloud_id = _detect_cloud_run_id()
    if cloud_id:
        return cloud_id
    if _RESOLVED_RUN_ID is None:
        try:
            from hve.config import generate_run_id
        except ImportError:  # pragma: no cover - script execution path
            from config import generate_run_id  # type: ignore[import-not-found,no-redef]
        _RESOLVED_RUN_ID = generate_run_id()
    return _RESOLVED_RUN_ID


def _reset_run_id_cache() -> None:
    """テスト専用: ``_RESOLVED_RUN_ID`` キャッシュをクリアする。"""
    global _RESOLVED_RUN_ID
    _RESOLVED_RUN_ID = None


def resolve_work_root() -> Path:
    """`work/run/<run-id>/` ディレクトリの絶対 Path を返す。

    解決順序（先勝ち）:
      1. 環境変数 ``HVE_WORK_ROOT`` が設定されていればその値
         （GUI/CLI 起動時に親プロセスが設定した値を子プロセスが継承、
          テストでの override 用途も兼ねる）
    2. ``<repo_root>/work/run/<run-id>/``
         （``<repo_root>`` = ``Path(__file__).resolve().parents[1]``、
          ``<run-id>`` は ``resolve_run_id()`` の結果）

    cwd 依存を排除するための関数。存在しないディレクトリでも Path は返す
    （呼び出し側で `is_dir()` を判定すること）。
    """
    override = os.environ.get("HVE_WORK_ROOT")
    if override:
        return Path(override).resolve()
    return (
        Path(__file__).resolve().parents[1]
        / WORK_DIRNAME
        / WORK_RUN_DIRNAME
        / resolve_run_id()
    ).resolve()


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


def has_validation_marker(text: str, *, html_comment_only: bool = False) -> bool:
    """完了報告の検証マーカー判定の単一実装（FR-MAINT-06）。

    Args:
        text: 検査対象の本文。
        html_comment_only: True のとき HTML コメント形式だけを受理する。
            TDD レポートは template が `<!-- validation-confirmed -->` を出力するため
            厳格化し、PR body / completion-report は 3 形式を許容する。
    """
    patterns = _VALIDATION_MARKER_PATTERNS[:1] if html_comment_only else _VALIDATION_MARKER_PATTERNS
    return any(pattern.search(text) for pattern in patterns)

_PLACEHOLDER_PATTERN = re.compile(r"REPLACE_ME", re.IGNORECASE)


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DiscoverResult:
    """`discover_subissues_md_verbose` の戻り値。観測性のためのメタ情報を含む。

    Attributes:
        path: 採用された subissues.md の Path。見つからなければ None。
        matched_pattern: マッチに用いた探索パターンの識別子。
            "agent-scoped" / "issue-only" / "fallback-glob" / None（未検出）。
        candidates_examined: 探索中に検出された候補数（重複排除前）。
    """
    path: Optional[Path]
    matched_pattern: Optional[str]
    candidates_examined: int


# `.failed-` を親ディレクトリ名に含むエントリは過去のパース失敗退避先のため、
# 探索段階で常に除外する（再採用による無限ループ・誤検出の防止）。
_FAILED_DIR_MARKER = ".failed-"

# `Issue-*` ディレクトリ名から step 識別子を取り出す正規表現キャッシュ。
_STEP_SUFFIX_RE_CACHE: "Dict[str, re.Pattern[str]]" = {}


def _compile_step_suffix_re(step_id: str) -> "re.Pattern[str]":
    """`step-<step_id>` の語境界付き一致用パターンを取得（キャッシュ付き）。

    Issue ディレクトリ名は `-` 区切り（例: `Issue-<run>-step-<id>`）のため、
    "step-" の前は **文字列先頭またはハイフン** を境界とする。
    "step-<id>" の直後は **文字列末尾または非数字非ハイフン**（数字や `-` が続くと
    別の step_id へ連結している可能性があるため）を境界とする。

    例: step_id="1" のとき
      - `Issue-...-step-1`        → 一致 ✓
      - `Issue-...-step-1.failed` → 一致 ✓
      - `Issue-...-step-1-2`      → 不一致
      - `Issue-...-step-12`       → 不一致

    step_id="2.1" のとき
      - `Issue-...-step-2.1`        → 一致 ✓
      - `Issue-...-step-2.1.failed` → 一致 ✓
    """
    cached = _STEP_SUFFIX_RE_CACHE.get(step_id)
    if cached is not None:
        return cached
    pat = re.compile(rf"(?:^|-)step-{re.escape(step_id)}(?:$|[^0-9-])")
    _STEP_SUFFIX_RE_CACHE[step_id] = pat
    return pat


def _passes_run_scope(parent_dir_name: str, run_id: Optional[str]) -> bool:
    """親 `Issue-*` ディレクトリ名が現在 run のスコープに合致するかを判定する。

    - `run_id` が None / 空文字なら常に True（後方互換）。
    - そうでなければ、ディレクトリ名に `run_id` を部分一致で含む場合のみ True。
      Issue-* ディレクトリ名は実運用上 `Issue-<run_id>-step-<id>` 形式または
      `Issue-hve-<run_id>-step-<id>` 形式を取るため、部分一致で安全に絞れる。
      ただし `run_id` は十分長い識別子（タイムスタンプ + ハッシュ）である前提。
    """
    if not run_id:
        return True
    return run_id in parent_dir_name


def _passes_step_scope(parent_dir_name: str, step_id: Optional[str]) -> bool:
    """親 `Issue-*` ディレクトリ名が現在 step のスコープに合致するかを判定する。

    - `step_id` が None / 空文字なら常に True（後方互換）。
    - ディレクトリ名に `step-` トークン自体が含まれない場合は常に True
      （Web UI 方式の `Issue-<番号>` 形式に対する互換性。これらの命名では
      step_id 情報が dir 名に埋め込まれない仕様のため、フィルタを無効化する）。
    - `step-` トークンが含まれる場合のみ、`step-<step_id>` の語境界付き一致で
      ふるい分ける（短い step_id "1" が `step-12` に誤一致するのを防ぐ）。
    """
    if not step_id:
        return True
    if "step-" not in parent_dir_name:
        return True
    return bool(_compile_step_suffix_re(step_id).search(parent_dir_name))


# ---------------------------------------------------------------------------
# 公開 API: 他モジュール（runner.py 等）から利用するスコープ判定ヘルパ。
# アンダースコア接頭辞の私的 API を直接 import せずに済むよう、同じ動作の
# 公開名を提供する（API 境界の明確化）。
# ---------------------------------------------------------------------------

FAILED_DIR_MARKER: str = _FAILED_DIR_MARKER


def matches_run_scope(parent_dir_name: str, run_id: Optional[str]) -> bool:
    """`_passes_run_scope` の公開版。詳細は `_passes_run_scope` を参照。"""
    return _passes_run_scope(parent_dir_name, run_id)


def matches_step_scope(parent_dir_name: str, step_id: Optional[str]) -> bool:
    """`_passes_step_scope` の公開版。詳細は `_passes_step_scope` を参照。"""
    return _passes_step_scope(parent_dir_name, step_id)


def is_failed_dir(parent_dir_name: str) -> bool:
    """親 `Issue-*` ディレクトリ名が `.failed-*` 退避先かを判定する公開ヘルパ。"""
    return FAILED_DIR_MARKER in parent_dir_name


def work_root_contains_run_id(work_root: Path, run_id: Optional[str]) -> bool:
    """work_root のパスセグメントに `run_id` が完全一致で含まれるかを判定する。

    `work/run/<run-id>/` 形式の run-scoped work_root では、ディレクトリ構造
    自体で run-id 隔離が成立しているため、追加の `parent.name` フィルタ
    （`_passes_run_scope`）は過剰となり、`Issue-0` 形式の正当な subissues.md
    を誤除外する原因になる。本ヘルパは「フィルタ skip 可否」の判定に使う。

    - `str(work_root)` の単純な部分一致では `<run-id>-old` のような紛らわしい
      祖先名や、偶然 run_id 文字列を含む親パスでも True を返してしまうため、
      必ず `Path.parts` でセグメント完全一致を取る。
    - symlink / junction で `.../work/run/<run-id>` を指している場合に resolve
      後の実体パスから run_id セグメントが消えるケースがあるため、lexical /
      resolved の両方を見る。
    """
    if not run_id:
        return False
    try:
        lexical_parts = Path(work_root).parts
    except (OSError, ValueError):
        lexical_parts = ()
    if run_id in lexical_parts:
        return True
    try:
        resolved_parts = Path(work_root).resolve().parts
    except (OSError, ValueError):
        return False
    return run_id in resolved_parts


def discover_subissues_md_verbose(
    work_root: Path,
    custom_agent: Optional[str],
    parent_step_id: str,
    *,
    run_id: Optional[str] = None,
    step_id: Optional[str] = None,
) -> DiscoverResult:
    """探索結果を観測メタ付きで返す詳細版。`discover_subissues_md` の実装本体。

    探索順序（先勝ちではなく全候補収集 → mtime 最新で選定）:
      1. work/<custom_agent>/Issue-*/subissues.md   （"agent-scoped"）
      2. work/Issue-*/subissues.md                  （"issue-only"）
      3. work/*/Issue-*/subissues.md                （フォールバック, "fallback-glob"）

    フィルタ:
      - 親 `Issue-*` ディレクトリ名に `.failed-` を含む候補は常に除外する。
      - `run_id` 指定時は親ディレクトリ名による部分一致絞り込みを行う。
      - `step_id` 指定時は `step-<step_id>` の語境界付き一致で絞り込む。
        ただし dir 名に `step-` トークンが無い場合は無効化（Web UI 方式互換）。

    Args:
        work_root: 探索ルート（絶対 Path 推奨）。
        custom_agent: 親 Step の Custom Agent 名。None / 空文字なら 1 をスキップ。
        parent_step_id: 親 Step ID（ログ用予約。本実装では未使用）。
        run_id: 現在 run の識別子（既定 None=後方互換）。
        step_id: 現在 Step ID（既定 None=後方互換）。
    """
    del parent_step_id  # 将来のログ拡張用予約引数

    tagged: List[tuple[Path, str]] = []

    if custom_agent:
        agent_dir = work_root / custom_agent
        if agent_dir.is_dir():
            for p in agent_dir.glob("Issue-*/subissues.md"):
                tagged.append((p, "agent-scoped"))

    if work_root.is_dir():
        for p in work_root.glob("Issue-*/subissues.md"):
            tagged.append((p, "issue-only"))

        # フォールバック: custom_agent が None/不一致の場合の救済探索。
        # 注: runner.py 側の `_step_declared_split_required` は custom_agent
        # 指定時に agent-scoped のみ走査するため、本番動線で fallback-glob が
        # 別 Agent の subissues.md を選定する経路は基本的に発火しない。
        # 直接 `discover_subissues_md_verbose` を呼ぶテスト・将来の custom_agent
        # 未指定ユースケースのために残置している。
        for p in work_root.glob("*/Issue-*/subissues.md"):
            tagged.append((p, "fallback-glob"))

    existing = [(p, tag) for (p, tag) in tagged if p.is_file()]

    # `.failed-*` 退避ディレクトリ配下を常に除外する。
    existing = [
        (p, tag) for (p, tag) in existing
        if _FAILED_DIR_MARKER not in p.parent.name
    ]

    # `run_id` 指定時は親ディレクトリ名のスコープでさらに絞り込む。
    # ただし `work_root` 自体のパスセグメントに `run_id` が完全一致で含まれる
    # （= `work/run/<run-id>/` 形式の run-scoped work_root）場合は、
    # work_root スコープだけで run-id 隔離が既に成立している。この場合の
    # 追加 parent.name フィルタは過剰となり、`Issue-0` 形式の正当な
    # subissues.md を誤除外するため、フィルタを skip する。
    if run_id and not work_root_contains_run_id(work_root, run_id):
        existing = [
            (p, tag) for (p, tag) in existing
            if _passes_run_scope(p.parent.name, run_id)
        ]

    # `step_id` 指定時は親ディレクトリ名の step スコープで絞り込む。
    if step_id:
        existing = [
            (p, tag) for (p, tag) in existing
            if _passes_step_scope(p.parent.name, step_id)
        ]

    if not existing:
        return DiscoverResult(path=None, matched_pattern=None, candidates_examined=0)

    seen: Dict[Path, str] = {}
    for p, tag in existing:
        if p not in seen:
            seen[p] = tag

    if custom_agent:
        agent_scoped_paths = {p for p, tag in seen.items() if tag == "agent-scoped"}
        if agent_scoped_paths:
            seen = {p: tag for p, tag in seen.items() if p in agent_scoped_paths}

    chosen = max(seen.keys(), key=lambda p: p.stat().st_mtime)
    return DiscoverResult(
        path=chosen,
        matched_pattern=seen[chosen],
        candidates_examined=len(seen),
    )


def discover_subissues_md(
    work_root: Path,
    custom_agent: Optional[str],
    parent_step_id: str,
    *,
    run_id: Optional[str] = None,
    step_id: Optional[str] = None,
) -> Optional[Path]:
    """親 Step の Agent が SPLIT_REQUIRED 時に出力した subissues.md を探索する。

    詳細は `discover_subissues_md_verbose` を参照。

    Args:
        work_root: リポジトリルートの `work/` ディレクトリ Path
        custom_agent: 親 Step の Custom Agent 名（None 可）。
        parent_step_id: 親 Step ID（ログ用）。
        run_id: 現在 run の識別子（既定 None=後方互換）。
        step_id: 現在 Step ID（既定 None=後方互換）。

    Returns:
        見つかった subissues.md の Path。見つからなければ None。
    """
    return discover_subissues_md_verbose(
        work_root=work_root,
        custom_agent=custom_agent,
        parent_step_id=parent_step_id,
        run_id=run_id,
        step_id=step_id,
    ).path


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------

_SUBISSUE_MARKER = "<!-- subissue -->"
_TITLE_RE = re.compile(r"<!--\s*title:\s*(.*?)\s*-->", re.IGNORECASE)
_LABELS_RE = re.compile(r"<!--\s*labels:\s*(.*?)\s*-->", re.IGNORECASE)
_CUSTOM_AGENT_RE = re.compile(r"<!--\s*custom_agent:\s*(.*?)\s*-->", re.IGNORECASE)
_DEPENDS_ON_RE = re.compile(r"<!--\s*depends_on:\s*(.*?)\s*-->", re.IGNORECASE)
_H2_RE = re.compile(r"^\s*##\s+(.+?)\s*$", re.MULTILINE)

# P-A: Markdown テーブル行（先頭・末尾が `|`）の連続検出用。
# `<!-- subissue -->` マーカーが 0 件のとき、Agent がテーブル形式で subissues.md を
# 生成したかを判定するために使用する。
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_MIN_CONSECUTIVE_ROWS = 3


def _detect_table_format(text: str) -> bool:
    """本文中に Markdown テーブル行が `_TABLE_MIN_CONSECUTIVE_ROWS` 行以上
    連続している箇所があれば True を返す。

    `<!-- subissue -->` マーカーが 0 件のとき、Agent がテーブル形式で
    subissues.md を生成したかを判定するために使用する。
    """
    consecutive = 0
    for line in text.split("\n"):
        if _TABLE_ROW_RE.match(line):
            consecutive += 1
            if consecutive >= _TABLE_MIN_CONSECUTIVE_ROWS:
                return True
        else:
            consecutive = 0
    return False


def _preflight_subissues(path: Path, blocks: List[str]) -> None:
    """全ブロックを走査して `<!-- title: ... -->` 欠落を一括検出する。

    1 ブロックでも欠落していれば、欠落ブロック全件と各ブロックの H2 見出し
    （修正候補のヒント）を含む詳細メッセージで `SubIssuesParseError` を送出する。

    エラーメッセージは下記既存テストとの互換のため、先頭に
    "`<!-- title: ... -->` が見つかりません" の語を含む。
      - `test_missing_title_raises`: `match="title.*見つかりません"`
    """
    missing: List[tuple[int, Optional[str]]] = []
    for idx, block in enumerate(blocks, start=1):
        if _TITLE_RE.search(block):
            continue
        m_h2 = _H2_RE.search(block)
        h2_text = m_h2.group(1).strip() if m_h2 else None
        missing.append((idx, h2_text))

    if not missing:
        return

    nums = ",".join(str(i) for i, _ in missing)
    lines: List[str] = [
        f"`<!-- title: ... -->` が見つかりません (subissues.md 検証失敗: {path})",
        f"  - 欠落ブロック: [{nums}]",
        "  - 検出された H2 見出し（修正候補のヒント）:",
    ]
    for i, h2 in missing:
        if h2:
            lines.append(f"      ブロック {i}: {h2!r}")
        else:
            lines.append(f"      ブロック {i}: （H2 見出しも未検出）")
    lines.extend([
        "  修正方法: 各 <!-- subissue --> 行の直下に下記 HTML コメントメタを追加してください。",
        "  最小サンプル（1 ブロック分）:",
        "    <!-- subissue -->",
        "    <!-- title: Sub-1 のタイトル -->",
        "    <!-- custom_agent: <Agent 名> -->",
        "    <!-- depends_on: -->",
        "    ## Sub-1: Sub-1 のタイトル",
        "    - 対象: ...",
        "    - AC: ...",
        "  テンプレート: .github/skills/task-dag-planning/references/subissues-template.md",
        "  規約: .github/skills/task-dag-planning/SKILL.md §subissues.md 作成規約",
        "  検証 (bash):       bash .github/scripts/bash/validate-subissues.sh --path <該当パス>",
        "  検証 (PowerShell): pwsh -NoProfile -File .github/scripts/powershell/validate-subissues.ps1 -Path <該当パス>",
    ])
    raise SubIssuesParseError("\n".join(lines))


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
        # P-A: テーブル形式（`| ... |` が連続）で書かれているケースを検知して
        # actionable な修正サンプル付きエラーを返す。Agent が `task-dag-planning`
        # Skill を読まずに自己流のテーブル形式で出力する事例が観測されている。
        if _detect_table_format(text):
            sample_lines = [
                f"`{_SUBISSUE_MARKER}` ブロックが 0 件 だが Markdown テーブル形式が検出されました: {path}",
                "  → テーブル形式は禁止です。各行を以下の HTML コメントブロック形式に展開してください:",
                "",
                "    <!-- parent_issue: <番号 or TBD> -->",
                "",
                "    <!-- subissue -->",
                "    <!-- title: <タイトル> -->",
                "    <!-- custom_agent: <Agent 名> -->",
                "    <!-- depends_on: <番号カンマ区切り or 空> -->",
                "    ## Sub-1",
                "    - 対象: ...",
                "    - AC: ...",
                "",
                "  規約: .github/skills/task-dag-planning/references/subissues-template.md",
                "  検証 (bash):       bash .github/scripts/bash/validate-subissues.sh --path <該当パス>",
                "  検証 (PowerShell): pwsh -NoProfile -File .github/scripts/powershell/validate-subissues.ps1 -Path <該当パス>",
            ]
            raise SubIssuesParseError("\n".join(sample_lines))
        raise SubIssuesParseError(
            f"`{_SUBISSUE_MARKER}` ブロックが 0 件: {path}"
        )

    blocks = chunks[1:]  # ヘッダ部を除く

    # Pre-flight: 全ブロックの title 欠落を一括検出して詳細メッセージで早期失敗させる。
    # Agent 側の self-validation (`validate-subissues.sh`) 漏れを Orchestrator が補完する。
    _preflight_subissues(path, blocks)

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

_SUBTASK_PROMPT_TEMPLATE = load_prompt_file("runtime/fleet/subtask.prompt.md")


def build_subtask_prompt(
    subissue: SubIssueDef,
    parent_step_id: str,
    parent_custom_agent: Optional[str],
    work_subdir: str,
    repo_root: Optional[Path] = None,
    work_root: Optional[Path] = None,
) -> str:
    """サブタスク実行用のプロンプト文字列を構築する。

    Args:
        subissue: 対象サブタスク定義
        parent_step_id: 親 Step ID（例 "2.1"）
        parent_custom_agent: 親 Step の Custom Agent 名
        work_subdir: サブタスクの出力 work_root 相対ディレクトリ。
            例 "Arch-UI-Detail/Issue-screen-detail/sub-001"
        repo_root: リポジトリルートの絶対パス。指定時はプロンプトに絶対パスで
            正規出力先を埋め込む。未指定時は `Path.cwd()` を使用する。
        work_root: `resolve_work_root()` 済みの出力ルート。未指定時は
            `repo_root / "work" / "run" / "unknown-run"` を安全側 fallback とする。

    Returns:
        プロンプト文字列。
    """
    if repo_root is None:
        repo_root = Path.cwd()
    effective_work_root = (
        Path(work_root).resolve()
        if work_root is not None
        else (repo_root / WORK_DIRNAME / WORK_RUN_DIRNAME / "unknown-run").resolve()
    )
    abs_output_path = (effective_work_root / work_subdir).resolve()
    abs_output_dir = abs_output_path.as_posix() + "/"
    try:
        rel_output_dir = abs_output_path.relative_to(repo_root.resolve()).as_posix() + "/"
    except ValueError:
        rel_output_dir = abs_output_dir
    return _SUBTASK_PROMPT_TEMPLATE.format(
        parent_step_id=parent_step_id,
        parent_custom_agent=parent_custom_agent or "(none)",
        index=subissue.index,
        title=subissue.title,
        depends_on_str=", ".join(f"Sub-{d:03d}" for d in subissue.depends_on) or "なし",
        labels_str=", ".join(subissue.labels) or "なし",
        body=subissue.body or "(本文なし)",
        work_subdir=work_subdir,
        repo_root=repo_root.as_posix(),
        abs_output_dir=abs_output_dir,
        rel_output_dir=rel_output_dir,
    )


def make_subtask_work_subdir(
    parent_custom_agent: Optional[str],
    parent_work_identifier: str,
    subissue_index: int,
) -> str:
    """サブタスク用の work ディレクトリ相対パスを生成する。

    返り値はリポジトリ直下の `work/` からの相対パス。完全な格納先は
    `<repo>/work/<返り値>/`。

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
        # 誤書き込み検知: 同じリポジトリ内の別 work/ ディレクトリ（特に hve/work/）に
        # 同名 completion-report.md が存在する場合、LLM が相対パスを誤解決して
        # 別の work/ ディレクトリへ出力した可能性が高い。診断情報として付加する。
        #
        # 注: work_root.name == "work" の場合のみ repo_root を推定する。これ以外の
        # ケース（テスト等で任意の tmp_path を渡した場合）は推定をスキップする。
        misplaced_hints: List[str] = []
        try:
            if work_root.name == "work":
                repo_root = work_root.parent
                candidate = repo_root / "hve" / "work" / work_subdir / "completion-report.md"
                if candidate.is_file():
                    misplaced_hints.append(str(candidate))
        except (OSError, ValueError):  # pragma: no cover - 診断補助
            pass

        msg = f"completion-report.md が存在しない: {report_path}"
        if misplaced_hints:
            msg += (
                " [MISPLACED] 誤書き込みの可能性: "
                + ", ".join(misplaced_hints)
                + " （正規パスは <repo>/work/... です。`hve/work/...` ではありません）"
            )
        return False, msg

    try:
        content = report_path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"completion-report.md 読み込み失敗: {exc}"

    if has_validation_marker(content):
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
