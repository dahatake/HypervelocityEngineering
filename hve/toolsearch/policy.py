"""HVE Tool Search — ポリシー解決（FR-TS-03）。

**強制力の所在（重要）**

本モジュールが決めるのは「`tool_search_tool` が **何を返すか**」だけである。
モデルによる呼び出しを禁止する力は持たない。禁止の強制は次の 2 つでしか行えない:

- ``create_session(excluded_tools=[...])``
- MCP サーバー設定の ``tools`` allowlist（``[]`` = なし / ``"*"`` = 全件）

したがって本モジュールを安全境界として扱ってはならない（FR-TS-03）。
``apply_policy()`` の ``excluded_tools`` 引数は「索引から落とす」ためのものであり、
実行時の禁止は呼び出し側が上記 2 つで別途設定する必要がある。
"""

from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .types import PinMode, ToolEntry, ToolSearchContractError, resolve_policy_value
from .usage import LOG_DIRNAME

_POLICY_FILE = Path(__file__).with_name("policy.json")

# キーは常に ToolEntry.id 形式か、サーバーワイルドカード。ツール名だけのキーは拒否する。
POLICY_KEY_RE = re.compile(r"^(mcp|native|skill):[^:*]+:([^:]+|\*)$")

_KEYED_TABLES = ("pins", "additional_search_text")
_VALID_PIN_MODES = ("always", "auto", "never")
_VALID_STEP_MODES = ("search", "pin_only")

RESOURCE_KINDS = ("plugins", "mcp_servers", "skills")
RESOURCE_CLASSIFICATIONS = (
    "knowledge",
    "software-engineering",
    "both",
    "unclassified",
)
_RESOURCE_ROUTING_FIELDS = (
    "resource_classifications",
    "knowledge_tool_allowlists",
    "software_engineering_tool_allowlists",
)
_REQUIRED_MCP_SERVERS_BY_SKILL_FIELD = "required_mcp_servers_by_skill"
_MCP_DEPENDENT_REQUIRED_SKILLS = frozenset({"microsoft-foundry"})

# FR-TS-13: Knowledge resource は registry 上の全 Workflow で利用候補。
KNOWLEDGE_WORKFLOW_IDS = frozenset(
    {
        "ard", "aas", "ada", "aad-web", "asdw-web", "adfd", "adfdv",
        "aag", "aagd", "aar", "akm", "adi", "adoc",
    }
)

# FR-TS-13: Software Engineering resource を利用できる Workflow の単一正本。
SOFTWARE_ENGINEERING_WORKFLOW_IDS = frozenset(
    {
        "aas", "ada", "aad-web", "asdw-web", "adfd", "adfdv",
        "aag", "aagd", "aar", "adoc",
    }
)

_REQUIRED_FIELDS = (
    "version", "limit", "max_limit", "tau",
    "field_weights", "pins", "additional_search_text", "step_overrides",
)
_REQUIRED_WEIGHT_FIELDS = frozenset(
    {"name", "additional_search_text", "description", "arg_terms"}
)


def _validate_exact_resource_name(name: object, *, field_name: str) -> str:
    if not isinstance(name, str) or not name.strip() or name == "*":
        raise PolicyError(f"{field_name} name must be a non-empty exact resource name")
    return name


def _validate_resource_classifications(raw: object) -> dict[str, dict[str, str]]:
    if not isinstance(raw, Mapping) or set(raw) != set(RESOURCE_KINDS):
        raise PolicyError(
            "resource_classifications must contain exactly "
            f"{list(RESOURCE_KINDS)}"
        )

    validated: dict[str, dict[str, str]] = {}
    for kind in RESOURCE_KINDS:
        table = raw[kind]
        if not isinstance(table, Mapping):
            raise PolicyError(f"resource_classifications.{kind} must be an object")
        validated[kind] = {}
        for raw_name, classification in table.items():
            name = _validate_exact_resource_name(
                raw_name,
                field_name=f"resource_classifications.{kind}",
            )
            if not isinstance(classification, str) or classification not in RESOURCE_CLASSIFICATIONS:
                raise PolicyError(
                    f"resource_classifications.{kind}[{name!r}] classification "
                    f"must be one of {RESOURCE_CLASSIFICATIONS}"
                )
            validated[kind][name] = classification
    return validated


def _validate_tool_allowlists(raw: object, *, field_name: str) -> dict[str, tuple[str, ...]]:
    if not isinstance(raw, Mapping):
        raise PolicyError(f"{field_name} allowlist table must be an object")

    validated: dict[str, tuple[str, ...]] = {}
    for raw_server, raw_tools in raw.items():
        server = _validate_exact_resource_name(raw_server, field_name=f"{field_name} allowlist")
        if not isinstance(raw_tools, list):
            raise PolicyError(f"{field_name}[{server!r}] allowlist must be a list")

        tools: list[str] = []
        for tool in raw_tools:
            if (
                not isinstance(tool, str)
                or not tool.strip()
                or tool == "*"
                or ":" in tool
                or any(character.isspace() for character in tool)
            ):
                raise PolicyError(
                    f"{field_name}[{server!r}] allowlist entries must be bare exact tool names"
                )
            if tool in tools:
                raise PolicyError(
                    f"{field_name}[{server!r}] allowlist contains duplicate tool {tool!r}"
                )
            tools.append(tool)
        validated[server] = tuple(tools)
    return validated


def _validate_required_mcp_servers_by_skill(
    raw: object,
) -> dict[str, tuple[str, ...]]:
    field_name = _REQUIRED_MCP_SERVERS_BY_SKILL_FIELD
    if not isinstance(raw, Mapping):
        raise PolicyError(f"{field_name} must be an object")

    validated: dict[str, tuple[str, ...]] = {}
    for raw_skill, raw_servers in raw.items():
        skill = _validate_exact_resource_name(raw_skill, field_name=field_name)
        if not isinstance(raw_servers, list) or not raw_servers:
            raise PolicyError(f"{field_name}[{skill!r}] must be a non-empty list")
        servers: list[str] = []
        for raw_server in raw_servers:
            server = _validate_exact_resource_name(
                raw_server,
                field_name=f"{field_name}[{skill!r}]",
            )
            if server in servers:
                raise PolicyError(
                    f"{field_name}[{skill!r}] contains duplicate server {server!r}"
                )
            servers.append(server)
        validated[skill] = tuple(servers)
    return validated


class PolicyError(ToolSearchContractError):
    """policy.json の形式違反。"""


@dataclass(frozen=True)
class PolicyDecision:
    """ポリシー適用の結果。

    ``pinned`` は検索なしで常時公開する集合、``searchable`` は検索の対象。
    ``dropped`` は索引から外した ``ToolEntry.id``（``excluded_tools`` 一致分）。

    ``pin`` の 3 値は「pin するか」だけを表し、公開可否ではない:

    - ``always`` — 常時公開（検索を経ずに呼べる）
    - ``auto``   — 検索対象。利用履歴による自動 pin の**対象になる**（FR-TS-07）
    - ``never``  — 検索対象。自動 pin の**対象にしない**（常に検索経由のまま）

    ``never`` は「索引から消す」ではない。索引から消す唯一の手段は ``excluded_tools``。
    """

    pinned: tuple[ToolEntry, ...] = ()
    searchable: tuple[ToolEntry, ...] = ()
    dropped: tuple[str, ...] = ()

    @property
    def auto_pin_candidates(self) -> tuple[ToolEntry, ...]:
        """自動 pin（FR-TS-07）で昇格させてよいエントリ。"""
        return tuple(entry for entry in self.searchable if entry.pin == "auto")


@dataclass(frozen=True)
class ToolSearchPolicy:
    version: int
    limit: int
    max_limit: int
    tau: float
    field_weights: Mapping[str, float]
    pins: Mapping[str, PinMode]
    additional_search_text: Mapping[str, str]
    step_overrides: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    resource_classifications: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    knowledge_tool_allowlists: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    software_engineering_tool_allowlists: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    required_mcp_servers_by_skill: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    extra_top_level: Mapping[str, Any] = field(default_factory=dict)

    # --- 読み込みと検証 ---------------------------------------------------
    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ToolSearchPolicy":
        for key in _REQUIRED_FIELDS:
            if key not in raw:
                raise PolicyError(f"policy is missing required field: {key!r}")

        weights = raw["field_weights"]
        if set(weights) != _REQUIRED_WEIGHT_FIELDS:
            raise PolicyError(
                f"field_weights must cover exactly {sorted(_REQUIRED_WEIGHT_FIELDS)}, got {sorted(weights)}"
            )

        for table_name in _KEYED_TABLES:
            for key in raw[table_name]:
                if not POLICY_KEY_RE.match(key):
                    raise PolicyError(
                        f"{table_name} key {key!r} must be '{{kind}}:{{server}}:{{name}}' "
                        "or '{kind}:{server}:*' (bare tool names are rejected because "
                        "names can collide across MCP servers)"
                    )

        for key, mode in raw["pins"].items():
            if mode not in _VALID_PIN_MODES:
                raise PolicyError(f"pins[{key!r}] = {mode!r} is not one of {_VALID_PIN_MODES}")

        for step_key, override in raw["step_overrides"].items():
            mode = override.get("mode")
            if mode not in _VALID_STEP_MODES:
                raise PolicyError(
                    f"step_overrides[{step_key!r}].mode = {mode!r} is not one of {_VALID_STEP_MODES}"
                )

        limit, max_limit = int(raw["limit"]), int(raw["max_limit"])
        if not 1 <= limit <= max_limit:
            raise PolicyError(f"require 1 <= limit <= max_limit, got {limit} and {max_limit}")
        tau = float(raw["tau"])
        if not 0.0 <= tau <= 1.0:
            raise PolicyError(f"tau must be within [0.0, 1.0], got {tau}")

        present_routing_fields = set(raw) & set(_RESOURCE_ROUTING_FIELDS)
        if present_routing_fields and present_routing_fields != set(_RESOURCE_ROUTING_FIELDS):
            missing = next(
                name for name in _RESOURCE_ROUTING_FIELDS if name not in present_routing_fields
            )
            raise PolicyError(f"policy is missing required field: {missing!r}")

        if present_routing_fields:
            resource_classifications = _validate_resource_classifications(
                raw["resource_classifications"]
            )
            knowledge_tool_allowlists = _validate_tool_allowlists(
                raw["knowledge_tool_allowlists"],
                field_name="knowledge_tool_allowlists",
            )
            software_engineering_tool_allowlists = _validate_tool_allowlists(
                raw["software_engineering_tool_allowlists"],
                field_name="software_engineering_tool_allowlists",
            )
        else:
            # FR-TS-03 のランキング専用 policy は後方互換のため引き続き受理する。
            resource_classifications = {kind: {} for kind in RESOURCE_KINDS}
            knowledge_tool_allowlists = {}
            software_engineering_tool_allowlists = {}

        required_mcp_servers_by_skill = _validate_required_mcp_servers_by_skill(
            raw.get(_REQUIRED_MCP_SERVERS_BY_SKILL_FIELD, {})
        )

        known_fields = (
            set(_REQUIRED_FIELDS)
            | set(_RESOURCE_ROUTING_FIELDS)
            | {_REQUIRED_MCP_SERVERS_BY_SKILL_FIELD}
        )
        extra_top_level = {key: value for key, value in raw.items() if key not in known_fields}

        return cls(
            version=int(raw["version"]),
            limit=limit,
            max_limit=max_limit,
            tau=tau,
            field_weights={k: float(v) for k, v in weights.items()},
            pins=dict(raw["pins"]),
            additional_search_text=dict(raw["additional_search_text"]),
            step_overrides={k: dict(v) for k, v in raw["step_overrides"].items()},
            resource_classifications=resource_classifications,
            knowledge_tool_allowlists=knowledge_tool_allowlists,
            software_engineering_tool_allowlists=software_engineering_tool_allowlists,
            required_mcp_servers_by_skill=required_mcp_servers_by_skill,
            extra_top_level=extra_top_level,
        )

    @staticmethod
    def default_path(repo_root: Path | str | None = None) -> Path:
        """`policy.json` の場所。表示側がパス規則を再実装しないための単一経路。

        ``repo_root`` を渡したとき、そのリポジトリに ``.toolsearch/policy.json`` が
        あればそれを優先する（別リポジトリで使うときの上書き経路）。
        """
        if repo_root is not None:
            local = Path(repo_root) / LOG_DIRNAME / "policy.json"
            if local.is_file():
                return local
        return _POLICY_FILE

    @classmethod
    def load(
        cls,
        path: Path | str | None = None,
        *,
        repo_root: Path | str | None = None,
    ) -> "ToolSearchPolicy":
        target = Path(path) if path is not None else cls.default_path(repo_root)
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except OSError as exc:
            raise PolicyError(f"cannot read policy file: {target}") from exc
        except json.JSONDecodeError as exc:
            raise PolicyError(f"policy file is not valid JSON: {target}") from exc
        return cls.from_dict(raw)

    # --- 書き戻し ---------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """`from_dict()` が受け付ける形へ戻す。"""
        return {
            **self.extra_top_level,
            "version": self.version,
            "limit": self.limit,
            "max_limit": self.max_limit,
            "tau": self.tau,
            "field_weights": dict(self.field_weights),
            "pins": dict(self.pins),
            "additional_search_text": dict(self.additional_search_text),
            "step_overrides": {k: dict(v) for k, v in self.step_overrides.items()},
            "resource_classifications": {
                kind: dict(self.resource_classifications.get(kind, {}))
                for kind in RESOURCE_KINDS
            },
            "knowledge_tool_allowlists": {
                server: list(tools)
                for server, tools in self.knowledge_tool_allowlists.items()
            },
            "software_engineering_tool_allowlists": {
                server: list(tools)
                for server, tools in self.software_engineering_tool_allowlists.items()
            },
            "required_mcp_servers_by_skill": {
                skill: list(servers)
                for skill, servers in self.required_mcp_servers_by_skill.items()
            },
        }

    def save(self, path: Path | str) -> None:
        """検証を通してから既存ファイルへ書き戻す（不正なら 1 バイトも書かない）。

        `_comment` のような未知のトップレベルキーを保持するため、既存の内容へ
        既知フィールドだけを重ねる。既存ファイルが読めない場合は保持を保証
        できないため ``PolicyError`` を送出して書き込まない。
        """
        target = Path(path)
        payload = self.to_dict()
        # 生成物ではなく from_dict と同じ経路で検証する（GUI と CLI で判定を分けない）。
        ToolSearchPolicy.from_dict(payload)

        existing: dict[str, Any] = {}
        if target.exists():
            try:
                loaded = json.loads(target.read_text(encoding="utf-8"))
            except OSError as exc:
                raise PolicyError(f"cannot read policy file: {target}") from exc
            except json.JSONDecodeError as exc:
                raise PolicyError(f"policy file is not valid JSON: {target}") from exc
            if not isinstance(loaded, dict):
                raise PolicyError(f"policy file is not a JSON object: {target}")
            existing = loaded

        existing.update(payload)
        target.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    # --- 参照 -------------------------------------------------------------
    def pin_for(self, entry_id: str) -> PinMode:
        return resolve_policy_value(entry_id, self.pins, "auto")

    def search_text_for(self, entry_id: str) -> str:
        return resolve_policy_value(entry_id, self.additional_search_text, "")

    def effective_limit(self, requested: int | None = None) -> int:
        if requested is None:
            return self.limit
        return max(1, min(int(requested), self.max_limit))

    def mode_for_step(self, workflow_id: str | None, step_id: str | None) -> str:
        """`search` か `pin_only` を返す。step 指定が無ければ `search`。"""
        if not workflow_id or not step_id:
            return "search"
        override = self.step_overrides.get(f"{workflow_id}:{step_id}")
        if not override:
            return "search"
        return str(override.get("mode", "search"))

    def classification_for(
        self,
        resource_kind: str,
        resource_name: str,
        *,
        owner_plugin: str | None = None,
    ) -> str:
        """exact resource、owner Plugin、未分類の順で分類を解決する。"""
        if resource_kind not in RESOURCE_KINDS:
            raise PolicyError(f"unknown resource kind: {resource_kind!r}")

        exact = self.resource_classifications.get(resource_kind, {}).get(resource_name)
        if exact is not None:
            return exact
        if resource_kind in ("mcp_servers", "skills") and owner_plugin is not None:
            owner = self.resource_classifications.get("plugins", {}).get(owner_plugin)
            if owner is not None:
                return owner
        return "unclassified"

    def classification_allowed(self, workflow_id: str, classification: str) -> bool:
        """Workflow で分類済み resource を公開候補にできるか判定する。"""
        if workflow_id not in KNOWLEDGE_WORKFLOW_IDS:
            raise PolicyError(f"unknown workflow: {workflow_id!r}")
        if classification not in RESOURCE_CLASSIFICATIONS:
            raise PolicyError(f"unknown resource classification: {classification!r}")
        if classification == "knowledge":
            return True
        if classification == "software-engineering":
            return workflow_id in SOFTWARE_ENGINEERING_WORKFLOW_IDS
        if classification == "both":
            # `SOFTWARE_ENGINEERING_WORKFLOW_IDS` は `KNOWLEDGE_WORKFLOW_IDS` の部分集合で、
            # 未登録 Workflow は冒頭で拒否済みのため、ここに来た時点で常に候補となる。
            return True
        return False

    def tool_allowlist_for(self, classification: str, server_name: str) -> tuple[str, ...]:
        """category と exact MCP server 名に対応する bare tool allowlist を返す。"""
        if classification == "knowledge":
            return tuple(self.knowledge_tool_allowlists.get(server_name, ()))
        if classification == "software-engineering":
            return tuple(self.software_engineering_tool_allowlists.get(server_name, ()))
        raise PolicyError(f"tool allowlist has no category for classification {classification!r}")

    def required_mcp_servers_for_skills(
        self,
        skill_names: Iterable[str],
    ) -> tuple[str, ...]:
        """Resolve exact MCP dependencies for required Skills without guessing names."""
        required: list[str] = []
        for raw_name in skill_names:
            skill_name = str(raw_name)
            servers = tuple(self.required_mcp_servers_by_skill.get(skill_name, ()))
            if skill_name in _MCP_DEPENDENT_REQUIRED_SKILLS and not servers:
                raise PolicyError(
                    "policy is missing required_mcp_servers_by_skill mapping for "
                    f"required Skill {skill_name!r}"
                )
            for server_name in servers:
                if server_name not in required:
                    required.append(server_name)
        return tuple(required)


def apply_policy(
    entries: Sequence[ToolEntry],
    policy: ToolSearchPolicy,
    *,
    excluded_tools: Iterable[str] | None = None,
    pin_only: bool = False,
    manifest_pins: Mapping[str, PinMode] | None = None,
    auto_pins: Iterable[str] | None = None,
) -> PolicyDecision:
    """`ToolEntry` 列へ pin と検索語彙を適用し、pin / 検索対象へ振り分ける。

    優先順位（FR-TS-03、高→低）:
    ``excluded_tools`` > ``manifest_pins`` > ``policy.pins`` > ``auto_pins`` > 検索結果。

    ``auto_pins`` は利用履歴による昇格（FR-TS-07）。``policy.pins`` が ``auto`` のときだけ
    適用する（``always`` / ``never`` の明示指定を上書きしない）。

    `pin_only=True`（fail-closed Step）のときは検索対象を空にする。ただしこれは
    「返さない」だけであり、呼び出しの禁止ではない（モジュール docstring 参照）。
    """
    excluded = {str(name) for name in (excluded_tools or ())}
    overrides = dict(manifest_pins or {})
    promoted = {str(tool_id) for tool_id in (auto_pins or ())}
    pinned: list[ToolEntry] = []
    searchable: list[ToolEntry] = []
    dropped: list[str] = []

    for entry in entries:
        if entry.name in excluded or entry.id in excluded:
            dropped.append(entry.id)
            continue
        pin: PinMode = overrides.get(entry.id) or policy.pin_for(entry.id)
        if pin == "auto" and entry.id in promoted:
            pin = "always"
        resolved = dataclasses.replace(
            entry,
            additional_search_text=policy.search_text_for(entry.id) or entry.additional_search_text,
            pin=pin,
        )
        if pin == "always":
            pinned.append(resolved)
        else:
            # auto / never のどちらも検索対象。差は自動 pin の対象になるかだけ。
            searchable.append(resolved)

    if pin_only:
        searchable = []

    return PolicyDecision(
        pinned=tuple(pinned),
        searchable=tuple(searchable),
        dropped=tuple(dropped),
    )
