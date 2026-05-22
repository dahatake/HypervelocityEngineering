"""hve.gui.tests.test_mdq_strategy_features

T13 / T16 / T21 統合テスト:

- T13: Chunking Strategy のコンボボックスが ``mdq.strategies.ALL_STRATEGIES``
        から動的に生成されること。
- T16: ``get_index_stats_all_strategies()`` が全 Strategy 分の dict を返すこと。
- T21: ``build_strategies`` 設定キーの保存・読み込みと、複数 Strategy
        一括ビルド処理 (T19/T20) の基本フロー。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")

from mdq.strategies import ALL_STRATEGIES  # noqa: E402


# ---------------------------------------------------------------------------
# T13: dynamic combobox population
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def patched_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """HVE 側 ``settings_path`` を tmp_path 配下に向ける。

    standalone settings_store は ``_try_hve_settings_store()`` で HVE 側へ
    委譲するため、HVE 側のパスを切り替えるだけで両者が同一ファイルを参照する。
    """
    from hve.gui import settings_store as hve_ss

    fake = tmp_path / ".settings.txt"
    monkeypatch.setattr(hve_ss, "settings_path", lambda: fake)

    # 利用統計レポート未存在による自動再生成スレッド起動を抑止。
    report_dir = (
        Path(__file__).resolve().parent.parent.parent
        / "tools"
        / "skills"
        / "markdown_query"
        / "usage-report"
    )
    if not (report_dir / "latest.md").exists():
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "latest.md").write_text("# dummy\n", encoding="utf-8")

    return fake


def test_strategy_combobox_contains_all_strategies(
    qapp, tmp_path: Path, patched_settings: Path
) -> None:
    """T13: コンボボックスの項目数 = len(ALL_STRATEGIES) かつ順序一致。"""
    from tools.skills.markdown_query.gui.settings_section import (
        MdqIndexSection,
    )

    section = MdqIndexSection(repo_root=tmp_path)
    combo = section._strategy_combo
    assert combo.count() == len(ALL_STRATEGIES)
    actual = [combo.itemData(i) for i in range(combo.count())]
    assert tuple(actual) == tuple(ALL_STRATEGIES)


def test_known_strategies_returns_four_entries() -> None:
    """SoT (mdq.strategies.ALL_STRATEGIES) が 4 件を返すことを検証。

    GUI 一括ビルドリストの表示件数不足 (vendor fallback への
    意図せざるダウングレード) を早期検知する。
    """
    from tools.skills.markdown_query.gui import settings_store as standalone_ss

    known = standalone_ss.known_strategies()
    assert len(known) == 4, f"expected 4 strategies, got {len(known)}: {known}"
    assert set(known) == {
        "heading",
        "heading_recursive",
        "fixed_window",
        "semantic_paragraph",
    }


# ---------------------------------------------------------------------------
# T16: get_index_stats_all_strategies
# ---------------------------------------------------------------------------


def test_get_index_stats_all_strategies_returns_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T16: 戻り値のキーが ALL_STRATEGIES と一致し、各 dict が strategy 名を持つ。

    No.1 修正後は DB ファイル未存在時に ``get_index_stats`` を呼ばない経路
    に分岐するため、各 Strategy の DB を事前に touch しておく。
    """
    from hve.gui import mdq_index_service

    mdq_dir = tmp_path / ".mdq"
    mdq_dir.mkdir(exist_ok=True)
    for strategy in ALL_STRATEGIES:
        (mdq_dir / f"index-ja-jp-{strategy}.sqlite").write_bytes(b"")

    # 高速化のため get_index_stats をモック。
    captured_calls: List[str] = []

    def _fake_get_index_stats(
        repo_root: Path,
        *,
        db_path: Path | None = None,
        lang: str = "ja-jp",
        strategy: str = "heading",
    ) -> Dict[str, Any]:
        captured_calls.append(strategy)
        return {
            "db_path": "/tmp/fake.sqlite",
            "db_exists": True,
            "db_mtime": "2025-01-01T00:00:00",
            "schema_version": "0",
            "fts5_enabled": False,
            "lang": lang,
            "strategy": strategy,
            "files": 0,
            "chunks": 0,
            "root_stats": [],
        }

    monkeypatch.setattr(
        mdq_index_service, "get_index_stats", _fake_get_index_stats
    )

    result = mdq_index_service.get_index_stats_all_strategies(
        tmp_path, lang="ja-jp"
    )
    assert set(result.keys()) == set(ALL_STRATEGIES)
    for strategy in ALL_STRATEGIES:
        assert result[strategy]["strategy"] == strategy
    # 全 Strategy について 1 回ずつ呼び出されたこと
    assert sorted(captured_calls) == sorted(ALL_STRATEGIES)


def test_get_index_stats_all_strategies_handles_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T16: 個別 Strategy で例外が出ても残りは取得され、error フィールドが入る。"""
    from hve.gui import mdq_index_service

    call_counter = {"n": 0}

    # 例外パスを通すために DB ファイルを物理的に作成しておく
    # (No.1 修正後、未生成 DB は open_store を呼ばないため例外が出ない)
    mdq_dir = tmp_path / ".mdq"
    mdq_dir.mkdir(exist_ok=True)
    fake_db = mdq_dir / "index-ja-jp-fixed_window.sqlite"
    fake_db.write_bytes(b"\x00")  # 不正な SQLite ファイル

    def _flaky(
        repo_root: Path,
        *,
        db_path: Path | None = None,
        lang: str = "ja-jp",
        strategy: str = "heading",
    ) -> Dict[str, Any]:
        call_counter["n"] += 1
        if strategy == "fixed_window":
            raise RuntimeError("simulated failure")
        return {
            "db_path": "/tmp/fake.sqlite",
            "db_exists": False,
            "db_mtime": "未作成",
            "schema_version": "0",
            "fts5_enabled": False,
            "lang": lang,
            "strategy": strategy,
            "files": 0,
            "chunks": 0,
            "root_stats": [],
        }

    monkeypatch.setattr(mdq_index_service, "get_index_stats", _flaky)

    result = mdq_index_service.get_index_stats_all_strategies(
        tmp_path, lang="ja-jp"
    )
    assert set(result.keys()) == set(ALL_STRATEGIES)
    assert "error" in result["fixed_window"]
    assert result["fixed_window"]["files"] == 0
    # 他 Strategy は通常 dict
    for strategy in ALL_STRATEGIES:
        if strategy == "fixed_window":
            continue
        assert "error" not in result[strategy]


def test_get_index_stats_all_strategies_does_not_create_db_files(
    tmp_path: Path,
) -> None:
    """No.1 (Critical): 未生成 DB は物理ファイル作成せずスタブ値を返す。

    敵対的レビューで指摘された ``open_store`` 副作用による .mdq/ 汚染を
    防止していることを実 I/O で検証する。
    """
    from hve.gui import mdq_index_service

    result = mdq_index_service.get_index_stats_all_strategies(
        tmp_path, lang="ja-jp"
    )
    # 全 Strategy について db_exists=False のスタブが返る
    for strategy in ALL_STRATEGIES:
        assert result[strategy]["db_exists"] is False
        assert result[strategy]["files"] == 0
        assert result[strategy]["chunks"] == 0
        assert result[strategy]["db_mtime"] == "未作成"
    # .mdq/ ディレクトリ自体が作られていない
    mdq_dir = tmp_path / ".mdq"
    assert not mdq_dir.exists(), (
        f".mdq/ が作成されている (副作用バグ): {list(tmp_path.iterdir())}"
    )


# ---------------------------------------------------------------------------
# T21: build_strategies persistence + bulk build flow
# ---------------------------------------------------------------------------


def test_build_strategies_parse_serialize_roundtrip() -> None:
    """T17: parse → serialize が「全選択 = 空文字列」規約に整合。"""
    from tools.skills.markdown_query.gui import settings_store as standalone_ss

    known = standalone_ss._known_strategies()

    # 空文字列 → 全 Strategy
    parsed = standalone_ss.parse_build_strategies("")
    assert tuple(parsed) == tuple(known)

    # 全 Strategy 選択 → 空文字列にシリアライズ
    assert standalone_ss.serialize_build_strategies(list(known)) == ""

    # 部分選択
    if len(known) >= 2:
        subset = [known[0], known[-1]]
        serialized = standalone_ss.serialize_build_strategies(subset)
        assert serialized != ""
        re_parsed = standalone_ss.parse_build_strategies(serialized)
        # 順序は known の順序に正規化される
        expected = [s for s in known if s in subset]
        assert re_parsed == expected


def test_build_strategies_unknown_ignored() -> None:
    """T17: 未知の Strategy 名は黙って除外される。"""
    from tools.skills.markdown_query.gui import settings_store as standalone_ss

    parsed = standalone_ss.parse_build_strategies(
        "heading;__nonexistent__;fixed_window"
    )
    assert "__nonexistent__" not in parsed
    assert "heading" in parsed
    assert "fixed_window" in parsed


def test_bulk_build_runs_each_strategy_in_serial(
    qapp,
    tmp_path: Path,
    patched_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T19: 一括ビルドで各 Strategy が 1 回ずつ直列実行されること。"""
    from tools.skills.markdown_query.gui.settings_section import (
        MdqIndexSection,
    )
    from tools.skills.markdown_query.gui import threads as gui_threads

    invocations: List[str] = []

    class _FakeThread:
        """IndexRefreshThread のテストダブル。即座に succeeded を emit する。"""

        def __init__(self, *, repo_root, lang, strategy, overlap_paragraphs, parent):  # noqa: D401, E501
            self._strategy = strategy
            invocations.append(strategy)

            class _Signal:
                def __init__(self):
                    self._handlers = []

                def connect(self, fn):
                    self._handlers.append(fn)

                def emit(self, *args):
                    for h in self._handlers:
                        h(*args)

            self.succeeded = _Signal()
            self.failed = _Signal()
            self.finished = _Signal()

        def isRunning(self) -> bool:
            return False

        def start(self) -> None:
            # 同期的に成功 → finished を発火（GUI スレッドで直列実行を模す）
            self.succeeded.emit({"elapsed_ms": 1, "strategy": self._strategy})
            self.finished.emit()

    monkeypatch.setattr(gui_threads, "IndexRefreshThread", _FakeThread)
    # settings_section も同名で import 済みなのでそちらも差し替え
    import tools.skills.markdown_query.gui.settings_section as ss_mod

    monkeypatch.setattr(ss_mod, "IndexRefreshThread", _FakeThread)

    section = MdqIndexSection(repo_root=tmp_path)
    # 全 Strategy を選択状態にする
    section._build_strategies = list(ALL_STRATEGIES)
    section._on_bulk_build_clicked()

    # 全 Strategy が 1 回ずつ呼ばれたこと
    assert sorted(invocations) == sorted(ALL_STRATEGIES)
    # 完了メッセージに成功表示
    msg = section._bulk_build_msg.text()
    assert str(len(ALL_STRATEGIES)) in msg


def test_bulk_build_empty_selection_does_not_build_all(
    qapp,
    tmp_path: Path,
    patched_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No.2 (Critical): チェック全解除時は警告表示し、ビルドを開始しない。

    敵対的レビュー前は「空 = 全選択扱い」のため、ユーザーが全チェックを
    外しても全 Strategy が勝手にビルドされる dead-code 問題があった。
    """
    from tools.skills.markdown_query.gui.settings_section import (
        MdqIndexSection,
    )
    import tools.skills.markdown_query.gui.settings_section as ss_mod

    invocations: List[str] = []

    class _FakeThread:
        def __init__(self, *, repo_root, lang, strategy, overlap_paragraphs, parent):  # noqa: E501
            invocations.append(strategy)

        def isRunning(self):
            return False

        def start(self):  # pragma: no cover - 呼ばれないことを期待
            pass

    monkeypatch.setattr(ss_mod, "IndexRefreshThread", _FakeThread)

    section = MdqIndexSection(repo_root=tmp_path)
    section._build_strategies = []  # 全解除を模擬
    section._on_bulk_build_clicked()

    # ビルドは 1 件も実行されない
    assert invocations == []
    # 警告メッセージが表示される
    msg = section._bulk_build_msg.text()
    assert "1 つも選択されていません" in msg


def test_bulk_build_cancel_stops_remaining(
    qapp,
    tmp_path: Path,
    patched_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T20: キャンセル後はキューが空になり、残り Strategy はビルドされない。"""
    from tools.skills.markdown_query.gui.settings_section import (
        MdqIndexSection,
    )
    import tools.skills.markdown_query.gui.settings_section as ss_mod

    invocations: List[str] = []
    cancel_after_first = {"done": False}

    class _FakeThread:
        def __init__(
            self,
            *,
            repo_root,
            lang,
            strategy,
            overlap_paragraphs,
            parent,
        ):
            self._strategy = strategy
            self._parent = parent
            invocations.append(strategy)

            class _Signal:
                def __init__(self):
                    self._handlers = []

                def connect(self, fn):
                    self._handlers.append(fn)

                def emit(self, *args):
                    for h in self._handlers:
                        h(*args)

            self.succeeded = _Signal()
            self.failed = _Signal()
            self.finished = _Signal()

        def isRunning(self) -> bool:
            return False

        def start(self) -> None:
            self.succeeded.emit({"elapsed_ms": 1, "strategy": self._strategy})
            # 1 件目の完了直後にキャンセル要求
            if not cancel_after_first["done"]:
                cancel_after_first["done"] = True
                self._parent._on_bulk_build_cancel_clicked()
            self.finished.emit()

    monkeypatch.setattr(ss_mod, "IndexRefreshThread", _FakeThread)

    section = MdqIndexSection(repo_root=tmp_path)
    section._build_strategies = list(ALL_STRATEGIES)
    section._on_bulk_build_clicked()

    # 1 件目のみ実行された
    assert len(invocations) == 1
    # キャンセルメッセージが出ている
    msg = section._bulk_build_msg.text()
    assert "キャンセル" in msg
