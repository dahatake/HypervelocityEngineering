"""hve.gui.tests.test_github_branch_fetch

C5「GitHub」セクション（_C5IssuePR）のブランチ取得機能の単体テスト。

検証内容:
  1. 取得成功時に branch の QCompleter にブランチ名が反映される。
  2. 取得失敗（例外）時に状態ラベルがエラーを表示し、ボタンが再有効化される。
  3. 空結果時に「見つかりませんでした」相当のメッセージを表示する。
  4. repo 未入力時は案内メッセージを表示し、取得スレッドを起動しない。

ネットワークには一切アクセスしない。取得結果ハンドラ
`_on_branches_fetched` を直接呼ぶことで決定論的に検証する
（`_FetchModelsThread` 系テストと同じ離散化方針）。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _completer_entries(widget) -> list[str]:
    model = widget.branch.completer().model()
    return [model.data(model.index(i, 0)) for i in range(model.rowCount())]


def test_branches_fetched_populates_completer(qapp) -> None:
    """取得成功時に QCompleter にブランチ名が反映され、件数が表示される。"""
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    w._on_branches_fetched(["main", "dev", "feature/x"])
    assert _completer_entries(w) == ["main", "dev", "feature/x"]
    assert "3" in w.branch_fetch_status.text()
    assert w.fetch_branches_button.isEnabled()


def test_branches_fetched_error_shows_status(qapp) -> None:
    """例外受領時にエラー文言を状態ラベルへ表示し、ボタンを再有効化する。"""
    from hve.gui.page_options import _C5IssuePR
    from hve.github_api import GitHubAPIError

    w = _C5IssuePR()
    w._on_branches_fetched(GitHubAPIError("not found", status=404))
    assert "not found" in w.branch_fetch_status.text()
    assert w.fetch_branches_button.isEnabled()
    # completer は空のまま（誤った候補を出さない）
    assert _completer_entries(w) == []


def test_branches_fetched_empty_shows_not_found(qapp) -> None:
    """空結果時は非空の案内メッセージを表示し、completer を更新しない。"""
    from hve.gui.page_options import _C5IssuePR

    w = _C5IssuePR()
    w._on_branches_fetched([])
    assert w.branch_fetch_status.text()  # 非空メッセージ
    assert _completer_entries(w) == []


def test_fetch_clicked_without_repo_shows_guidance(qapp, monkeypatch) -> None:
    """repo 未入力（入力欄空 + REPO 環境変数なし）時は案内を表示し、スレッド未起動。"""
    from hve.gui.page_options import _C5IssuePR

    monkeypatch.delenv("REPO", raising=False)
    w = _C5IssuePR()
    w.repo.setText("")
    w._on_fetch_branches_clicked()
    assert w.branch_fetch_status.text()  # 案内メッセージ
    # 取得スレッドは起動されない（属性が設定されない）
    assert not hasattr(w, "_fetch_branches_thread")
    # 早期 return のためボタンは無効化されない
    assert w.fetch_branches_button.isEnabled()
