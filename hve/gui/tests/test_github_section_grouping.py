"""hve.gui.tests.test_github_section_grouping

C5「GitHub」セクション（_C5IssuePR）のグループ枠（QGroupBox）構成の単体テスト（offscreen）。

各コンポーネントが分類どおりの QGroupBox 枠へ配置され、特に「ソースコード管理」枠に
Issue 作成 / PR 作成 / git add 除外パスの 3 項目が含まれることを検証する。
翻訳未ロード（offscreen）では tr() がソース日本語を返すため、タイトルは日本語で照合する。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QWidget,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# 期待されるグループ枠タイトル（生成順、tr() ソース日本語）。
_EXPECTED_TITLES = [
    "認証",
    "ソースコード管理",
    "リポジトリ / Issue 設定",
    "ベースブランチ",
    "PR 自動 Approve & Auto-merge",
    "実行中の自動進捗 Post",
    "GitHub Copilot SDK 連携",
]


def _group_of(widget: QWidget) -> QGroupBox | None:
    """`widget` を内包する直近の QGroupBox 祖先を返す（なければ None）。"""
    parent = widget.parentWidget()
    while parent is not None and not isinstance(parent, QGroupBox):
        parent = parent.parentWidget()
    return parent if isinstance(parent, QGroupBox) else None


def test_seven_groups_in_expected_order(qapp) -> None:
    """7 つの QGroupBox が分類どおりのタイトル・生成順で並ぶ。"""
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    boxes = w.findChildren(QGroupBox)
    assert [b.title() for b in boxes] == _EXPECTED_TITLES


def test_source_control_group_contains_three_items(qapp) -> None:
    """「ソースコード管理」枠に Issue 作成 / PR 作成 / git add 除外パスが含まれる。"""
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    for widget in (w.create_issues, w.create_pr, w.ignore_paths):
        group = _group_of(widget)
        assert group is not None
        assert group.title() == "ソースコード管理"


def test_grouped_widgets_belong_to_expected_groups(qapp) -> None:
    """代表的なウィジェットが想定どおりのグループ枠に属する。"""
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    expected = {
        "gh_login_button": "認証",
        "repo": "リポジトリ / Issue 設定",
        "issue_title": "リポジトリ / Issue 設定",
        "branch": "ベースブランチ",
        "fetch_branches_button": "ベースブランチ",
        "enable_auto_merge": "PR 自動 Approve & Auto-merge",
        "github_auto_post_target": "実行中の自動進捗 Post",
        "fleet_mode_enabled": "GitHub Copilot SDK 連携",
        "cloud_session_enabled": "GitHub Copilot SDK 連携",
    }
    for attr, title in expected.items():
        group = _group_of(getattr(w, attr))
        assert group is not None, attr
        assert group.title() == title, attr


def test_all_input_attributes_preserved(qapp) -> None:
    """settings 反映・既存テスト互換のため、入力ウィジェット属性が全て保持される。"""
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    checkboxes = (
        "create_issues",
        "create_pr",
        "enable_auto_merge",
        "cloud_session_enabled",
    )
    line_edits = (
        "ignore_paths",
        "repo",
        "issue_title",
        "branch",
        "cloud_session_repository_branch",
        "cloud_session_integration_id",
        "cloud_session_mc_base_url",
        "cloud_session_step_overrides",
        "cloud_session_subtask_overrides",
    )
    for attr in checkboxes:
        assert isinstance(getattr(w, attr), QCheckBox), attr
    for attr in line_edits:
        assert isinstance(getattr(w, attr), QLineEdit), attr
    # ハンドラ接続済みボタン / tri-state / spinbox も存在する。
    assert hasattr(w, "gh_login_button")
    assert hasattr(w, "fetch_branches_button")
    assert hasattr(w, "fleet_mode_enabled")
    assert hasattr(w, "cloud_session_max_concurrency")


def test_cloud_repository_owner_name_fields_are_not_visible(qapp) -> None:
    """Cloud repository owner/name は repo から派生するため画面に表示しない。"""
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    label_texts = [label.text() for label in w.findChildren(QLabel)]
    assert not hasattr(w, "cloud_session_repository_owner")
    assert not hasattr(w, "cloud_session_repository_name")
    assert all("Cloud repository owner" not in text for text in label_texts)
    assert all("Cloud repository name" not in text for text in label_texts)
    assert isinstance(w.cloud_session_repository_branch, QLineEdit)
