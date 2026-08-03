"""`output_paths_template` の宣言が解決可能な形であることを固定する。

live canary 前の調査で、宣言済みテンプレートに 2 種類の欠陥が見つかった。

1. **非 fan-out Step が fan-out プレースホルダを宣言している**
   `asdw-web 3.4`（`fanout_parser=None`）が `src/test/{serviceId}-{serviceNameSlug}/`
   を宣言していた。fan-out しない Step ではキー別名を代入する機会が無いため、
   このエントリは永久に解決されず、[hve/fanout_expander.py](hve/fanout_expander.py)
   の fail-closed drop 規則で必ず捨てられる。実際に `src/test/` 直下へ当該
   ディレクトリが作られたことも無い（実在するのは `api` / `integration` / `ui`）。

2. **実際の命名規約と異なるプレースホルダを使っている**
   `asdw-web 3.2` が `src/test/api/{serviceNameSlug}.Tests/` を宣言していたが、
   ASDW-WEB 実行後に実在するのは `SVC-01.Tests` 〜 `SVC-23.Tests` の 8 件で、
   いずれも **serviceId** による命名だった。`{serviceId}-{serviceNameSlug}` 形式を
   採る `src/api/SVC-01-member-consent-service/` とは規約が異なる。

いずれも現状は fail-closed drop により実行時ゲートから外れるため実害が出ていないが、
`{serviceNameSlug}` の解決を実装した時点で **存在しないパスを必須化して実行時に
false-fail する**。宣言の正しさを先に固定しておく。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hve.fanout_expander import (  # noqa: E402
    _KEY_ALIAS_PLACEHOLDERS_BY_PARSER,
    _key_placeholder_names,
    _resolve_output_path_template,
    resolve_output_path_prefix_gates,
)
from hve.workflow_registry import get_workflow, list_workflows  # noqa: E402


class _KeyedStep:
    """fan-out キーを与えた StepDef ビュー（prefix ゲート判定用）。"""

    def __init__(self, step: object, key: str) -> None:
        self._step = step
        self.fanout_key = key

    def __getattr__(self, name: str) -> object:
        return getattr(self._step, name)

_PLACEHOLDER = re.compile(r"\{([A-Za-z][A-Za-z0-9_]*)\}")
_ALL_KEY_ALIASES = {
    alias.strip("{}")
    for aliases in _KEY_ALIAS_PLACEHOLDERS_BY_PARSER.values()
    for alias in (aliases if isinstance(aliases, (list, tuple, set)) else [aliases])
}


def _has_fanout(step) -> bool:
    """fan-out の有無。

    fan-out は parser 経由（`fanout_parser`）だけでなく、固定キー集合
    （`fanout_static_keys`。AKM / AQOD の D01〜D21 など）でも成立する。
    どちらかを持てばキー別名を代入できる。
    """
    return bool(
        getattr(step, "fanout_parser", None)
        or getattr(step, "fanout_static_keys", None)
    )


def _fanout_steps_declaring_key_aliases() -> list[tuple[str, str, str, set[str]]]:
    findings: list[tuple[str, str, str, set[str]]] = []
    for workflow in list_workflows():
        for step in workflow.steps:
            if _has_fanout(step):
                continue
            for template in getattr(step, "output_paths_template", None) or []:
                names = set(_PLACEHOLDER.findall(template)) & (_ALL_KEY_ALIASES | {"key"})
                if names:
                    findings.append((workflow.id, step.id, template, names))
    return findings


def test_non_fanout_steps_do_not_declare_fanout_placeholders() -> None:
    """fan-out しない Step はキー別名を代入できないため宣言してはならない。"""
    findings = _fanout_steps_declaring_key_aliases()

    assert findings == [], (
        "非 fan-out Step が fan-out プレースホルダを宣言している（永久に解決されない）: "
        + ", ".join(f"{w} {s}: {t} -> {sorted(n)}" for w, s, t, n in findings)
    )


def test_static_key_fanout_steps_may_declare_key_placeholders() -> None:
    """`fanout_static_keys` の Step は `{key}` を宣言してよい（誤検知防止）。"""
    static_key_steps = [
        (workflow.id, step.id)
        for workflow in list_workflows()
        for step in workflow.steps
        if getattr(step, "fanout_static_keys", None)
        and any("{key}" in t for t in (getattr(step, "output_paths_template", None) or []))
    ]

    assert static_key_steps, (
        "`fanout_static_keys` で `{key}` を宣言する Step が存在しない（前提が変わっている）"
    )


@pytest.mark.parametrize(
    ("workflow_id", "step_id", "expected"),
    (
        ("asdw-web", "3.2", "src/test/api/{serviceId}.Tests/"),
        ("asdw-web", "3.2", "src/test/api/{serviceId}.Tests/README.md"),
    ),
)
def test_service_test_project_paths_use_the_service_id(
    workflow_id: str, step_id: str, expected: str
) -> None:
    """テストプロジェクトは serviceId で命名される（実在 8 ディレクトリで確認済み）。"""
    step = next(s for s in get_workflow(workflow_id).steps if s.id == step_id)
    templates = list(getattr(step, "output_paths_template", None) or [])

    assert expected in templates, (
        f"{workflow_id} {step_id} が {expected} を宣言していない: {templates}"
    )


def test_service_test_project_paths_do_not_use_the_name_slug() -> None:
    """`{serviceNameSlug}.Tests` は実在しない命名規約。"""
    step = next(s for s in get_workflow("asdw-web").steps if s.id == "3.2")
    templates = list(getattr(step, "output_paths_template", None) or [])

    assert not any("{serviceNameSlug}.Tests" in t for t in templates), (
        f"実在しない命名規約を宣言している: {templates}"
    )


# ---------------------------------------------------------------------------
# ゲートへ 1 件も載らない宣言（sentinel）
# ---------------------------------------------------------------------------
# `{screenNameSlug}` / `{serviceNameSlug}` / `{jobNameSlug}` は
# **日本語カタログ名の英訳** であり、catalog parser からは決定的に復元できない。
#
#   docs/catalog/service-catalog.md: `| SVC-01 | 会員・同意管理サービス | ... |`
#   実在ファイル                    : `docs/services/SVC-01-member-consent-service-description.md`
#
# 訳語は Agent が生成するため、parser を拡張しても機械的には求められない。
# したがって [hve/fanout_expander.py](hve/fanout_expander.py) の fail-closed drop
# により、これらの宣言は **恒久的に** ゲートへ載らない。
#
# 実害は「誤 fail」ではなく「宣言があるのにゲートが無言で空になる」こと。
# 気付かないまま新しい no-op 宣言が増えるのを防ぐため、空になる宣言を
# 明示 allowlist として固定する。allowlist に無い Step が空になったら CI で落とす。
#
# なお FR-WF-OUT-10 の prefix 存在ゲートにより、**fan-out キーを実際に含む**
# エントリは「キー接頭辞に前方一致する成果物があるか」で検証が回復している
# （AAD-WEB 2.1 / 2.2、ASDW-WEB 3.3、AKM 1）。ここに残るのは prefix 化しても
# 検証できない Step だけである。
_EMPTY_GATE_ALLOWLIST: dict[tuple[str, str], str] = {
    ("adfdv", "2.1"): "{jobId} が dataflow_catalog の返す APP-ID と不一致でキーが代入されず、prefix 化もできない（FR-WF-ADFDV-01/02）",
    ("adfdv", "2.2"): "{jobId} が dataflow_catalog の返す APP-ID と不一致でキーが代入されず、prefix 化もできない（FR-WF-ADFDV-01/02）",
    ("asdw-web", "4.2"): "src/app/ 配下は全 fan-out 子で同一の固定パスで per-key 成果物でない（規則 1）",
}

_SAMPLE_FANOUT_KEYS = ("SVC-01", "APP-009", "APP-009-S001", "D01")


def _fanout_steps_with_empty_gate() -> list[tuple[str, str]]:
    """fan-out する Step のうち、通常ゲートも prefix ゲートも空になる宣言を返す。"""
    empty: list[tuple[str, str]] = []
    for workflow in list_workflows():
        for step in workflow.steps:
            templates = list(getattr(step, "output_paths_template", None) or [])
            if not templates or not _has_fanout(step):
                continue
            names = _key_placeholder_names(step)
            resolved = [
                _resolve_output_path_template(template, key, names)
                for key in _SAMPLE_FANOUT_KEYS
                for template in templates
            ]
            if any(resolved):
                continue
            if any(
                resolve_output_path_prefix_gates(_KeyedStep(step, key))
                for key in _SAMPLE_FANOUT_KEYS
            ):
                continue
            empty.append((workflow.id, step.id))
    return empty


def test_empty_output_gate_steps_match_the_documented_allowlist() -> None:
    """ゲートが空になる fan-out Step は allowlist と完全一致する。"""
    actual = set(_fanout_steps_with_empty_gate())
    expected = set(_EMPTY_GATE_ALLOWLIST)

    assert actual == expected, (
        "output_paths ゲートが無言で空になる Step の集合が allowlist と一致しない。"
        f" 新たに空になった: {sorted(actual - expected)} /"
        f" 解決可能になった（allowlist から削除すること）: {sorted(expected - actual)}"
    )


@pytest.mark.parametrize(("workflow_id", "step_id"), sorted(_EMPTY_GATE_ALLOWLIST))
def test_empty_gate_allowlist_entries_are_real_steps(
    workflow_id: str, step_id: str
) -> None:
    """allowlist は実在 Step のみを指し、理由が記載されている。"""
    workflow = get_workflow(workflow_id)
    assert workflow is not None, f"未知の workflow: {workflow_id}"

    step_ids = [s.id for s in workflow.steps]
    assert step_id in step_ids, f"{workflow_id} に Step {step_id} が無い: {step_ids}"
    assert _EMPTY_GATE_ALLOWLIST[(workflow_id, step_id)].strip(), "理由が空"


def test_name_slug_placeholders_are_not_registered_as_key_aliases() -> None:
    """名称スラッグをキー別名として登録してはならない（実在しないパスの必須化を防ぐ）。"""
    registered = {
        alias
        for aliases in _KEY_ALIAS_PLACEHOLDERS_BY_PARSER.values()
        for alias in aliases
    }
    slug_aliases = sorted(a for a in registered if a.lower().endswith("nameslug"))

    assert slug_aliases == [], (
        "名称スラッグは日本語カタログ名の英訳であり parser から復元できない。"
        f" キー別名に登録されている: {slug_aliases}"
    )
