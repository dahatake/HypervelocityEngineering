"""FR-GUI-05: GUI からの索引構築が全 chunking strategy を配線していること。

背景（実測 2026-08-13、リポジトリ `.mdq/`）:
  ``index-ja-jp-graphrag.sqlite`` に 110 files / 0 chunks の SQLite が生成され、
  本来の LightRAG 作業ディレクトリ ``.mdq/graphrag-ja-jp/`` は存在しなかった。
  ``mdq.indexer.build_graphrag_index`` の呼び出し元が ``mdq/cli.py`` のみで、
  GUI 経路が SQLite 索引パイプラインへフォールバックしていたため。

``graphrag`` は任意依存 ``[graphrag]``（lightrag-hku）と Ollama を要するため、
本テストは CLI と共有する構築関数へ**配線されていること**を検証対象とし、
LightRAG 自体の動作は検証しない。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mdq import indexer as mdq_indexer
from mdq import store
from mdq.gui import index_service as svc
from mdq.strategies import ALL_STRATEGIES


def _seed_docs(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text(
        "# Heading\n\nAlpha content paragraph.\n\n## Section\n\nBeta body.\n",
        encoding="utf-8",
    )


def _fake_graphrag_builder(captured: dict):
    """LightRAG 作業ディレクトリを作る最小のスタブ。"""

    def _build(repo_root, roots, working_dir, *, rebuild=False,
               progress_callback=None):
        captured["repo_root"] = Path(repo_root)
        captured["roots"] = list(roots)
        captured["working_dir"] = Path(working_dir)
        captured["rebuild"] = bool(rebuild)
        Path(working_dir).mkdir(parents=True, exist_ok=True)
        (Path(working_dir) / "kv_store_doc_status.json").write_text(
            "{}", encoding="utf-8"
        )
        return {
            "strategy": "graphrag",
            "working_dir": str(working_dir),
            "files_total": 1,
            "files_ok": 1,
            "files_skipped": 0,
            "files_error": 0,
            "errors": [],
        }

    return _build


# ---------------------------------------------------------------------------
# 索引実体パスの単一情報源
# ---------------------------------------------------------------------------


def test_graphrag_dir_for_matches_cli_convention() -> None:
    """作業ディレクトリのパス規則が ``mdq.store`` の単一実装であること。"""
    assert store.graphrag_dir_for("ja-jp") == Path(".mdq") / "graphrag-ja-jp"
    assert store.graphrag_dir_for("en-us") == Path(".mdq") / "graphrag-en-us"
    # 未知の言語は db_path_for と同じく既定へフォールバックする。
    assert store.graphrag_dir_for("../evil") == Path(".mdq") / "graphrag-ja-jp"


def test_index_artifact_path_is_strategy_aware(tmp_path: Path) -> None:
    """SQLite 索引を持たない strategy は作業ディレクトリを実体とすること。"""
    assert svc.index_artifact_path(tmp_path, strategy="heading") == (
        tmp_path / ".mdq" / "index-ja-jp-heading.sqlite"
    ).resolve()
    assert svc.index_artifact_path(tmp_path, strategy="graphrag") == (
        tmp_path / ".mdq" / "graphrag-ja-jp"
    ).resolve()


# ---------------------------------------------------------------------------
# graphrag の構築分岐
# ---------------------------------------------------------------------------


def test_rebuild_index_graphrag_uses_lightrag_builder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """graphrag が CLI と同じ構築関数へ渡り、SQLite を作らないこと。"""
    _seed_docs(tmp_path)
    captured: dict = {}

    def _must_not_run(*_args, **_kwargs):
        raise AssertionError(
            "graphrag must not fall back to the SQLite index pipeline"
        )

    monkeypatch.setattr(
        mdq_indexer, "build_graphrag_index", _fake_graphrag_builder(captured)
    )
    monkeypatch.setattr(mdq_indexer, "build_index", _must_not_run)

    summary = svc.rebuild_index(tmp_path, roots=["docs"], strategy="graphrag")

    assert captured["working_dir"] == (
        tmp_path / ".mdq" / "graphrag-ja-jp"
    ).resolve()
    assert captured["roots"] == ["docs"]
    assert not (tmp_path / ".mdq" / "index-ja-jp-graphrag.sqlite").exists()
    assert summary["strategy"] == "graphrag"
    assert summary["roots"] == ["docs"]
    assert summary["db_path"] == str(captured["working_dir"])


def test_rebuild_index_graphrag_forwards_force_as_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """完全再ビルドが LightRAG の rebuild へ伝播すること。"""
    _seed_docs(tmp_path)
    captured: dict = {}
    monkeypatch.setattr(
        mdq_indexer, "build_graphrag_index", _fake_graphrag_builder(captured)
    )

    svc.rebuild_index(
        tmp_path, roots=["docs"], strategy="graphrag", force=True
    )

    assert captured["rebuild"] is True


def test_rebuild_index_graphrag_forwards_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """進捗コールバックが LightRAG 構築へ届くこと。"""
    _seed_docs(tmp_path)
    forwarded: list = []

    def _build(repo_root, roots, working_dir, *, rebuild=False,
               progress_callback=None):
        Path(working_dir).mkdir(parents=True, exist_ok=True)
        assert progress_callback is not None
        progress_callback("docs/a.md", 1, 1)
        return {"strategy": "graphrag", "working_dir": str(working_dir),
                "files_total": 0, "files_ok": 0, "files_skipped": 0,
                "files_error": 0, "errors": []}

    monkeypatch.setattr(mdq_indexer, "build_graphrag_index", _build)

    svc.rebuild_index(
        tmp_path, roots=["docs"], strategy="graphrag",
        progress_callback=lambda rel, cur, total: forwarded.append(
            (rel, cur, total)
        ),
    )

    assert forwarded == [("docs/a.md", 1, 1)]


def test_cli_and_gui_share_the_working_dir_convention() -> None:
    """CLI の既定作業ディレクトリが単一実装から解決されること (FR-MAINT-07)。"""
    import argparse

    from mdq import cli

    ns = argparse.Namespace(graphrag_working_dir=None, lang="en-us")
    assert cli._graphrag_working_dir(ns) == str(store.graphrag_dir_for("en-us"))

    explicit = argparse.Namespace(
        graphrag_working_dir="custom/dir", lang="en-us"
    )
    assert cli._graphrag_working_dir(explicit) == str(Path("custom/dir"))


def test_rebuild_index_graphrag_failure_leaves_no_sqlite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """任意依存が無い場合は失敗が伝播し、空の SQLite 索引を残さないこと。"""
    _seed_docs(tmp_path)

    def _unavailable(*_args, **_kwargs):
        raise RuntimeError("LightRAG is not installed")

    monkeypatch.setattr(mdq_indexer, "build_graphrag_index", _unavailable)

    with pytest.raises(RuntimeError):
        svc.rebuild_index(tmp_path, roots=["docs"], strategy="graphrag")

    assert not (tmp_path / ".mdq" / "index-ja-jp-graphrag.sqlite").exists()


# ---------------------------------------------------------------------------
# 全 strategy の配線（新 strategy の配線漏れを落とす）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_every_strategy_materialises_its_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, strategy: str
) -> None:
    """``ALL_STRATEGIES`` の全件が自身の索引実体を生成すること。

    新しい strategy を追加して GUI 構築経路へ配線し忘れた場合、
    このテストが必ず失敗する。
    """
    _seed_docs(tmp_path)
    # semantic_paragraph の埋め込みモデル DL を避ける（既存テストと同じ手段）。
    monkeypatch.setenv("MDQ_EMBED_PROVIDER", "null")
    if strategy == "graphrag":
        monkeypatch.setattr(
            mdq_indexer, "build_graphrag_index", _fake_graphrag_builder({})
        )

    svc.rebuild_index(tmp_path, roots=["docs"], strategy=strategy)

    artifact = svc.index_artifact_path(tmp_path, strategy=strategy)
    assert artifact.exists(), f"{strategy} の索引実体が生成されていない"
    stats = svc.get_index_stats_all_strategies(tmp_path)[strategy]
    assert stats["db_exists"] is True


# ---------------------------------------------------------------------------
# strategy 別統計の存在判定
# ---------------------------------------------------------------------------


def test_stats_for_graphrag_uses_working_dir(tmp_path: Path) -> None:
    """SQLite の有無で graphrag の索引存在を判定しないこと。"""
    mdq_dir = tmp_path / ".mdq"
    mdq_dir.mkdir()
    # 旧不具合の産物: チャンクを持たない SQLite だけが存在する状態。
    (mdq_dir / "index-ja-jp-graphrag.sqlite").write_bytes(b"")

    stats = svc.get_index_stats_all_strategies(tmp_path)["graphrag"]

    assert stats["db_exists"] is False
    assert stats["db_path"] == str((mdq_dir / "graphrag-ja-jp").resolve())


def test_stats_for_graphrag_does_not_fabricate_counts(tmp_path: Path) -> None:
    """実体から取得していない件数を 0 として提示しないこと。"""
    working = tmp_path / ".mdq" / "graphrag-ja-jp"
    working.mkdir(parents=True)
    (working / "kv_store_doc_status.json").write_text("{}", encoding="utf-8")

    stats = svc.get_index_stats_all_strategies(tmp_path)["graphrag"]

    assert stats["db_exists"] is True
    assert stats["files"] is None
    assert stats["chunks"] is None


def test_empty_working_dir_is_not_reported_as_built(tmp_path: Path) -> None:
    """空の作業ディレクトリを「索引あり」と判定しないこと。

    ``build_graphrag_index`` は LightRAG を呼ぶ前に作業ディレクトリを作るため、
    任意依存の欠落でビルドが失敗しても空ディレクトリだけが残る。
    """
    (tmp_path / ".mdq" / "graphrag-ja-jp").mkdir(parents=True)

    assert svc.get_index_stats(tmp_path, strategy="graphrag")["db_exists"] is False
    assert (
        svc.get_index_stats_all_strategies(tmp_path)["graphrag"]["db_exists"] is False
    )


def test_failed_graphrag_build_is_not_reported_as_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """任意依存が無くビルドが失敗した後に「索引あり」と表示しないこと。"""
    _seed_docs(tmp_path)

    def _unavailable(repo_root, roots, working_dir, **_kwargs):
        Path(working_dir).mkdir(parents=True, exist_ok=True)
        raise RuntimeError("LightRAG is not installed")

    monkeypatch.setattr(mdq_indexer, "build_graphrag_index", _unavailable)

    with pytest.raises(RuntimeError):
        svc.rebuild_index(tmp_path, roots=["docs"], strategy="graphrag")

    stats = svc.get_index_stats_all_strategies(tmp_path)["graphrag"]
    assert stats["db_exists"] is False
    assert stats["db_mtime"] == "未作成"


def test_lightrag_index_predicate_is_shared_with_the_indexer(
    tmp_path: Path,
) -> None:
    """LightRAG 索引の判定規則が単一実装であること (FR-MAINT-07)。"""
    working = tmp_path / "wd"
    working.mkdir()
    assert mdq_indexer.has_lightrag_index(working) is False
    (working / "unrelated.txt").write_text("x", encoding="utf-8")
    assert mdq_indexer.has_lightrag_index(working) is False
    (working / "graph_chunk_entity_relation.graphml").write_text(
        "", encoding="utf-8"
    )
    assert mdq_indexer.has_lightrag_index(working) is True


def test_stats_for_graphrag_does_not_create_working_dir(tmp_path: Path) -> None:
    """統計取得が LightRAG 作業ディレクトリを新規作成しないこと。"""
    svc.get_index_stats(tmp_path, strategy="graphrag")
    assert not (tmp_path / ".mdq").exists()
