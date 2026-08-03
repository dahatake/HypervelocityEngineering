"""hve.gui.tests.test_github_section_consolidation

GitHub 設定統合（Issue/PR + Fleet mode + Cloud Session を単一「GitHub」
セクション C5 に集約）の回帰防止テスト。

検証内容:
  1. _SECTION_FIELDS: fleet/cloud キーが C5 に存在し C1 に存在しないこと。
  2. ウィジェット属性: _C5IssuePR が fleet/cloud 属性を持ち、_C1Basic が
     持たないこと（T1 の移動先と _SECTION_FIELDS の整合）。
  3. 設定画面ツリー / Step 2 のセクションラベルが「GitHub」であること。
  4. C5 経由で fleet (tri-state) / cloud_session の値が save→load→apply→
     collect で往復すること。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hve.gui import settings_apply, settings_store

# C5 へ集約された Fleet / Cloud Session キー群（C1 から移動）。
_MOVED_KEYS = [
    "fleet_mode_enabled",
    "cloud_session_enabled",
    "cloud_session_repository_branch",
    "cloud_session_max_concurrency",
    "cloud_session_integration_id",
    "cloud_session_mc_base_url",
    "cloud_session_step_overrides",
    "cloud_session_subtask_overrides",
]


# ---------------------------------------------------------------------------
# 1. _SECTION_FIELDS のセクション割当
# ---------------------------------------------------------------------------
def test_moved_keys_are_in_c5_not_c1() -> None:
    """fleet/cloud キーが _SECTION_FIELDS["C5"] に在り ["C1"] に無いこと。"""
    c1 = settings_apply._SECTION_FIELDS["C1"]
    c5 = settings_apply._SECTION_FIELDS["C5"]
    for key in _MOVED_KEYS:
        assert key in c5, f"{key} が _SECTION_FIELDS['C5'] に未登録"
        assert key not in c1, f"{key} が _SECTION_FIELDS['C1'] に残存"


# ---------------------------------------------------------------------------
# 2. ウィジェット属性の所在
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def qapp():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_c5_widget_has_moved_attributes(qapp) -> None:
    """_C5IssuePR が fleet/cloud ウィジェット属性を持つこと。"""
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    for key in _MOVED_KEYS:
        assert hasattr(w, key), f"_C5IssuePR に属性 {key} が無い"


def test_c1_widget_lacks_moved_attributes(qapp) -> None:
    """_C1Basic が fleet/cloud ウィジェット属性を持たないこと。"""
    from hve.gui.page_options import _C1Basic

    w = _C1Basic()
    for key in _MOVED_KEYS:
        assert not hasattr(w, key), f"_C1Basic に属性 {key} が残存"


# ---------------------------------------------------------------------------
# 3. セクションラベル
# ---------------------------------------------------------------------------
def test_settings_window_tree_labels_c5_as_github() -> None:
    """設定画面ツリーの C5 ノードラベルが「GitHub」であること。"""
    from hve.gui.settings_window import _CATEGORY_TREE

    renkei_items = [items for label, items in _CATEGORY_TREE if label == "連携"][0]
    label_by_key = {key: name for name, key in renkei_items}
    assert label_by_key.get("C5") == "GitHub", (
        f"C5 のラベルが GitHub でない: {label_by_key.get('C5')!r}"
    )


def test_options_page_section_label_c5_is_github(qapp) -> None:
    """Step 2 OptionsPage の C5 グループタイトルが「GitHub」であること。"""
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    group = page._category_groups.get("C5")
    assert group is not None, "C5 グループが存在しない"
    assert group.title() == "GitHub", (
        f"C5 グループタイトルが GitHub でない: {group.title()!r}"
    )


# ---------------------------------------------------------------------------
# 4. C5 経由の round-trip
# ---------------------------------------------------------------------------
@pytest.fixture
def tmp_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_path = tmp_path / ".settings.txt"
    monkeypatch.setattr(settings_store, "settings_path", lambda: fake_path)
    return fake_path


def test_c5_fleet_and_cloud_roundtrip(tmp_settings: Path, qapp) -> None:
    """C5 経由で fleet (tri-state) / cloud_session 値が round-trip すること。"""
    from hve.gui.page_options import _C5IssuePR
    from PySide6.QtWidgets import QWidget

    snapshot = settings_store.load()
    snapshot.setdefault("options", {}).update({
        "fleet_mode_enabled": "on",
        "cloud_session_enabled": True,
        "repo": "acme/svc",
        "cloud_session_max_concurrency": 9,
    })
    settings_store.save(snapshot)

    reloaded = settings_store.load()
    widget = _C5IssuePR()
    sections: dict[str, QWidget] = {"C5": widget}
    settings_apply.apply_to_widgets(sections, reloaded)
    collected = settings_apply.collect_from_widgets(sections)

    assert collected["fleet_mode_enabled"] == "on", (
        f"fleet_mode_enabled が round-trip 後に {collected['fleet_mode_enabled']!r}"
    )
    assert collected["cloud_session_enabled"] is True, (
        f"cloud_session_enabled が round-trip 後に {collected['cloud_session_enabled']!r}"
    )
    assert collected["repo"] == "acme/svc"
    assert "cloud_session_repository_owner" not in collected
    assert "cloud_session_repository_name" not in collected
    assert collected["cloud_session_max_concurrency"] == 9


def test_c1_section_does_not_collect_moved_keys(qapp) -> None:
    """C1 セクション経由では fleet/cloud キーが収集されないこと（移動完了の確認）。"""
    from hve.gui.page_options import _C1Basic

    widget = _C1Basic()
    collected = settings_apply.collect_from_widgets({"C1": widget})
    for key in _MOVED_KEYS:
        assert key not in collected, (
            f"C1 経由で {key} が収集された（C5 への移動が不完全）"
        )


def test_c5_to_args_populates_fleet_and_cloud(qapp) -> None:
    """`_C5IssuePR.to_args()` が fleet/cloud 値を OrchestrateArgs に反映すること。

    本統合の中核挙動（CLI 引数伝播）の回帰防止。to_args の移動行が
    欠落すると永続化テストは緑のまま CLI 引数だけ静かに欠落するため、
    OrchestrateArgs への書き込みを直接検証する。
    """
    from hve.gui.page_options import _C5IssuePR
    from hve.gui.orchestrate_args import OrchestrateArgs

    widget = _C5IssuePR()
    widget.fleet_mode_enabled.set_tristate(True)
    widget.cloud_session_enabled.setChecked(True)
    widget.repo.setText("acme/svc")
    widget.cloud_session_repository_branch.setText("dev")
    widget.cloud_session_max_concurrency.setValue(7)
    widget.cloud_session_integration_id.setText("integ-1")
    widget.cloud_session_mc_base_url.setText("https://mc.example.com")
    widget.cloud_session_step_overrides.setText('{"1": true}')
    widget.cloud_session_subtask_overrides.setText('{"pre_qa": false}')

    args = OrchestrateArgs(workflow="aad-web", repo_root=Path.cwd())
    widget.to_args(args)

    assert args.fleet_mode_enabled is True
    assert args.cloud_session_enabled is True
    assert args.cloud_session_owner == "acme"
    assert args.cloud_session_repository_name == "svc"
    assert args.cloud_session_branch == "dev"
    assert args.cloud_session_max_concurrency == 7
    assert args.cloud_session_integration_id == "integ-1"
    assert args.cloud_session_mc_base_url == "https://mc.example.com"
    assert args.cloud_session_step_overrides == '{"1": true}'
    assert args.cloud_session_subtask_overrides == '{"pre_qa": false}'


