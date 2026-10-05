"""knowledge_discovery.py — 知識探索エージェント（FR-KD-01〜FR-KD-09）。

目的だけを与えた 1 つの SDK セッションに、読み取り専用の知識源（MCP）と
``qa/`` / ``knowledge/`` への安全な書込み tool（FR-KD-05）を渡し、
問い合わせの計画・回数・順序はモデルに任せる。HVE が行うのは、知識源の利用可否の
判定（FR-KD-02）、出典の実在照合（FR-KD-04）、事後検証と修復（FR-KD-09）だけとする。
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    from . import knowledge_files as kf
    from .prompt_loader import load_prompt_file
    from .qa_merger import QADocument, QAMerger, QAQuestion
    from .workiq import extract_tool_metadata_from_event
except ImportError:  # pragma: no cover - flat import compatibility
    import knowledge_files as kf  # type: ignore[no-redef]
    from prompt_loader import load_prompt_file  # type: ignore[no-redef]
    from qa_merger import QADocument, QAMerger, QAQuestion  # type: ignore[no-redef]
    from workiq import extract_tool_metadata_from_event  # type: ignore[no-redef]

KNOWLEDGE_SOURCE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
DISCOVERY_MODES = ("qa", "knowledge", "research")
MAX_REPAIR_ROUNDS = 2
MAX_QA_CREATES = 5
MAX_EVIDENCE_CHARS = 1_000_000
MAX_EVIDENCE_CALLS = 500
MIN_LOCATOR_CHARS = 3
RUNTIME_INSPECT_TIMEOUT_SECONDS = 30.0
RUNTIME_INSPECT_POLL_SECONDS = 0.5

TOOL_READ = "hve_read_file"
TOOL_QA_CREATE = "hve_qa_create"
TOOL_QA_ANSWER = "hve_qa_answer"
TOOL_KNOWLEDGE_WRITE = "hve_knowledge_write"
BUILTIN_READ_TOOLS = ("view", "grep", "glob", "skill")
_DENIED_READ_ROOTS = (".git", ".hve")


# --------------------------------------------------------------------------- FR-KD-01


def is_valid_source_name(name: object) -> bool:
    return isinstance(name, str) and bool(KNOWLEDGE_SOURCE_NAME_RE.match(name))


def parse_source_names(values: Iterable[object], *, strict: bool) -> List[str]:
    """カンマ区切りを含む値列を知識源名へ分解する。

    ``strict=True`` のとき不正名は ``ValueError``、``False`` のとき無視する。
    """
    names: List[str] = []
    for value in values:
        for token in str(value or "").split(","):
            name = token.strip()
            if not name:
                continue
            if not is_valid_source_name(name):
                if strict:
                    raise ValueError(name)
                continue
            if name not in names:
                names.append(name)
    return names


def merge_source_names(*groups: Iterable[str]) -> List[str]:
    merged: List[str] = []
    for group in groups:
        for name in group:
            if is_valid_source_name(name) and name not in merged:
                merged.append(name)
    return merged


# --------------------------------------------------------------------------- FR-KD-02


@dataclass(frozen=True)
class SourceResolution:
    usable: Tuple[str, ...]
    excluded: Tuple[Tuple[str, str], ...]
    enabled_server_names: Tuple[str, ...]
    allowlists: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)


def resolve_sources(
    requested: Sequence[str],
    snapshot: Any,
    allowlist_for: Callable[[str], Sequence[str]],
) -> SourceResolution:
    """FR-TS-12 の snapshot と FR-TS-03 の許可リストから知識源を判定する。"""
    enabled: List[str] = []
    snapshot_ready = getattr(snapshot, "mcp_state", None) == "ready"
    if snapshot_ready:
        for item in getattr(snapshot, "mcp_servers", None) or ():
            name = getattr(item, "name", None)
            if isinstance(name, str) and name and getattr(item, "enabled", None) is True:
                if name not in enabled:
                    enabled.append(name)
    usable: List[str] = []
    excluded: List[Tuple[str, str]] = []
    allowlists: Dict[str, Tuple[str, ...]] = {}
    for name in requested:
        if not snapshot_ready:
            excluded.append((name, "unverified"))
            continue
        if name not in enabled:
            excluded.append((name, "not-configured"))
            continue
        try:
            tools = tuple(str(t) for t in allowlist_for(name) if str(t))
        except Exception:
            tools = ()
        if not tools:
            excluded.append((name, "no-readonly-allowlist"))
            continue
        usable.append(name)
        allowlists[name] = tools
    return SourceResolution(tuple(usable), tuple(excluded), tuple(sorted(enabled)), allowlists)


def format_exclusion_warning(name: str, reason: str) -> str:
    message = f"知識源 {name} を除外します（{reason}）"
    if reason == "server-needs-auth":
        # FR-KD-12: HVE は認証を試みず、利用者が行う操作だけを案内する。
        message += f"。GitHub Copilot CLI で /mcp auth {name} を実行して認証し、HVE を再起動してください。"
    return message


def _status_value(status: object) -> str:
    return str(getattr(status, "value", status) or "").strip().lower()


async def inspect_runtime_sources(
    session: Any,
    sources: Sequence[str],
    allowlists: Mapping[str, Sequence[str]],
    *,
    timeout: float = RUNTIME_INSPECT_TIMEOUT_SECONDS,
) -> Tuple[Tuple[str, ...], Tuple[Tuple[str, str], ...]]:
    """セッション上で connected かつ許可 tool を公開する知識源だけを残す。

    SDK は MCP host の初期化前は ``session.mcp.list`` の状態を空で返すため、
    先に ``initialize_and_validate`` を呼び、``pending`` の間は期限まで再取得する。
    """
    try:
        from copilot.generated.rpc import MCPListToolsRequest
    except ImportError:  # pragma: no cover - SDK 未導入
        return (), tuple((name, "unverified") for name in sources)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(0.001, timeout)

    def _remaining() -> float:
        return max(0.001, deadline - loop.time())

    async def _rpc(call: Callable[..., Awaitable[Any]], *args: Any) -> Any:
        remaining = _remaining()
        return await asyncio.wait_for(call(*args, timeout=remaining), timeout=remaining)

    unverified = tuple((name, "unverified") for name in sources)
    try:
        initialize = getattr(getattr(session.rpc, "tools", None), "initialize_and_validate", None)
        if callable(initialize):
            await _rpc(initialize)
        while True:
            listing = await _rpc(session.rpc.mcp.list)
            servers = {getattr(s, "name", None): s for s in getattr(listing, "servers", None) or ()}
            statuses = {
                name: (_status_value(getattr(servers[name], "status", None)) if name in servers else "not_configured")
                for name in sources
            }
            if "pending" not in statuses.values() or deadline - loop.time() <= RUNTIME_INSPECT_POLL_SECONDS:
                break
            await asyncio.sleep(RUNTIME_INSPECT_POLL_SECONDS)
    except Exception:
        return (), unverified
    usable: List[str] = []
    excluded: List[Tuple[str, str]] = []
    for name in sources:
        status = statuses[name]
        if status != "connected":
            excluded.append((name, f"server-{status or 'unknown'}"))
            continue
        try:
            result = await _rpc(session.rpc.mcp.list_tools, MCPListToolsRequest(server_name=name))
            exposed = {getattr(t, "name", None) for t in getattr(result, "tools", None) or ()}
        except Exception:
            excluded.append((name, "unverified"))
            continue
        if exposed & set(allowlists.get(name, ())):
            usable.append(name)
        else:
            excluded.append((name, "no-allowlisted-tool-exposed"))
    return tuple(usable), tuple(excluded)


# --------------------------------------------------------------------------- FR-KD-04


def normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).replace("\\/", "/")).strip().casefold()


def _event_type(event: object) -> str:
    raw = event.get("type") if isinstance(event, dict) else getattr(event, "type", None)
    return str(getattr(raw, "value", raw) or "")


def _event_data(event: object) -> object:
    return event.get("data") if isinstance(event, dict) else getattr(event, "data", None)


def _attr(obj: object, *names: str) -> object:
    for name in names:
        value = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
        if value not in (None, ""):
            return value
    return None


class SourceEvidence:
    """成功した MCP 呼出しの server・tool・本文をメモリ上だけに保持する（NFR-KD-01）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: Dict[str, Tuple[str, str]] = {}
        self._ambiguous: set[str] = set()
        self._calls: List[Tuple[str, str, str]] = []

    def handle_event(self, event: object) -> None:
        metadata = extract_tool_metadata_from_event(event)
        if metadata is None or not metadata.tool_call_id:
            return
        call_id = metadata.tool_call_id
        with self._lock:
            if metadata.event_type == "tool.execution_start":
                server = metadata.mcp_server_name or ""
                tool = metadata.mcp_tool_name or ""
                if call_id in self._pending or call_id in self._ambiguous:
                    self._pending.pop(call_id, None)
                    self._ambiguous.add(call_id)
                    return
                if server and tool:
                    self._pending[call_id] = (server, tool)
                return
            if metadata.event_type != "tool.execution_complete":
                return
            if call_id in self._ambiguous:
                return
            pair = self._pending.pop(call_id, None)
            if pair is None or metadata.success is not True or len(self._calls) >= MAX_EVIDENCE_CALLS:
                return
            result = _attr(_event_data(event), "result")
            parts = [str(_attr(result, "content") or ""), str(_attr(result, "detailed_content", "detailedContent") or "")]
            text = "\n".join(p for p in parts if p)[:MAX_EVIDENCE_CHARS]
            self._calls.append((pair[0], pair[1], text))

    def successful_call_count(self, server: str, tool: str) -> int:
        with self._lock:
            return sum(1 for s, t, _ in self._calls if s == server and t == tool)

    def locator_found(self, server: str, locator: str) -> bool:
        needle = normalize_for_match(locator)
        with self._lock:
            texts = [text for s, _, text in self._calls if s == server]
        return any(needle in normalize_for_match(text) for text in texts)


def verify_source(
    source: kf.SourceEntry,
    *,
    repo_root: Path,
    usable: Sequence[str],
    allowlists: Mapping[str, Sequence[str]],
    evidence: SourceEvidence,
) -> Optional[str]:
    """FR-KD-04 の規則で出典を検証し、違反の理由コードを返す（合格は ``None``）。"""
    if source.kind == "repo":
        try:
            rel = kf.normalize_relative_path(source.locator)
        except kf.KnowledgeFileError:
            return "repo-path-invalid"
        if rel.split("/")[0] in _DENIED_READ_ROOTS:
            return "repo-path-invalid"
        path = Path(repo_root) / rel
        try:
            path.resolve().relative_to(Path(repo_root).resolve())
        except (OSError, ValueError):
            return "repo-path-invalid"
        return None if path.is_file() else "repo-path-missing"
    if source.kind != "mcp":
        return "unknown-source-kind"
    if source.server not in usable:
        return "server-not-usable"
    if source.tool not in allowlists.get(source.server, ()):
        return "tool-not-allowlisted"
    if evidence.successful_call_count(source.server, source.tool) == 0:
        return "no-successful-call"
    if len(source.locator.strip()) < MIN_LOCATOR_CHARS:
        return "locator-too-short"
    if not evidence.locator_found(source.server, source.locator):
        return "locator-not-found"
    return None


# --------------------------------------------------------------------------- tools (FR-KD-05)

_SOURCE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "この呼出し内の出典 ID（例: L1）"},
        "kind": {"type": "string", "enum": ["mcp", "repo"]},
        "server": {"type": "string", "description": "kind=mcp のときの MCP server 名"},
        "tool": {"type": "string", "description": "kind=mcp のときの MCP tool 名"},
        "locator": {"type": "string", "description": "応答に含まれていた URL・パス・タイトル、または repo 相対パス"},
        "summary": {"type": "string"},
    },
    "required": ["id", "kind", "locator", "summary"],
}

_TOOL_SPECS: Dict[str, Tuple[str, Dict[str, Any]]] = {
    TOOL_READ: (
        "qa/ または knowledge/ のファイルの内容と SHA-256 を返す。更新の前に必ず読むこと。",
        {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    ),
    TOOL_QA_CREATE: (
        "調査した問いの一覧を新しい質問票として qa/ に作成する。",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "questions": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 50,
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "category": {"type": "string"},
                            "priority": {"type": "string"},
                            "background": {"type": "string"},
                            "default_answer": {"type": "string"},
                        },
                        "required": ["question"],
                    },
                },
            },
            "required": ["title", "questions"],
        },
    ),
    TOOL_QA_ANSWER: (
        "質問票の質問へ調査回答・調査状態・出典を記録する。出典を確認できない場合は失敗する。",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "base_sha256": {"type": "string"},
                "answers": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "no": {"type": "integer"},
                            "answer": {"type": "string"},
                            "status": {"type": "string", "enum": list(kf.RESEARCH_STATUSES)},
                            "source_ids": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["no", "answer", "status"],
                    },
                },
                "sources": {"type": "array", "items": _SOURCE_SCHEMA},
            },
            "required": ["path", "base_sha256", "answers"],
        },
    ),
    TOOL_KNOWLEDGE_WRITE: (
        "knowledge/ の D 文書または status ファイルを全文で書く。新規作成は base_sha256=null。",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "base_sha256": {"type": ["string", "null"]},
                "content": {"type": "string"},
                "summary": {"type": "string"},
                "sources": {"type": "array", "minItems": 1, "items": _SOURCE_SCHEMA},
            },
            "required": ["path", "base_sha256", "content", "summary", "sources"],
        },
    ),
}


class ToolInputError(Exception):
    def __init__(self, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.payload = {"ok": False, "code": code, "message": message, **extra}


def _require_str(args: Mapping[str, Any], key: str, *, allow_empty: bool = False) -> str:
    value = args.get(key)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ToolInputError("invalid-input", f"{key} は文字列で指定してください。")
    return value


def _parse_sources(raw: object) -> List[kf.SourceEntry]:
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise ToolInputError("invalid-input", "sources は配列で指定してください。")
    entries: List[kf.SourceEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ToolInputError("invalid-input", "sources の要素はオブジェクトです。")
        entries.append(kf.SourceEntry(
            id=_require_str(item, "id"),
            kind=str(item.get("kind") or ""),
            server=str(item.get("server") or ""),
            tool=str(item.get("tool") or ""),
            locator=str(item.get("locator") or ""),
            summary=str(item.get("summary") or ""),
        ))
    return entries


class DiscoveryToolset:
    """知識探索セッションへ渡す custom tool と、その書込み記録。"""

    def __init__(
        self,
        *,
        mode: str,
        repo_root: Path,
        run_id: str,
        label: str,
        usable: Sequence[str],
        allowlists: Mapping[str, Sequence[str]],
        evidence: SourceEvidence,
        qa_path: Optional[str] = None,
        validator_path: Optional[Path] = None,
    ) -> None:
        if mode not in DISCOVERY_MODES:
            raise ValueError(f"unknown discovery mode: {mode}")
        self.mode = mode
        self.repo_root = Path(repo_root)
        self.run_id = run_id
        self.label = label
        self.usable: Tuple[str, ...] = tuple(usable)
        self.allowlists = {k: tuple(v) for k, v in allowlists.items()}
        self.evidence = evidence
        self.qa_path = kf.normalize_relative_path(qa_path) if qa_path else None
        self.validator_path = validator_path
        self.created_qa: List[str] = []
        self.knowledge_written: List[str] = []
        self.failures = 0
        self._lock = threading.Lock()

    def tool_names(self) -> List[str]:
        names = [TOOL_READ, TOOL_QA_CREATE, TOOL_QA_ANSWER]
        if self.mode == "knowledge":
            names.append(TOOL_KNOWLEDGE_WRITE)
        return names

    def touched_qa_paths(self) -> List[str]:
        paths = [self.qa_path] if self.qa_path else []
        return paths + [p for p in self.created_qa if p not in paths]

    # -- verification -------------------------------------------------------

    def _verify(self, sources: Sequence[kf.SourceEntry]) -> Dict[str, Optional[str]]:
        return {
            s.id: verify_source(
                s, repo_root=self.repo_root, usable=self.usable,
                allowlists=self.allowlists, evidence=self.evidence,
            )
            for s in sources
        }

    # -- handlers (同期。SDK からは別スレッドで呼ぶ) -------------------------

    def handle(self, name: str, args: object) -> Dict[str, Any]:
        if not isinstance(args, dict):
            args = {}
        try:
            if name == TOOL_READ:
                return {"ok": True, **kf.read_file(self.repo_root, _require_str(args, "path"))}
            if name == TOOL_QA_CREATE:
                return self._qa_create(args)
            if name == TOOL_QA_ANSWER:
                return self._qa_answer(args)
            if name == TOOL_KNOWLEDGE_WRITE and self.mode == "knowledge":
                return self._knowledge_write(args)
            raise ToolInputError("unknown-tool", f"未知の tool です: {name}")
        except kf.KnowledgeFileError as exc:
            result = exc.to_dict()
        except ToolInputError as exc:
            result = dict(exc.payload)
        with self._lock:
            self.failures += 1
        return result

    def _qa_create(self, args: Mapping[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if len(self.created_qa) >= MAX_QA_CREATES:
                raise ToolInputError("limit-exceeded", f"1 セッションで作成できる質問票は {MAX_QA_CREATES} 件までです。")
        title = _require_str(args, "title")
        raw_questions = args.get("questions")
        if not isinstance(raw_questions, list) or not 1 <= len(raw_questions) <= 50:
            raise ToolInputError("invalid-input", "questions は 1〜50 件の配列で指定してください。")
        questions: List[QAQuestion] = []
        for number, item in enumerate(raw_questions, start=1):
            if not isinstance(item, dict):
                raise ToolInputError("invalid-input", "questions の要素はオブジェクトです。")
            questions.append(QAQuestion(
                no=number,
                question=_require_str(item, "question"),
                category=str(item.get("category") or ""),
                priority=str(item.get("priority") or ""),
                background=str(item.get("background") or ""),
                default_answer=str(item.get("default_answer") or ""),
            ))
        doc = QADocument(
            title=title,
            status="調査中",
            header_fields=[("状態", "調査中"), ("作成", f"知識探索（{self.run_id}）")],
            questions=questions,
        )
        rel, sha = kf.create_qa_document(
            self.repo_root, run_id=self.run_id, label=self.label, text=QAMerger.render_merged(doc)
        )
        with self._lock:
            self.created_qa.append(rel)
        return {"ok": True, "path": rel, "sha256": sha, "question_numbers": [q.no for q in questions]}

    def _qa_answer(self, args: Mapping[str, Any]) -> Dict[str, Any]:
        rel = kf.normalize_relative_path(_require_str(args, "path"))
        if rel not in self.touched_qa_paths():
            raise kf.KnowledgeFileError("path-denied", f"このセッションで更新できない質問票です: {rel}")
        sources = _parse_sources(args.get("sources"))
        source_ids = {s.id for s in sources}
        raw_answers = args.get("answers")
        if not isinstance(raw_answers, list) or not raw_answers:
            raise ToolInputError("invalid-input", "answers は 1 件以上の配列で指定してください。")
        reasons = self._verify(sources)
        answers: List[kf.ResearchAnswer] = []
        violations: List[Dict[str, Any]] = []
        for item in raw_answers:
            if not isinstance(item, dict) or not isinstance(item.get("no"), int):
                raise ToolInputError("invalid-input", "answers の要素には整数の no が必要です。")
            cited = tuple(str(sid) for sid in item.get("source_ids") or ())
            status = str(item.get("status") or "")
            for sid in cited:
                if sid not in source_ids:
                    violations.append({"answer": item["no"], "source": sid, "reason": "unknown-source-id"})
            verified = [sid for sid in cited if sid in source_ids and reasons.get(sid) is None]
            if status == "Confirmed" and not verified:
                violations.append({"answer": item["no"], "source": None, "reason": "confirmed-without-source"})
            answers.append(kf.ResearchAnswer(
                no=item["no"], answer=str(item.get("answer") or ""), status=status, source_ids=cited,
            ))
        violations.extend(
            {"answer": None, "source": sid, "reason": reason} for sid, reason in reasons.items() if reason
        )
        if violations:
            raise ToolInputError(
                "source-verification-failed", "出典を確認できないため記録しませんでした。", violations=violations
            )
        return kf.update_qa_research(
            self.repo_root, rel, base_sha256=args.get("base_sha256"), answers=answers, sources=sources,
        )

    def _knowledge_write(self, args: Mapping[str, Any]) -> Dict[str, Any]:
        sources = _parse_sources(args.get("sources"))
        if not sources:
            raise ToolInputError("invalid-input", "出典を 1 件以上指定してください。")
        violations = [
            {"source": sid, "reason": reason} for sid, reason in self._verify(sources).items() if reason
        ]
        if violations:
            raise ToolInputError(
                "source-verification-failed", "出典を確認できないため書き込みませんでした。", violations=violations
            )
        base = args.get("base_sha256")
        result = kf.write_knowledge(
            self.repo_root,
            _require_str(args, "path"),
            _require_str(args, "content", allow_empty=True),
            base_sha256=base if isinstance(base, str) else None,
            run_id=self.run_id,
            summary=_require_str(args, "summary"),
            locators=[s.locator for s in sources],
            validator_path=self.validator_path,
        )
        with self._lock:
            self.knowledge_written.append(result["path"])
        return result

    def sdk_tools(self) -> List[Any]:
        """Copilot SDK の ``Tool`` を返す（ハンドラは別スレッドでファイル操作を行う）。"""
        from copilot.tools import Tool, ToolResult

        def _make(name: str) -> Any:
            async def _handler(invocation: Any) -> Any:
                result = await asyncio.to_thread(self.handle, name, getattr(invocation, "arguments", None))
                return ToolResult(
                    text_result_for_llm=json.dumps(result, ensure_ascii=False),
                    result_type="success" if result.get("ok") else "failure",
                )
            description, schema = _TOOL_SPECS[name]
            return Tool(name=name, description=description, handler=_handler, parameters=schema, skip_permission=True)

        return [_make(name) for name in self.tool_names()]


# --------------------------------------------------------------------------- FR-KD-03


def decide_permission(
    request: Any,
    *,
    repo_root: Path,
    usable: Sequence[str],
    allowlists: Mapping[str, Sequence[str]],
    custom_tools: Sequence[str],
) -> bool:
    """知識探索セッションで許可する操作だけ True を返す。"""
    if getattr(request, "managed_approval_required", False) is True:
        return False
    if getattr(request, "request_sandbox_bypass", False) is True:
        return False
    kind = str(getattr(request, "kind", "") or "")
    if kind == "read":
        raw = getattr(request, "path", None)
        if not isinstance(raw, str) or not raw.strip():
            return False
        root = Path(repo_root).resolve()
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            rel = candidate.resolve().relative_to(root)
        except (OSError, ValueError):
            return False
        parts = rel.parts
        if parts and parts[0] in _DENIED_READ_ROOTS:
            return False
        return not (parts and parts[-1].startswith(".env"))
    if kind == "mcp":
        server = getattr(request, "server_name", None)
        tool = getattr(request, "tool_name", None)
        return server in usable and tool in tuple(allowlists.get(server, ()))
    if kind == "custom-tool":
        return getattr(request, "tool_name", None) in custom_tools
    return False


def make_permission_handler(repo_root: Path, toolset: DiscoveryToolset) -> Callable[[Any, Any], Any]:
    def _handler(request: Any, _invocation: Any) -> Any:
        from copilot.generated.rpc import PermissionDecisionApproveOnce, PermissionDecisionReject

        allowed = decide_permission(
            request,
            repo_root=repo_root,
            usable=toolset.usable,
            allowlists=toolset.allowlists,
            custom_tools=toolset.tool_names(),
        )
        if allowed:
            return PermissionDecisionApproveOnce()
        return PermissionDecisionReject(feedback="知識探索セッションでは許可されない操作です。")

    return _handler


def build_session_options(
    *,
    base: Mapping[str, Any],
    usable: Sequence[str],
    allowlists: Mapping[str, Sequence[str]],
    enabled_server_names: Sequence[str],
    toolset: DiscoveryToolset,
    tools: Sequence[Any],
    permission_handler: Callable[[Any, Any], Any],
    on_event: Callable[[Any], None],
) -> Dict[str, Any]:
    options: Dict[str, Any] = dict(base)
    options.pop("on_user_input_request", None)
    options.update({
        "enable_config_discovery": True,
        "disabled_mcp_servers": sorted(set(enabled_server_names) - set(usable)),
        "available_tools": (
            [f"builtin:{name}" for name in BUILTIN_READ_TOOLS]
            + [f"custom:{name}" for name in toolset.tool_names()]
            + [f"mcp:{server}-{tool}" for server in usable for tool in allowlists.get(server, ())]
        ),
        "tools": list(tools),
        "infinite_sessions": {"enabled": True},
        "streaming": True,
        "on_permission_request": permission_handler,
        "on_event": on_event,
    })
    return options


def _fill(template: str, values: Mapping[str, str]) -> str:
    for key, value in values.items():
        template = template.replace("{" + key + "}", value)
    return template


_MODE_PROMPTS: Dict[str, str] = {
    "qa": "runtime/knowledge-discovery/qa.prompt.md",
    "knowledge": "runtime/knowledge-discovery/knowledge.prompt.md",
    "research": "runtime/knowledge-discovery/research.prompt.md",
}


def build_goal_prompt(
    *,
    mode: str,
    goal: str,
    usable: Sequence[str],
    allowlists: Mapping[str, Sequence[str]],
    run_id: str,
    qa_path: Optional[str],
) -> str:
    sources = "\n".join(
        f"- {server}: {', '.join(allowlists.get(server, ()))}" for server in usable
    )
    values = {"goal": goal.strip(), "sources": sources, "qa_path": qa_path or "", "run_id": run_id}
    common = load_prompt_file("runtime/knowledge-discovery/common.prompt.md")
    specific = load_prompt_file(_MODE_PROMPTS[mode])
    return _fill(common, values).rstrip() + "\n\n" + _fill(specific, values).strip() + "\n"


def build_repair_prompt(missing: Sequence[str]) -> str:
    template = load_prompt_file("runtime/knowledge-discovery/repair.prompt.md")
    return _fill(template, {"missing": "\n".join(f"- {item}" for item in missing)})


# --------------------------------------------------------------------------- FR-KD-09


def _parse_qa(repo_root: Path, rel: str) -> Optional[QADocument]:
    try:
        return QAMerger.parse_qa_file(Path(repo_root) / rel)
    except (OSError, ValueError):
        return None


def find_missing_items(toolset: DiscoveryToolset) -> List[str]:
    """調査状態が未記録の項目を返す。"""
    if toolset.mode != "qa" and not toolset.created_qa:
        return ["QA 未作成"]
    missing: List[str] = []
    for rel in toolset.touched_qa_paths():
        doc = _parse_qa(toolset.repo_root, rel)
        if doc is None:
            missing.append(f"{rel}: 読み込めません")
            continue
        for q in doc.questions:
            if not q.research_status:
                missing.append(f"{rel} Q{q.no}")
    return missing


def _retry_update(repo_root: Path, rel: str, mutate: Callable[[str], None]) -> None:
    for _ in range(5):
        current = kf.read_file(repo_root, rel)
        try:
            mutate(current["sha256"])
            return
        except kf.KnowledgeFileError as exc:
            if exc.code != "conflict":
                raise
    raise kf.KnowledgeFileError("conflict", f"競合が解消しませんでした: {rel}")


def mark_unrecorded_unknown(repo_root: Path, rel: str) -> int:
    doc = _parse_qa(repo_root, rel)
    if doc is None:
        return 0
    pending = [q.no for q in doc.questions if not q.research_status]
    if not pending:
        return 0
    answers = [kf.ResearchAnswer(no=n, answer="", status="Unknown") for n in pending]
    _retry_update(
        repo_root, rel,
        lambda sha: kf.update_qa_research(repo_root, rel, base_sha256=sha, answers=answers, sources=[]),
    )
    return len(pending)


def finalize_ledger(repo_root: Path, rel: str) -> None:
    """knowledge / research の質問票を ``調査済み`` とし、調査回答を回答欄へ写す。"""

    def _mutate(sha: str) -> None:
        current = kf.read_file(repo_root, rel)
        if current["sha256"] != sha:
            raise kf.KnowledgeFileError("conflict", rel, current_sha256=current["sha256"])
        doc = QAMerger.parse_qa_content(current["content"])
        for q in doc.questions:
            if q.research_status in ("Confirmed", "Tentative") and q.research_answer.strip():
                q.user_answer = q.research_answer.strip()
        doc.status = "調査済み"
        doc.header_fields = [(k, "調査済み" if k == "状態" else v) for k, v in doc.header_fields]
        kf.write_file(repo_root, rel, QAMerger.render_merged(doc), base_sha256=sha, kind="qa")

    _retry_update(repo_root, rel, _mutate)


def count_statuses(repo_root: Path, paths: Sequence[str]) -> Dict[str, int]:
    counts = {status: 0 for status in kf.RESEARCH_STATUSES}
    for rel in paths:
        doc = _parse_qa(repo_root, rel)
        for q in doc.questions if doc else ():
            if q.research_status in counts:
                counts[q.research_status] += 1
    return counts


def format_summary(label: str, counts: Mapping[str, int], repairs: int, failures: int) -> str:
    return (
        f"知識探索 [{label}]: Confirmed={counts.get('Confirmed', 0)} "
        f"Tentative={counts.get('Tentative', 0)} Unknown={counts.get('Unknown', 0)} "
        f"修復={repairs} tool失敗={failures}"
    )


QA_STATUS_SECTION = "知識探索の状況"


def build_status_section(
    requested: Sequence[str],
    result: Any,
    *,
    consent_denied: bool = False,
) -> str:
    """FR-KD-12: QA の ``## 知識探索の状況`` 節の本文（表）を返す。

    ``result`` が ``None`` なら探索の開始時に例外が発生したものとして扱う。
    """
    usable = set(getattr(result, "usable", None) or ()) if result is not None else set()
    excluded = dict(getattr(result, "excluded", None) or ()) if result is not None else {}
    rows = ["| 知識源 | 状態 | 理由コード |", "|---|---|---|"]
    for name in requested:
        if consent_denied:
            state, reason = "未実行", "consent-not-granted"
        elif result is None:
            state, reason = "不明", "discovery-error"
        elif name in usable:
            state, reason = "利用", "-"
        elif name in excluded:
            state, reason = "除外", excluded[name]
        else:
            state, reason = "不明", "not-reported"
        rows.append("| " + " | ".join(kf.escape_table_cell(c) for c in (name, state, reason)) + " |")
    return "\n".join(rows)


# --------------------------------------------------------------------------- run


@dataclass
class DiscoveryRequest:
    mode: str
    repo_root: Path
    run_id: str
    label: str
    goal: str
    sources: Sequence[str]
    qa_path: Optional[str] = None
    validator_path: Optional[Path] = None


@dataclass
class DiscoveryResult:
    ran: bool
    reason: str = ""
    qa_paths: List[str] = field(default_factory=list)
    knowledge_paths: List[str] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=dict)
    repairs: int = 0
    tool_failures: int = 0
    error: Optional[str] = None
    usable: List[str] = field(default_factory=list)
    excluded: List[Tuple[str, str]] = field(default_factory=list)


async def run_knowledge_discovery(
    request: DiscoveryRequest,
    *,
    snapshot: Any,
    allowlist_for: Callable[[str], Sequence[str]],
    base_session_options: Mapping[str, Any],
    create_session: Callable[[Dict[str, Any]], Awaitable[Any]],
    disconnect: Callable[[Any], Awaitable[None]],
    warn: Callable[[str], None],
    status: Callable[[str], None],
    timeout: float,
    event_sink: Optional[Callable[[Any], None]] = None,
) -> DiscoveryResult:
    """1 セッションの知識探索を実行し、事後検証と修復まで行う。"""
    resolution = resolve_sources(list(request.sources), snapshot, allowlist_for)
    excluded_all: List[Tuple[str, str]] = list(resolution.excluded)
    for name, reason in resolution.excluded:
        warn(format_exclusion_warning(name, reason))
    if not resolution.usable:
        return DiscoveryResult(ran=False, reason="no-usable-source", excluded=excluded_all)

    evidence = SourceEvidence()
    toolset = DiscoveryToolset(
        mode=request.mode, repo_root=request.repo_root, run_id=request.run_id, label=request.label,
        usable=resolution.usable, allowlists=resolution.allowlists, evidence=evidence,
        qa_path=request.qa_path, validator_path=request.validator_path,
    )

    def _on_event(event: Any) -> None:
        evidence.handle_event(event)
        if event_sink is not None:
            try:
                event_sink(event)
            except Exception:
                pass

    options = build_session_options(
        base=base_session_options, usable=resolution.usable, allowlists=resolution.allowlists,
        enabled_server_names=resolution.enabled_server_names, toolset=toolset,
        tools=toolset.sdk_tools(), permission_handler=make_permission_handler(request.repo_root, toolset),
        on_event=_on_event,
    )
    session = await create_session(options)
    result = DiscoveryResult(ran=True, excluded=excluded_all)
    try:
        usable, excluded = await inspect_runtime_sources(session, resolution.usable, resolution.allowlists)
        excluded_all.extend(excluded)
        for name, reason in excluded:
            warn(format_exclusion_warning(name, reason))
        if not usable:
            return DiscoveryResult(ran=False, reason="no-usable-source", excluded=excluded_all)
        toolset.usable = usable
        result.usable = list(usable)
        prompt = build_goal_prompt(
            mode=request.mode, goal=request.goal, usable=usable, allowlists=resolution.allowlists,
            run_id=request.run_id, qa_path=toolset.qa_path,
        )
        await session.send_and_wait(prompt, timeout=timeout)
        while result.repairs < MAX_REPAIR_ROUNDS:
            missing = find_missing_items(toolset)
            if not missing:
                break
            result.repairs += 1
            await session.send_and_wait(build_repair_prompt(missing), timeout=timeout)
    except Exception as exc:
        result.error = type(exc).__name__
        warn(f"知識探索 [{request.label}] が途中で終了しました（{result.error}）。記録済みの調査結果だけを使います。")
    finally:
        try:
            await disconnect(session)
        except Exception as exc:
            warn(f"知識探索 [{request.label}] のセッション切断に失敗しました（{type(exc).__name__}）。")

    for rel in toolset.touched_qa_paths():
        try:
            mark_unrecorded_unknown(request.repo_root, rel)
            if request.mode != "qa":
                finalize_ledger(request.repo_root, rel)
        except kf.KnowledgeFileError as exc:
            warn(f"知識探索 [{request.label}] の事後処理に失敗しました（{exc.code}: {rel}）。")
    result.qa_paths = toolset.touched_qa_paths()
    result.knowledge_paths = list(dict.fromkeys(toolset.knowledge_written))
    result.counts = count_statuses(request.repo_root, result.qa_paths)
    result.tool_failures = toolset.failures
    status(format_summary(request.label, result.counts, result.repairs, result.tool_failures))
    return result


# --------------------------------------------------------------------------- FR-KD-08


def _escape_comment_cell(text: str) -> str:
    """QA の表セル（``&#124;`` / ``<br>`` で保存済み）をコメント用に無害化する。"""
    held = str(text).replace("<br>", "\x00")
    held = held.replace("<", "&lt;").replace(">", "&gt;")
    return kf.escape_table_cell(held).replace("\x00", "<br>")


def build_ard_comment(repo_root: Path, qa_paths: Sequence[str]) -> Optional[str]:
    """ARD Step 2 へ投稿するコメント本文。回答が 0 件なら ``None``。"""
    blocks: List[str] = []
    for rel in qa_paths:
        doc = _parse_qa(repo_root, rel)
        if doc is None:
            continue
        rows = [
            q for q in doc.questions
            if q.research_status in ("Confirmed", "Tentative") and q.research_answer.strip()
        ]
        if not rows:
            continue
        blocks.extend([
            f"QA: `{rel}`",
            "",
            "| No. | 質問 | 調査状態 | 調査回答 | 調査出典 |",
            "|---|---|---|---|---|",
            *(
                "| " + " | ".join(_escape_comment_cell(c) for c in (
                    str(q.no), q.question, q.research_status, q.research_answer, q.research_sources,
                )) + " |"
                for q in rows
            ),
            "",
        ])
        sources = doc.raw_sections.get(kf.QA_SOURCES_SECTION, "").strip()
        if sources:
            safe = sources.replace("<br>", "\x00").replace("<", "&lt;").replace(">", "&gt;").replace("\x00", "<br>")
            blocks.extend(["### 調査出典", "", safe, ""])
    if not blocks:
        return None
    return "\n".join(["## ARD 知識探索: ユースケース参照情報", "", *blocks]).rstrip() + "\n"
