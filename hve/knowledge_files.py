"""knowledge_files.py — qa/ と knowledge/ への並行実行に安全なファイル操作（FR-KD-05）。

複数の HVE ジョブ（別プロセス）が同じリポジトリの ``qa/`` と ``knowledge/`` を
同時に作成・更新しても差分を失わないよう、次の 3 つを組み合わせる。

- 対象ごとのプロセス間ロック（``.hve/locks/<hash>.lock`` に OS の排他ロック）
- 呼出し側が読んだ内容の SHA-256 との照合（楽観的な同時実行制御）
- 一時ファイル + ``os.replace`` による原子的な置換
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import re
import socket
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

try:
    from .qa_merger import QAMerger
    from .run_state import _safe_run_id_component
except ImportError:  # pragma: no cover - flat import compatibility
    from qa_merger import QAMerger  # type: ignore[no-redef]
    from run_state import _safe_run_id_component  # type: ignore[no-redef]

PathKind = Literal["qa", "knowledge", "read"]

LOCK_DIR = Path(".hve") / "locks"
LOCK_TIMEOUT_SECONDS = 30.0
_LOCK_INITIAL_DELAY = 0.05
_LOCK_MAX_DELAY = 0.5
_REPLACE_RETRIES = 5
_REPLACE_RETRY_DELAY = 0.1
_RELEASE_RETRY_DELAY = 0.01

KNOWLEDGE_STATUS_FILE = "knowledge/business-requirement-document-status.md"
CHANGELOG_SUFFIX = "-ChangeLog.md"
DISCOVERY_CHANGELOG_HEADING = "## 知識探索による更新履歴"
_DISCOVERY_CHANGELOG_HEADER = "| 日時 (UTC) | 実行 ID | 変更内容の要約 | 出典 |"
_DISCOVERY_CHANGELOG_DELIMITER = "|---|---|---|---|"
QA_SOURCES_SECTION = "調査出典"
_QA_SOURCES_HEADER = "| 出典ID | 種別 | サーバー | ツール | 場所 | 要約 |"
_QA_SOURCES_DELIMITER = "|---|---|---|---|---|---|"
RESEARCH_STATUSES = ("Confirmed", "Tentative", "Unknown")

_KNOWLEDGE_DOC_RE = re.compile(r"^knowledge/D(\d{2})-[^/]+\.md$")
_LABEL_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]")
_SOURCE_ROW_RE = re.compile(r"^\|\s*S(\d+)\s*\|")
_DEFAULT_VALIDATOR = Path(".github") / "scripts" / "validate-knowledge-files.py"

_PROCESS_GUARD = threading.Lock()
_PROCESS_LOCKS: Dict[str, threading.Lock] = {}


class KnowledgeFileError(Exception):
    """FR-KD-05 の理由コード付きエラー。"""

    def __init__(self, code: str, message: str, *, current_sha256: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.current_sha256 = current_sha256

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"ok": False, "code": self.code, "message": self.message}
        if self.code == "conflict":
            payload["current_sha256"] = self.current_sha256
        return payload


@dataclass(frozen=True)
class ResearchAnswer:
    """``hve_qa_answer`` が 1 質問へ書く調査列。"""

    no: int
    answer: str
    status: str
    source_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceEntry:
    """出典（FR-KD-04）。``id`` は呼出し内のローカル ID。"""

    id: str
    kind: str
    server: str
    tool: str
    locator: str
    summary: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def escape_table_cell(text: str) -> str:
    """Markdown 表のセルを 1 物理行に保つ。"""
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    return normalized.replace("|", "&#124;").replace("\n", "<br>")


def utc_timestamp(now: Optional[datetime] = None) -> str:
    moment = now or datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- paths


def normalize_relative_path(raw: object) -> str:
    """``\\`` を ``/`` に読み替え、リポジトリ相対の POSIX パスへ正規化する。"""
    if not isinstance(raw, str):
        raise KnowledgeFileError("path-denied", "パスは文字列で指定してください。")
    value = raw.strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    if not value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise KnowledgeFileError("path-denied", f"リポジトリ相対パスではありません: {raw!r}")
    parts = PurePosixPath(value).parts
    if any(part in ("..", ".", "") for part in parts) or ":" in value:
        raise KnowledgeFileError("path-denied", f"許可されないパス要素を含みます: {raw!r}")
    return "/".join(parts)


def is_qa_path(rel: str) -> bool:
    parts = rel.split("/")
    return len(parts) >= 2 and parts[0] == "qa" and rel.endswith(".md") and bool(parts[-1][:-3])


def is_knowledge_path(rel: str) -> bool:
    if rel == KNOWLEDGE_STATUS_FILE:
        return True
    return bool(_KNOWLEDGE_DOC_RE.match(rel)) and not rel.endswith(CHANGELOG_SUFFIX)


def _check_no_symlink(repo_root: Path, rel: str) -> Path:
    current = repo_root
    for part in rel.split("/"):
        current = current / part
        if current.is_symlink():
            raise KnowledgeFileError("path-denied", f"symlink を含むパスは扱えません: {rel}")
    return current


def resolve_path(repo_root: Path, raw: object, kind: PathKind) -> Tuple[str, Path]:
    """種別ごとの許可規則を適用し ``(相対パス, 絶対パス)`` を返す。"""
    rel = normalize_relative_path(raw)
    allowed = {
        "qa": is_qa_path(rel),
        "knowledge": is_knowledge_path(rel),
        "read": is_qa_path(rel) or is_knowledge_path(rel),
    }[kind]
    if not allowed:
        raise KnowledgeFileError("path-denied", f"このパスは対象外です: {rel}")
    root = Path(repo_root)
    path = _check_no_symlink(root, rel)
    try:
        path.resolve(strict=False).relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise KnowledgeFileError("path-denied", f"リポジトリ外のパスです: {rel}") from exc
    return rel, path


# --------------------------------------------------------------------------- lock


def _try_os_lock(descriptor: int) -> bool:
    """先頭 1 byte に非ブロッキングの排他ロックを掛ける。取得できなければ False。"""
    os.lseek(descriptor, 0, os.SEEK_SET)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            fcntl = __import__("fcntl")
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _os_unlock(descriptor: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        fcntl = __import__("fcntl")
        fcntl.flock(descriptor, fcntl.LOCK_UN)


class FileLock:
    """対象パスごとのプロセス間ロック（OS の排他ロック。異常終了時は OS が解放する）。"""

    def __init__(
        self,
        repo_root: Path,
        rel_path: str,
        *,
        timeout: Optional[float] = None,
    ) -> None:
        key = os.path.normcase(rel_path.replace("\\", "/"))
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]
        self.lock_path = Path(repo_root) / LOCK_DIR / f"{digest}.lock"
        self.timeout = LOCK_TIMEOUT_SECONDS if timeout is None else timeout
        self._token = uuid.uuid4().hex
        self._descriptor: Optional[int] = None
        with _PROCESS_GUARD:
            self._thread_lock = _PROCESS_LOCKS.setdefault(str(self.lock_path), threading.Lock())

    def acquire(self) -> None:
        deadline = time.monotonic() + max(0.0, self.timeout)
        if not self._thread_lock.acquire(timeout=max(0.0, self.timeout)):
            raise KnowledgeFileError("lock-timeout", f"ロックを取得できません: {self.lock_path.name}")
        descriptor: Optional[int] = None
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(
                str(self.lock_path), os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
            )
            delay = _LOCK_INITIAL_DELAY
            while not _try_os_lock(descriptor):
                if time.monotonic() >= deadline:
                    raise KnowledgeFileError(
                        "lock-timeout", f"ロックを取得できません: {self.lock_path.name}"
                    )
                time.sleep(delay)
                delay = min(delay * 2, _LOCK_MAX_DELAY)
            payload = json.dumps(
                {
                    "pid": os.getpid(),
                    "host": socket.gethostname(),
                    "token": self._token,
                    "created_at": utc_timestamp(),
                },
                ensure_ascii=False,
            ).encode("utf-8")
            os.lseek(descriptor, 0, os.SEEK_SET)
            os.write(descriptor, payload)
            os.ftruncate(descriptor, len(payload))
            self._descriptor = descriptor
        except BaseException:
            if descriptor is not None:
                os.close(descriptor)
            self._thread_lock.release()
            raise

    def release(self) -> None:
        descriptor = self._descriptor
        if descriptor is None:
            return
        self._descriptor = None
        try:
            try:
                _os_unlock(descriptor)
            finally:
                os.close(descriptor)
        finally:
            self._thread_lock.release()

    def __enter__(self) -> "FileLock":
        self.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


# --------------------------------------------------------------------------- write


def atomic_write_text(path: Path, text: str) -> None:
    """同じディレクトリの一時ファイルへ書き、``os.replace`` で置き換える。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(_REPLACE_RETRIES):
            try:
                os.replace(str(tmp_path), str(path))
                return
            except PermissionError:
                if attempt == _REPLACE_RETRIES - 1:
                    raise
                time.sleep(_REPLACE_RETRY_DELAY)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def _read_bytes(path: Path) -> Optional[bytes]:
    # Windows では他プロセスの os.replace と重なった読込が一時的に PermissionError になる。
    for attempt in range(_REPLACE_RETRIES * 10):
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None
        except PermissionError:
            if attempt == _REPLACE_RETRIES * 10 - 1:
                raise
            time.sleep(_RELEASE_RETRY_DELAY)
    return None


def _check_base(current: Optional[bytes], base_sha256: Optional[str], rel: str) -> None:
    current_sha = sha256_bytes(current) if current is not None else None
    if base_sha256 is None:
        if current is not None:
            raise KnowledgeFileError(
                "conflict", f"既に存在します。現在の内容を読んでから更新してください: {rel}",
                current_sha256=current_sha,
            )
        return
    if current_sha != str(base_sha256).strip().lower():
        raise KnowledgeFileError(
            "conflict", f"他の書込みで内容が変わりました。読み直してください: {rel}",
            current_sha256=current_sha,
        )


def write_file(
    repo_root: Path,
    raw_path: object,
    text: str,
    *,
    base_sha256: Optional[str],
    kind: PathKind,
) -> str:
    """SHA-256 照合付きで作成・更新し、新しい SHA-256 を返す。"""
    rel, path = resolve_path(repo_root, raw_path, kind)
    with FileLock(repo_root, rel):
        _check_base(_read_bytes(path), base_sha256, rel)
        atomic_write_text(path, text)
    return sha256_text(text)


def replace_file(repo_root: Path, raw_path: object, text: str, *, kind: PathKind) -> str:
    """ロック下で無条件に置き換える（HVE が所有するファイル用）。"""
    rel, path = resolve_path(repo_root, raw_path, kind)
    with FileLock(repo_root, rel):
        atomic_write_text(path, text)
    return sha256_text(text)


def read_file(repo_root: Path, raw_path: object) -> Dict[str, Any]:
    rel, path = resolve_path(repo_root, raw_path, "read")
    data = _read_bytes(path)
    if data is None:
        return {"path": rel, "exists": False, "sha256": None, "content": ""}
    return {
        "path": rel,
        "exists": True,
        "sha256": sha256_bytes(data),
        "content": data.decode("utf-8", errors="replace"),
    }


# --------------------------------------------------------------------------- QA


def _safe_component(value: object, limit: int = 0) -> str:
    cleaned = _LABEL_UNSAFE_RE.sub("-", str(value or "").strip()) or "x"
    return cleaned[:limit] if limit else cleaned


def _qa_run_id_component(run_id: object) -> str:
    """run_id は共通規則（``run_state``）で無害化し、空になれば ``unknown`` とする。"""
    try:
        return _safe_run_id_component(str(run_id or ""))
    except ValueError:
        return "unknown"


def create_qa_document(repo_root: Path, *, run_id: str, label: str, text: str) -> Tuple[str, str]:
    """``qa/<run_id>-<label>-knowledge-discovery-qa[-N].md`` を排他的に作成する。"""
    stem = f"{_qa_run_id_component(run_id)}-{_safe_component(label, 40)}-knowledge-discovery-qa"
    for number in [None, *range(2, 100)]:
        rel = f"qa/{stem}.md" if number is None else f"qa/{stem}-{number}.md"
        try:
            return rel, write_file(repo_root, rel, text, base_sha256=None, kind="qa")
        except KnowledgeFileError as exc:
            if exc.code != "conflict":
                raise
    raise KnowledgeFileError("exists", f"QA ファイル名の連番が上限に達しました: qa/{stem}-99.md")


def _rebuild_sources_section(section: str, rows: List[str]) -> str:
    body = section.strip()
    if not rows:
        return body
    if not body:
        return "\n".join([_QA_SOURCES_HEADER, _QA_SOURCES_DELIMITER, *rows])
    return body + "\n" + "\n".join(rows)


def update_qa_research(
    repo_root: Path,
    raw_path: object,
    *,
    base_sha256: Optional[str],
    answers: Sequence[ResearchAnswer],
    sources: Sequence[SourceEntry],
) -> Dict[str, Any]:
    """指定した質問の調査列だけを更新し、出典をファイル内の ``S<n>`` へ振り直す。"""
    rel, path = resolve_path(repo_root, raw_path, "qa")
    for answer in answers:
        if answer.status not in RESEARCH_STATUSES:
            raise KnowledgeFileError(
                "invalid-answer", f"調査状態は {', '.join(RESEARCH_STATUSES)} のいずれかです: Q{answer.no}"
            )
    with FileLock(repo_root, rel):
        current = _read_bytes(path)
        if current is None:
            raise KnowledgeFileError("not-found", f"QA ファイルがありません: {rel}")
        _check_base(current, base_sha256, rel)
        doc = copy.deepcopy(QAMerger.parse_qa_content(current.decode("utf-8")))
        by_no = {q.no: q for q in doc.questions}
        unknown = sorted({a.no for a in answers if a.no not in by_no})
        if unknown:
            raise KnowledgeFileError(
                "invalid-question", "表に無い質問番号です: " + ", ".join(f"Q{n}" for n in unknown)
            )
        section = doc.raw_sections.get(QA_SOURCES_SECTION, "")
        used = [
            int(match.group(1))
            for line in section.splitlines()
            if (match := _SOURCE_ROW_RE.match(line.strip()))
        ]
        next_id = max(used, default=0) + 1
        id_map: Dict[str, str] = {}
        rows: List[str] = []
        for source in sources:
            if source.id in id_map:
                continue
            id_map[source.id] = f"S{next_id}"
            next_id += 1
            cells = (id_map[source.id], source.kind, source.server, source.tool, source.locator, source.summary)
            rows.append("| " + " | ".join(escape_table_cell(cell) for cell in cells) + " |")
        for answer in answers:
            missing = [sid for sid in answer.source_ids if sid not in id_map]
            if missing:
                raise KnowledgeFileError(
                    "unknown-source-id", f"Q{answer.no} が未定義の出典 ID を引用しています: {', '.join(missing)}"
                )
            question = by_no[answer.no]
            question.research_answer = answer.answer.strip()
            question.research_status = answer.status
            question.research_sources = ", ".join(id_map[sid] for sid in dict.fromkeys(answer.source_ids))
        doc.raw_sections[QA_SOURCES_SECTION] = _rebuild_sources_section(section, rows)
        rendered = QAMerger.render_merged(doc)
        atomic_write_text(path, rendered)
    return {
        "ok": True,
        "path": rel,
        "sha256": sha256_text(rendered),
        "updated": sorted({a.no for a in answers}),
        "source_id_map": id_map,
    }


def save_qa_text(path: Path, text: str, *, repo_root: Optional[Path] = None) -> None:
    """HVE が所有する QA ファイルをロック下で原子的に置き換える（FR-QA-03 / FR-KD-05）。

    リポジトリ内の ``qa/`` 配下は FR-KD-05 のパス規則を適用する。それ以外の明示パス
    （呼出し側が指定した出力先）は同じロックと原子的置換だけを適用する。
    """
    root = Path(repo_root or Path.cwd())
    target = Path(path)
    absolute = target if target.is_absolute() else root / target
    try:
        rel = absolute.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        rel = None
    if rel is not None and is_qa_path(rel):
        replace_file(root, rel, text, kind="qa")
        return
    with FileLock(root, os.path.normcase(str(absolute.resolve()))):
        atomic_write_text(absolute, text)


# --------------------------------------------------------------------------- knowledge

_VALIDATOR_CACHE: Dict[str, Any] = {}


def _load_validator(validator_path: Path) -> Any:
    key = str(validator_path.resolve())
    if key not in _VALIDATOR_CACHE:
        spec = importlib.util.spec_from_file_location("hve_validate_knowledge_files", validator_path)
        if spec is None or spec.loader is None:
            raise ImportError(str(validator_path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _VALIDATOR_CACHE[key] = module
    return _VALIDATOR_CACHE[key]


def validate_knowledge_document(
    rel: str, content: str, *, validator_path: Path
) -> List[str]:
    """D 文書の見出しと FR-WF-AKM-01 の本文 schema を検査する。"""
    match = _KNOWLEDGE_DOC_RE.match(rel)
    if match is None:
        return []
    first = next((line.strip() for line in content.splitlines() if line.strip()), "")
    errors: List[str] = []
    if not first.startswith(f"# D{match.group(1)}:"):
        errors.append(f"最初の行は `# D{match.group(1)}:` で始めてください。")
    try:
        validator = _load_validator(validator_path)
        errors.extend(validator._validate_main(content))
    except Exception:
        errors.append("FR-WF-AKM-01 の検証器を読み込めないため書き込みません。")
    return errors


def build_changelog_skeleton(doc_rel: str, now: Optional[datetime] = None) -> str:
    """FR-WF-AKM-01 の ChangeLog schema を満たす最小の雛形。"""
    match = _KNOWLEDGE_DOC_RE.match(doc_rel)
    number = match.group(1) if match else "00"
    name = Path(doc_rel).stem.split("-", 1)[-1]
    stamp = utc_timestamp(now)
    return "\n".join([
        "<!-- sources: [] -->",
        f"<!-- generated_at: {stamp} -->",
        "<!-- generator: hve-knowledge-discovery -->",
        "",
        f"# D{number} 変更ログ: {name}",
        "",
        f"**対象ファイル**: `{doc_rel}`",
        "**カバー率（REQ単位）**: 未算出",
        f"**最終更新**: {stamp[:10]}",
        "**更新エージェント**: hve-knowledge-discovery",
        "**入力ソース**: 知識探索（FR-KD-07）",
        "",
        "---",
        "",
        "## 全体更新履歴",
        "",
        "| 日時 (UTC) | 更新エージェント | イベント種別 | 変更内容の要約 | REQ 件数（Confirmed/Tentative） | カバー率 |",
        "|---|---|---|---|---|---|",
        "",
        "## 要求項目別ログ",
        "",
        "該当 REQ なし。",
        "",
        "## 付録 A: マッピング詳細",
        "",
        "なし。",
        "",
    ])


def _insert_changelog_row(text: str, row: str) -> str:
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)
    try:
        heading = next(i for i, line in enumerate(lines) if line.strip() == DISCOVERY_CHANGELOG_HEADING)
    except StopIteration:
        while lines and not lines[-1].strip():
            lines.pop()
        lines.extend(["", DISCOVERY_CHANGELOG_HEADING, "", _DISCOVERY_CHANGELOG_HEADER,
                      _DISCOVERY_CHANGELOG_DELIMITER, row, ""])
        return newline.join(lines)
    index = heading + 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index < len(lines) and lines[index].lstrip().startswith("|"):
        while index < len(lines) and lines[index].lstrip().startswith("|"):
            index += 1
        lines.insert(index, row)
    else:
        lines[heading + 1:heading + 1] = ["", _DISCOVERY_CHANGELOG_HEADER, _DISCOVERY_CHANGELOG_DELIMITER, row]
    return newline.join(lines)


def append_discovery_changelog(
    repo_root: Path,
    doc_rel: str,
    *,
    run_id: str,
    summary: str,
    locators: Sequence[str],
    now: Optional[datetime] = None,
) -> str:
    changelog_rel = doc_rel[: -len(".md")] + CHANGELOG_SUFFIX
    path = _check_no_symlink(Path(repo_root), changelog_rel)
    row = "| " + " | ".join([
        utc_timestamp(now),
        escape_table_cell(run_id),
        escape_table_cell(summary),
        "<br>".join(escape_table_cell(locator) for locator in locators),
    ]) + " |"
    with FileLock(repo_root, changelog_rel):
        current = _read_bytes(path)
        text = current.decode("utf-8") if current is not None else build_changelog_skeleton(doc_rel, now)
        atomic_write_text(path, _insert_changelog_row(text, row))
    return changelog_rel


def write_knowledge(
    repo_root: Path,
    raw_path: object,
    content: str,
    *,
    base_sha256: Optional[str],
    run_id: str,
    summary: str,
    locators: Sequence[str],
    validator_path: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """D 文書または status ファイルを書き、D 文書なら ChangeLog へ 1 行追記する。"""
    root = Path(repo_root)
    rel, path = resolve_path(root, raw_path, "knowledge")
    if not str(content).strip():
        raise KnowledgeFileError("invalid-content", "本文が空です。")
    if not locators:
        raise KnowledgeFileError("invalid-content", "検証済みの出典が 1 件以上必要です。")
    if rel != KNOWLEDGE_STATUS_FILE:
        errors = validate_knowledge_document(
            rel, content, validator_path=validator_path or (root / _DEFAULT_VALIDATOR)
        )
        if errors:
            raise KnowledgeFileError("invalid-content", " / ".join(errors))
    with FileLock(root, rel):
        _check_base(_read_bytes(path), base_sha256, rel)
        atomic_write_text(path, content)
    changelog = None
    if rel != KNOWLEDGE_STATUS_FILE:
        changelog = append_discovery_changelog(
            root, rel, run_id=run_id, summary=summary, locators=locators, now=now
        )
    return {"ok": True, "path": rel, "sha256": sha256_text(content), "changelog_path": changelog}
