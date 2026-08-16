"""FR-GUI-05: graphrag の LLM タイムアウトを GUI から調整できること。

背景（実測 2026-08-14）:
  既定 240 秒では実リポジトリの文書（5 chunk 規模）で抽出が時間切れになる。
  CLI は ``--graphrag-timeout`` で調整できるが GUI には調整手段が無く、
  GUI からは失敗を回避できなかった。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def isolated_settings(tmp_path: Path, monkeypatch):
    """設定ファイルを隔離し、利用統計レポートの自動再生成スレッドを抑止する。

    抑止しないとセクション生成のたびにスレッドが起動し、テスト終了時に
    実行中のまま破棄されてプロセスごと落ちる。
    """
    from mdq import usage_report
    from mdq.gui import settings_store as ss

    fake = tmp_path / "isolated-settings.ini"
    monkeypatch.setattr(ss, "detect_settings_path", lambda _repo_root: fake)
    report_dir = usage_report.default_output_dir(tmp_path)
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "latest.md").write_text("# dummy\n", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# 設定ストア
# ---------------------------------------------------------------------------


def test_default_llm_timeout_matches_the_runtime_config() -> None:
    """GUI 既定値がコード側の単一情報源と乖離しないこと。"""
    from mdq.gui import settings_store
    from mdq.strategies_graphrag import GraphRAGConfig

    assert settings_store.defaults()["graphrag_llm_timeout"] == 0
    # 0 は「コード側既定を採用」の意味。コード側既定は 1200 秒。
    assert GraphRAGConfig().llm_timeout == 1200.0


def test_runtime_config_omits_zero_so_code_default_wins(tmp_path: Path) -> None:
    """0（未指定）のときはコード既定を上書きしないこと。"""
    from mdq.gui import settings_store

    cfg = settings_store.get_graphrag_runtime_config(
        tmp_path, settings={"mdq": {"graphrag_llm_timeout": 0}}
    )
    assert "llm_timeout" not in cfg


def test_runtime_config_passes_through_an_explicit_value(tmp_path: Path) -> None:
    from mdq.gui import settings_store

    cfg = settings_store.get_graphrag_runtime_config(
        tmp_path, settings={"mdq": {"graphrag_llm_timeout": 3600}}
    )
    assert cfg["llm_timeout"] == 3600.0


# ---------------------------------------------------------------------------
# 索引操作サービス
# ---------------------------------------------------------------------------


def test_rebuild_index_forwards_graphrag_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GUI が渡したタイムアウトが graphrag の実行設定へ届くこと。"""
    from mdq import indexer as mdq_indexer
    from mdq import strategies_graphrag as gs
    from mdq.gui import index_service as svc

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# T\n\nbody\n", encoding="utf-8")

    seen: dict = {}

    def _fake_build(repo_root, roots, working_dir, **_kwargs):
        seen["llm_timeout"] = gs.get_runtime_config().llm_timeout
        Path(working_dir).mkdir(parents=True, exist_ok=True)
        return {"strategy": "graphrag", "working_dir": str(working_dir),
                "files_total": 0, "files_ok": 0, "files_skipped": 0,
                "files_error": 0, "documents_processed": 0,
                "documents_failed": 0, "errors": []}

    monkeypatch.setattr(mdq_indexer, "build_graphrag_index", _fake_build)
    gs.clear_runtime_config()
    try:
        svc.rebuild_index(
            tmp_path, roots=["docs"], strategy="graphrag",
            graphrag_options={"llm_timeout": 3600.0},
        )
    finally:
        gs.clear_runtime_config()

    assert seen["llm_timeout"] == 3600.0


# ---------------------------------------------------------------------------
# GUI ウィジェット
# ---------------------------------------------------------------------------


def test_widget_round_trips_the_timeout(qapp) -> None:
    from mdq.gui.graphrag_options import GraphRagOptionsWidget

    w = GraphRagOptionsWidget()
    w.load_from({"graphrag_llm_timeout": 900})
    assert w.to_settings_dict()["graphrag_llm_timeout"] == 900
    assert w.to_runtime_kwargs()["llm_timeout"] == 900.0


def test_widget_zero_means_code_default(qapp) -> None:
    from mdq.gui.graphrag_options import GraphRagOptionsWidget

    w = GraphRagOptionsWidget()
    w.load_from({"graphrag_llm_timeout": 0})
    assert w.to_runtime_kwargs() == {}


def test_section_shows_the_widget_only_for_graphrag(
    qapp, isolated_settings: Path
) -> None:
    """他 strategy の設定と同じく、選択時のみ表示されること。"""
    from mdq.gui.settings_section import MdqIndexSection

    section = MdqIndexSection(repo_root=isolated_settings)
    assert hasattr(section, "_graphrag_options_widget")

    section._strategy_combo.setCurrentIndex(
        section._strategy_combo.findData("graphrag")
    )
    assert section._graphrag_options_widget.isVisibleTo(section)

    section._strategy_combo.setCurrentIndex(
        section._strategy_combo.findData("heading")
    )
    assert not section._graphrag_options_widget.isVisibleTo(section)
