"""FR-WF-OUT-10: `_check_output_paths_gate` の prefix ゲート適用契約テスト。

`resolve_output_path_prefix_gates` が返す接頭辞を、runner のゲートが
「前方一致するファイルまたはディレクトリが 1 件以上存在するか」で判定すること、
および `output_paths` の内容を変更しない（他の消費者へ影響しない）ことを固定する。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hve.artifact_validation import find_missing_output_paths  # noqa: E402
from hve.fanout_expander import FanoutChildStep  # noqa: E402
from hve.runner import _check_output_paths_gate  # noqa: E402


class _Ctx:
    split_fork_enabled = False


class _Workflow:
    def __init__(self, steps: list[object]) -> None:
        self.steps = steps


def _child(
    step_id: str,
    output_paths: list[str],
    output_paths_template: list[str] | None,
    fanout_key: str,
    fanout_parser: str | None = "service_catalog",
) -> FanoutChildStep:
    child = FanoutChildStep(
        id=step_id,
        title="t",
        custom_agent=None,
        depends_on=[],
        body_template_path=None,
        is_container=False,
        skip_fallback_deps=[],
        block_unless=[],
        consumed_artifacts=None,
        output_paths=output_paths,
        required_input_paths=[],
        fanout_key=fanout_key,
        base_step_id=step_id.split("/", 1)[0],
    )
    child.output_paths_template = output_paths_template
    child.fanout_parser = fanout_parser
    return child


def test_gate_passes_when_a_prefix_match_exists(tmp_path: Path) -> None:
    """接頭辞に前方一致する成果物があれば pass する。"""
    (tmp_path / "docs" / "services").mkdir(parents=True)
    (tmp_path / "docs" / "services" / "SVC-01-member-consent-service-description.md").write_text(
        "x", encoding="utf-8"
    )
    step = _child(
        "2.2/SVC-01",
        [],
        ["docs/services/{serviceId}-{serviceNameSlug}-description.md"],
        "SVC-01",
    )

    missing = _check_output_paths_gate(_Ctx(), _Workflow([step]), "2.2/SVC-01", tmp_path)

    assert missing == []


def test_gate_passes_for_every_observed_naming_variant(tmp_path: Path) -> None:
    """3 形式に分岐した命名のいずれでも pass する（誤 fail しない）。"""
    services = tmp_path / "docs" / "services"
    services.mkdir(parents=True)
    (services / "SVC-02-description.md").write_text("x", encoding="utf-8")
    (services / "SVC-09.md").write_text("x", encoding="utf-8")

    for key in ("SVC-02", "SVC-09"):
        step = _child(
            f"2.2/{key}",
            [],
            ["docs/services/{serviceId}-{serviceNameSlug}-description.md"],
            key,
        )

        missing = _check_output_paths_gate(
            _Ctx(), _Workflow([step]), f"2.2/{key}", tmp_path
        )

        assert missing == [], key


def test_gate_passes_when_a_directory_matches_the_prefix(tmp_path: Path) -> None:
    """ディレクトリ成果物も前方一致で検出する。"""
    (tmp_path / "src" / "api" / "SVC-01-member-consent-service").mkdir(parents=True)
    step = _child(
        "3.3/SVC-01",
        [],
        ["src/api/{serviceId}-{serviceNameSlug}/"],
        "SVC-01",
    )

    missing = _check_output_paths_gate(_Ctx(), _Workflow([step]), "3.3/SVC-01", tmp_path)

    assert missing == []


def test_gate_fails_when_no_artifact_matches_the_prefix(tmp_path: Path) -> None:
    """当該キーの成果物が 1 件も無ければ検出する（検証の回復）。"""
    (tmp_path / "docs" / "services").mkdir(parents=True)
    (tmp_path / "docs" / "services" / "SVC-02-description.md").write_text(
        "x", encoding="utf-8"
    )
    step = _child(
        "2.2/SVC-01",
        [],
        ["docs/services/{serviceId}-{serviceNameSlug}-description.md"],
        "SVC-01",
    )

    missing = _check_output_paths_gate(_Ctx(), _Workflow([step]), "2.2/SVC-01", tmp_path)

    assert missing == ["docs/services/SVC-01*"]


def test_gate_fails_when_the_parent_directory_is_absent(tmp_path: Path) -> None:
    """親ディレクトリごと存在しない場合も例外を出さず欠落として報告する。"""
    step = _child(
        "2.2/SVC-01",
        [],
        ["docs/services/{serviceId}-{serviceNameSlug}-description.md"],
        "SVC-01",
    )

    missing = _check_output_paths_gate(_Ctx(), _Workflow([step]), "2.2/SVC-01", tmp_path)

    assert missing == ["docs/services/SVC-01*"]


def test_prefix_gate_does_not_alter_output_paths(tmp_path: Path) -> None:
    """prefix ゲートは `output_paths` を書き換えない（他の消費者へ影響しない）。"""
    declared = ["docs/catalog/service-catalog.md"]
    step = _child(
        "2.2/SVC-01",
        list(declared),
        ["docs/services/{serviceId}-{serviceNameSlug}-description.md"],
        "SVC-01",
    )

    _check_output_paths_gate(_Ctx(), _Workflow([step]), "2.2/SVC-01", tmp_path)

    assert step.output_paths == declared


def test_concrete_and_prefix_gates_are_both_enforced(tmp_path: Path) -> None:
    """確定パスの欠落と prefix の欠落を両方報告する。"""
    step = _child(
        "2.2/SVC-01",
        ["docs/catalog/service-catalog.md"],
        ["docs/services/{serviceId}-{serviceNameSlug}-description.md"],
        "SVC-01",
    )

    missing = _check_output_paths_gate(_Ctx(), _Workflow([step]), "2.2/SVC-01", tmp_path)

    assert missing == ["docs/catalog/service-catalog.md", "docs/services/SVC-01*"]


def test_shared_helper_preserves_missing_display_without_side_effects(
    tmp_path: Path,
) -> None:
    """共有 helper は欠落表示を維持し、入力や filesystem を変更しない。"""
    declared = ["docs/catalog/service-catalog.md"]
    prefixes = ["docs/services/SVC-01"]

    missing = find_missing_output_paths(tmp_path, declared, prefixes)

    assert missing == ["docs/catalog/service-catalog.md", "docs/services/SVC-01*"]
    assert declared == ["docs/catalog/service-catalog.md"]
    assert prefixes == ["docs/services/SVC-01"]
    assert not (tmp_path / "docs").exists()


def test_shared_helper_treats_glob_metacharacters_as_literal_prefix(
    tmp_path: Path,
) -> None:
    services = tmp_path / "docs" / "services"
    services.mkdir(parents=True)
    (services / "A-decoy.md").write_text("decoy", encoding="utf-8")
    prefix = "docs/services/[AB]"

    assert find_missing_output_paths(tmp_path, (), (prefix,)) == [f"{prefix}*"]

    (services / "[AB]-literal.md").write_text("literal", encoding="utf-8")
    assert find_missing_output_paths(tmp_path, (), (prefix,)) == []


def test_gate_is_skipped_in_fleet_mode(tmp_path: Path) -> None:
    """fleet mode では FR-WF-OUT-01 と同様に prefix ゲートも適用しない。"""

    class _FleetCtx:
        split_fork_enabled = True

    step = _child(
        "2.2/SVC-01",
        [],
        ["docs/services/{serviceId}-{serviceNameSlug}-description.md"],
        "SVC-01",
    )

    missing = _check_output_paths_gate(
        _FleetCtx(), _Workflow([step]), "2.2/SVC-01", tmp_path
    )

    assert missing == []


def test_gate_is_skipped_in_standalone_mode(tmp_path: Path) -> None:
    """単独実行モード（ctx 未注入）でも適用しない。"""
    step = _child(
        "2.2/SVC-01",
        [],
        ["docs/services/{serviceId}-{serviceNameSlug}-description.md"],
        "SVC-01",
    )

    missing = _check_output_paths_gate(None, _Workflow([step]), "2.2/SVC-01", tmp_path)

    assert missing == []


def test_non_fanout_step_keeps_the_plain_gate(tmp_path: Path) -> None:
    """fan-out していない Step には prefix ゲートを足さない。"""

    class _Plain:
        id = "3.4"
        output_paths = ["src/infra/README.md"]
        output_paths_template = [
            "docs/services/{serviceId}-{serviceNameSlug}-description.md"
        ]

    missing = _check_output_paths_gate(_Ctx(), _Workflow([_Plain()]), "3.4", tmp_path)

    assert missing == ["src/infra/README.md"]
