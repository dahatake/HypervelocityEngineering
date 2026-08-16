"""FR-CQ-17: 意味検索のための埋め込み provider（RED）。

`mdq` にも同種の実装があるが import しない。`cq` は `mdq` に依存しない契約
（FR-CQ-01 / FR-KIT-05）で、独立性ガード `test_code_query_skill_wiring.py` が
`from mdq import ...` を含む全形式を拒否する。
"""

from __future__ import annotations

import pytest


def test_the_module_does_not_import_mdq() -> None:
    """部分文字列ではなく import 文の形で見る（docstring 中の言及は許す）。"""
    import re
    from pathlib import Path

    source = Path("cq/embeddings.py").read_text(encoding="utf-8")
    assert re.search(r"^[ \t]*(?:import|from)[ \t]+mdq\b", source, re.MULTILINE) is None


class TestProviderResolution:
    def test_an_absent_backend_is_reported_as_unavailable(self, monkeypatch) -> None:
        """任意依存が無い環境でも索引と検索は動く。例外型で区別できること。"""
        from cq import embeddings

        monkeypatch.setattr(embeddings, "_load_backend", lambda model: None)
        embeddings.get_provider.cache_clear()
        with pytest.raises(embeddings.EmbeddingsUnavailable):
            embeddings.get_provider()

    def test_the_provider_is_cached_per_model(self, monkeypatch) -> None:
        """索引 1 回で数万回呼ばれるため、毎回モデルを構築してはいけない。"""
        from cq import embeddings

        calls: list[str] = []

        def fake_backend(model: str):
            calls.append(model)
            return _FakeBackend(model)

        monkeypatch.setattr(embeddings, "_load_backend", fake_backend)
        embeddings.get_provider.cache_clear()
        first = embeddings.get_provider("m")
        second = embeddings.get_provider("m")
        embeddings.get_provider("other")
        assert first is second
        assert calls == ["m", "other"]

    def test_the_default_model_is_the_measured_one(self) -> None:
        """前回 NO-GO の実測値と切り分けられるよう、同じモデルを既定にする。"""
        from cq import embeddings

        assert embeddings.DEFAULT_MODEL == (
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )

    def test_the_default_model_is_one_fastembed_supports(self) -> None:
        """fastembed は短名を受け付けず ValueError になるので、実在を固定する。"""
        fastembed = pytest.importorskip("fastembed")
        from cq import embeddings

        supported = {m["model"] for m in fastembed.TextEmbedding.list_supported_models()}
        assert embeddings.DEFAULT_MODEL in supported


class TestEncoding:
    def test_vectors_are_normalised(self, monkeypatch) -> None:
        """cosine を内積 1 回で計算するため、格納前に L2 正規化する。"""
        from cq import embeddings

        monkeypatch.setattr(embeddings, "_load_backend", lambda model: _FakeBackend(model))
        embeddings.get_provider.cache_clear()
        provider = embeddings.get_provider("m")
        vectors = provider.embed(["alpha", "beta"])
        for row in vectors:
            assert abs(sum(value * value for value in row) - 1.0) < 1e-5

    def test_encoding_is_deterministic(self, monkeypatch) -> None:
        from cq import embeddings

        monkeypatch.setattr(embeddings, "_load_backend", lambda model: _FakeBackend(model))
        embeddings.get_provider.cache_clear()
        provider = embeddings.get_provider("m")
        assert provider.embed(["alpha"]).tolist() == provider.embed(["alpha"]).tolist()

    def test_round_tripping_through_bytes_preserves_the_vector(self, monkeypatch) -> None:
        from cq import embeddings

        monkeypatch.setattr(embeddings, "_load_backend", lambda model: _FakeBackend(model))
        embeddings.get_provider.cache_clear()
        vector = embeddings.get_provider("m").embed(["alpha"])[0]
        assert embeddings.from_bytes(embeddings.to_bytes(vector)).tolist() == vector.tolist()


class _FakeBackend:
    """`fastembed.TextEmbedding` のダックタイプ（`embed` が iterable を返す）。"""

    def __init__(self, model: str) -> None:
        self.model = model

    def embed(self, texts):
        import numpy as np

        return (
            np.array([float(len(t)), float(sum(map(ord, t)) % 97), 1.0], dtype="float32")
            for t in texts
        )
