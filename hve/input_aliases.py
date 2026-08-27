"""hve.input_aliases — Prompt 版の実行時入力別名（canonical → actual、FR-PROMPT-08 / 09）。

canonical 契約（`StepDef.required_input_paths` と `.github/io-contracts/`）は変更せず、
**その run に限って** canonical 入力をリポジトリ内の実ファイルへ読み替える。ファイルの
コピーも出力契約の書き換えも行わない。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    from .workflow_registry import expand_group_step_ids, get_workflow
    from .prompt_loader import load_prompt_file
except ImportError:  # pragma: no cover - script 実行経路
    from workflow_registry import expand_group_step_ids, get_workflow  # type: ignore[no-redef]
    from prompt_loader import load_prompt_file  # type: ignore[no-redef]

_GLOB_CHARS = ("*", "?", "[")
_PLACEHOLDER_CHARS = ("{", "}")


class InputAliasError(ValueError):
    """入力別名が v1 の契約を満たさないことを表す。fail-closed で実行を止める。"""


@dataclass(frozen=True)
class ResolvedAlias:
    canonical: str
    actual: str


def _norm(value: Any, where: str) -> str:
    if not isinstance(value, str):
        raise InputAliasError(f"{where} は文字列でなければなりません: {value!r}")
    text = value.replace("\\", "/").strip()
    if not text:
        raise InputAliasError(f"{where} が空です。")
    return text


def normalize_alias_pairs(pairs: Iterable[Sequence[Any]]) -> Tuple[ResolvedAlias, ...]:
    """`(canonical, actual)` の並びを正規化する。宣言順を保持する。"""
    aliases: List[ResolvedAlias] = []
    seen: set[str] = set()
    for index, pair in enumerate(pairs):
        if isinstance(pair, ResolvedAlias):
            canonical, actual = pair.canonical, pair.actual
        else:
            items = list(pair)
            if len(items) != 2:
                raise InputAliasError(
                    f"input_aliases[{index}] は CANONICAL と ACTUAL の 2 要素で指定してください。"
                )
            canonical, actual = items
        canonical = _norm(canonical, f"input_aliases[{index}].canonical")
        actual = _norm(actual, f"input_aliases[{index}].actual")
        if canonical in seen:
            raise InputAliasError(f"同じ canonical に複数の別名が指定されています: {canonical}")
        seen.add(canonical)
        aliases.append(ResolvedAlias(canonical=canonical, actual=actual))
    return tuple(aliases)


def _active_steps(workflow_id: str, step_ids: Sequence[str]):
    wf = get_workflow(workflow_id)
    if wf is None:
        raise InputAliasError(f"未知の Workflow です: {workflow_id!r}")
    # CLI / GUI は表示グループ ID（"1"〜"5" 等）を渡しうるため実 Step ID へ展開する。
    selected = {s for s in expand_group_step_ids(workflow_id, list(step_ids)) if s}
    if not selected:
        return list(wf.steps)
    return [s for s in wf.steps if s.id in selected]


def _check_canonical_shape(canonical: str) -> None:
    if any(ch in canonical for ch in _GLOB_CHARS):
        raise InputAliasError(
            f"v1 は glob パターンの別名に対応していません: {canonical}"
        )
    if any(ch in canonical for ch in _PLACEHOLDER_CHARS):
        raise InputAliasError(
            f"v1 は placeholder を含む入力の別名に対応していません: {canonical}"
        )
    if canonical.endswith("/"):
        raise InputAliasError(
            f"v1 はディレクトリ入力の別名に対応していません: {canonical}"
        )


def _check_actual_path(actual: str, repo_root: Path) -> None:
    if actual.startswith("/") or os.path.splitdrive(actual)[0]:
        raise InputAliasError(f"別名の実ファイルは相対パスで指定してください: {actual}")
    if any(part == ".." for part in actual.split("/")):
        raise InputAliasError(f"別名の実ファイルに '..' は使用できません: {actual}")

    root = repo_root.resolve()
    target = (root / actual)
    if target.is_symlink():
        raise InputAliasError(f"別名の実ファイルに symlink は指定できません: {actual}")
    if not target.exists():
        raise InputAliasError(f"別名の実ファイルが存在しません: {actual}")
    if not target.is_file():
        raise InputAliasError(f"別名の実ファイルは通常ファイルでなければなりません: {actual}")
    try:
        resolved = target.resolve(strict=True)
    except OSError as exc:  # pragma: no cover - 実行環境依存の縮退
        raise InputAliasError(f"別名の実ファイルを解決できません: {actual} ({exc})") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise InputAliasError(f"別名の実ファイルがリポジトリ外を指しています: {actual}") from exc


def validate_aliases(
    aliases: Sequence[ResolvedAlias],
    *,
    workflow_id: str,
    step_ids: Sequence[str],
    repo_root: "str | Path",
) -> Tuple[ResolvedAlias, ...]:
    """active Step のリテラル入力・path 安全性・producer 衝突を検証する。"""
    root = Path(repo_root)
    steps = _active_steps(workflow_id, step_ids)

    literal_inputs: set[str] = set()
    produced: set[str] = set()
    for step in steps:
        for path in step.required_input_paths or []:
            normalized = path.replace("\\", "/")
            if not any(ch in normalized for ch in _GLOB_CHARS + _PLACEHOLDER_CHARS) and not normalized.endswith("/"):
                literal_inputs.add(normalized)
        for path in list(step.output_paths or []) + list(
            getattr(step, "output_paths_template", None) or []
        ):
            produced.add(path.replace("\\", "/"))

    for alias in aliases:
        if alias.canonical not in literal_inputs:
            # glob / placeholder / ディレクトリは v1 非対応として固有の理由で拒否する。
            _check_canonical_shape(alias.canonical)
            raise InputAliasError(
                "別名の canonical が、選択された Step の required_input_paths に"
                f"リテラルで存在しません: {alias.canonical}"
            )
        if alias.canonical in produced:
            raise InputAliasError(
                "選択された Step が生成する成果物は別名で差し替えられません: "
                f"{alias.canonical}"
            )
        _check_actual_path(alias.actual, root)

    return tuple(aliases)


class AliasResolver:
    """canonical path を actual path へ読み替える単一の解決器（FR-PROMPT-09）。"""

    __slots__ = ("_by_canonical", "_aliases")

    def __init__(self, aliases: Sequence[ResolvedAlias] = ()):
        self._aliases: Tuple[ResolvedAlias, ...] = tuple(aliases)
        self._by_canonical = {a.canonical: a.actual for a in self._aliases}

    def __bool__(self) -> bool:
        return bool(self._by_canonical)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, AliasResolver) and other._aliases == self._aliases

    @property
    def aliases(self) -> Tuple[ResolvedAlias, ...]:
        return self._aliases

    def actual_for(self, canonical: str) -> Optional[str]:
        return self._by_canonical.get((canonical or "").replace("\\", "/"))

    def resolve_paths(self, paths: Iterable[str]) -> List[str]:
        out: List[str] = []
        for path in paths:
            normalized = (path or "").replace("\\", "/")
            out.append(self._by_canonical.get(normalized, normalized))
        return out

    def aliases_for_paths(self, paths: Iterable[str]) -> Tuple[ResolvedAlias, ...]:
        """与えられた canonical 群に関係する別名だけを宣言順で返す。"""
        wanted = {(p or "").replace("\\", "/") for p in paths}
        return tuple(a for a in self._aliases if a.canonical in wanted)


def resolver_from_params(params: Mapping[str, Any]) -> AliasResolver:
    """workflow params の `input_aliases` から解決器を組み立てる。"""
    raw = (params or {}).get("input_aliases") or ()
    if isinstance(raw, AliasResolver):
        return raw
    return AliasResolver(normalize_alias_pairs(raw))


def build_alias_addendum(step: Any, resolver: AliasResolver) -> str:
    """当該 Step に関係する別名だけを説明する決定的な addendum を返す。

    ファイル本文は埋め込まない（NFR-CTX-01）。関係する別名が無ければ空文字列。
    """
    if not resolver:
        return ""
    related = resolver.aliases_for_paths(getattr(step, "required_input_paths", None) or [])
    if not related:
        return ""
    lines = load_prompt_file("runtime/addenda/input-aliases.prompt.md").splitlines()
    if len(lines) < 3:
        raise InputAliasError(
            "input alias addendum template が不正です: runtime/addenda/input-aliases.prompt.md"
        )
    lines += ["", *(f"- `{a.canonical}` → `{a.actual}`" for a in related)]
    return "\n".join(lines)
