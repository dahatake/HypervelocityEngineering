"""Tests for mdq.embeddings.

We avoid downloading the intfloat/multilingual-e5-large model (~2.2GB) in CI
by exercising the :class:`NullProvider` for shape/math behaviour, and asserting
the :class:`FastEmbedProvider` raises :class:`EmbeddingsUnavailable` cleanly
when fastembed is not installed.
"""
from __future__ import annotations

import os

import pytest

from mdq import embeddings as emb


def test_null_provider_shape_and_determinism():
    p = emb.NullProvider(dim=16)
    out1 = p.embed(["hello", "world"])
    out2 = p.embed(["hello", "world"])
    assert out1.shape == (2, 16)
    # Deterministic: same input must give same vectors.
    assert (out1 == out2).all()


def test_null_provider_distinct_inputs_distinct_vectors():
    p = emb.NullProvider(dim=16)
    out = p.embed(["alpha", "beta"])
    # The two rows must not be identical.
    assert not (out[0] == out[1]).all()


def test_null_provider_empty_input():
    p = emb.NullProvider(dim=16)
    out = p.embed([])
    assert out.shape == (0, 16)


def test_cosine_distances_basic():
    import numpy as np

    vecs = np.array(
        [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32
    )
    dists = emb.cosine_distances(vecs)
    assert dists.shape == (2,)
    # First pair: identical → distance ~0.
    assert dists[0] < 1e-5
    # Second pair: orthogonal → distance ~1.
    assert abs(dists[1] - 1.0) < 1e-5


def test_cosine_distances_handles_short_input():
    import numpy as np

    assert emb.cosine_distances(np.zeros((0, 4))).shape == (0,)
    assert emb.cosine_distances(np.zeros((1, 4))).shape == (0,)


def test_cosine_distances_zero_vectors():
    import numpy as np

    vecs = np.zeros((3, 4), dtype=np.float32)
    dists = emb.cosine_distances(vecs)
    # All-zero pairs: similarity defined as 0 → distance = 1.
    assert dists.shape == (2,)
    assert (dists == 1.0).all()


def test_get_provider_unknown_raises():
    with pytest.raises(emb.EmbeddingsUnavailable):
        emb.get_provider(name="does-not-exist")


def test_get_provider_null_via_factory():
    p = emb.get_provider(name="null")
    assert isinstance(p, emb.NullProvider)


def test_get_provider_env_var_resolution(monkeypatch):
    monkeypatch.setenv("MDQ_EMBED_PROVIDER", "null")
    p = emb.get_provider()
    assert isinstance(p, emb.NullProvider)


def test_fastembed_unavailable_when_extra_missing():
    """If fastembed is not installed, requesting it must raise cleanly.

    When the `[semantic]` extra *is* installed in the dev environment, this
    test is skipped because the import would succeed (and we don't want to
    pay the model-download cost in unit tests).
    """
    try:
        import fastembed  # noqa: F401
    except ImportError:
        with pytest.raises(emb.EmbeddingsUnavailable):
            emb.get_provider(name="fastembed")
        return
    pytest.skip("fastembed is installed; skipping unavailability check")
