"""FR-WF-OUT-10: prefix 存在ゲートによる検証回復の契約テスト。

FR-WF-OUT-06 の fail-closed drop は誤 fail を防ぐ一方で、名称スラッグを含む
エントリの検証を **完全に消していた**（FR-WF-OUT-09）。本テストは、drop された
エントリのうち **fan-out キーを実際に含むもの** を prefix 存在ゲートへ降格して
検証を回復する契約を固定する。

根拠（実地の証拠）:
    単一 run `ed3931b8` の生成物が `docs/services/` だけで 3 形式に分岐している。

        SVC-01-member-consent-service-description.md   {id}-{slug}-description.md
        SVC-02-description.md                          {id}-description.md
        SVC-09.md                                      {id}.md

    完全パス一致でも glob 一致でも誤 fail するが、**全件が ID 接頭辞で始まる**
    点は一貫している。したがって接頭辞一致だけが誤 fail なしに「当該キーの
    成果物が存在するか」を検証できる。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hve.fanout_expander import resolve_output_path_prefix_gates  # noqa: E402
from hve.workflow_registry import get_workflow  # noqa: E402


class _Step:
    """prefix ゲート判定に必要な属性だけを持つ最小の StepDef 代替。"""

    def __init__(
        self,
        output_paths_template: list[str] | None,
        fanout_parser: str | None = None,
        fanout_static_keys: list[str] | None = None,
        fanout_key: str = "",
    ) -> None:
        self.output_paths_template = output_paths_template
        self.fanout_parser = fanout_parser
        self.fanout_static_keys = fanout_static_keys
        self.fanout_key = fanout_key


# ---------------------------------------------------------------------------
# 降格の基本規則
# ---------------------------------------------------------------------------


def test_name_slug_entry_is_demoted_to_a_key_prefix_gate() -> None:
    """未解決スラッグを含むエントリはキー出現位置までの接頭辞ゲートになる。"""
    step = _Step(
        ["docs/services/{serviceId}-{serviceNameSlug}-description.md"],
        fanout_parser="service_catalog",
        fanout_key="SVC-01",
    )

    assert resolve_output_path_prefix_gates(step) == ["docs/services/SVC-01"]


def test_directory_entry_is_demoted_to_a_key_prefix_gate() -> None:
    """ディレクトリ参照（FR-WF-OUT-06 規則 4）も接頭辞ゲートで回復する。"""
    step = _Step(
        ["src/api/{serviceId}-{serviceNameSlug}/"],
        fanout_parser="service_catalog",
        fanout_key="SVC-01",
    )

    assert resolve_output_path_prefix_gates(step) == ["src/api/SVC-01"]


def test_glob_entry_is_demoted_to_a_key_prefix_gate() -> None:
    """glob（規則 3）も接頭辞ゲートで回復する。"""
    step = _Step(
        ["knowledge/{key}-*.md"],
        fanout_static_keys=["D01"],
        fanout_key="D01",
    )

    assert resolve_output_path_prefix_gates(step) == ["knowledge/D01"]


# ---------------------------------------------------------------------------
# 降格してはならないもの
# ---------------------------------------------------------------------------


def test_entry_without_a_key_alias_is_not_demoted() -> None:
    """キー別名を含まない固定パスは per-key 成果物でないため降格しない。"""
    step = _Step(
        ["src/app/package.json", "src/app/main.js"],
        fanout_parser="screen_catalog",
        fanout_key="APP-009-S001",
    )

    assert resolve_output_path_prefix_gates(step) == []


def test_entry_whose_key_is_never_substituted_is_not_demoted() -> None:
    """parser が返さない ID 名（ADFDV の `{jobId}`）は代入されないため降格しない。"""
    step = _Step(
        ["src/dataflow/{jobId}-{jobNameSlug}/"],
        fanout_parser="dataflow_catalog",
        fanout_key="APP-009",
    )

    assert resolve_output_path_prefix_gates(step) == []


def test_fully_resolved_entry_is_not_demoted() -> None:
    """確定パスへ解決できるエントリは通常ゲートが担うため降格しない。"""
    step = _Step(
        ["docs/catalog/screen-catalog-{key}.md"],
        fanout_parser="app_catalog",
        fanout_key="APP-009",
    )

    assert resolve_output_path_prefix_gates(step) == []


def test_non_fanout_step_has_no_prefix_gate() -> None:
    """fan-out していない Step は代入するキーが無いため対象外。"""
    step = _Step(["docs/services/{serviceId}-{serviceNameSlug}-description.md"])

    assert resolve_output_path_prefix_gates(step) == []


def test_prefix_gates_are_deduplicated() -> None:
    """同一接頭辞へ落ちる複数エントリは 1 件へ集約する。"""
    step = _Step(
        [
            "src/test/dataflow/{serviceId}-{serviceNameSlug}.Tests/",
            "src/test/dataflow/{serviceId}-{serviceNameSlug}.Tests/README.md",
        ],
        fanout_parser="service_catalog",
        fanout_key="SVC-01",
    )

    assert resolve_output_path_prefix_gates(step) == ["src/test/dataflow/SVC-01"]


# ---------------------------------------------------------------------------
# 実地データに対する誤 fail 検証
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("prefix", "reason"),
    (
        ("docs/services/SVC-01", "{id}-{slug}-description.md 形式"),
        ("docs/services/SVC-02", "{id}-description.md 形式"),
        ("docs/services/SVC-09", "{id}.md 形式"),
        ("docs/screen/APP-009-S001", "画面定義書"),
        ("src/api/SVC-01", "ディレクトリ成果物"),
    ),
)
def test_prefix_gate_matches_every_observed_naming_variant(
    prefix: str, reason: str
) -> None:
    """3 形式に分岐した実在成果物のすべてに接頭辞が一致する（誤 fail しない）。"""
    repo_root = Path(__file__).resolve().parents[2]
    parent = repo_root / Path(prefix).parent
    stem = Path(prefix).name

    matches = [p for p in parent.glob(f"{stem}*")] if parent.is_dir() else []

    assert matches, f"{prefix}* に一致する成果物が無い（{reason}）"


# ---------------------------------------------------------------------------
# レジストリ実データ
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("workflow_id", "step_id", "key", "expected"),
    (
        ("aad-web", "2.1", "APP-009-S001", ["docs/screen/APP-009-S001"]),
        ("aad-web", "2.2", "SVC-01", ["docs/services/SVC-01"]),
        ("asdw-web", "3.3", "SVC-01", ["src/api/SVC-01"]),
    ),
)
def test_registry_steps_recover_their_gate_via_prefix(
    workflow_id: str, step_id: str, key: str, expected: list[str]
) -> None:
    """レジストリ実定義でも検証が回復すること。"""
    workflow = get_workflow(workflow_id)
    base = next(s for s in workflow.steps if s.id == step_id)
    step = _Step(
        list(base.output_paths_template or []),
        fanout_parser=getattr(base, "fanout_parser", None),
        fanout_static_keys=getattr(base, "fanout_static_keys", None),
        fanout_key=key,
    )

    assert resolve_output_path_prefix_gates(step) == expected
