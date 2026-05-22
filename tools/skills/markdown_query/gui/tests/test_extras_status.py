"""Tests for the GUI extras-status probe (Phase 0 / T02)."""
from __future__ import annotations

import pytest

# Skip this whole module when pytest is not installed in the venv; the probe
# itself does not depend on Qt so we can run it as plain pytest.
extras_status = pytest.importorskip(
    "tools.skills.markdown_query.gui.extras_status"
)


def test_probe_returns_extras_status():
    status = extras_status.probe()
    assert isinstance(status, extras_status.ExtrasStatus)
    # Booleans must be present even if extras are not installed.
    assert isinstance(status.fastembed_available, bool)
    assert isinstance(status.nltk_available, bool)
    assert isinstance(status.numpy_available, bool)


def test_semantic_ok_matches_all_three():
    s = extras_status.ExtrasStatus(
        fastembed_available=True,
        nltk_available=True,
        numpy_available=True,
    )
    assert s.semantic_ok is True
    s2 = extras_status.ExtrasStatus(
        fastembed_available=True,
        nltk_available=False,
        numpy_available=True,
        missing=("nltk",),
    )
    assert s2.semantic_ok is False
    assert "nltk" in s2.banner_message()
    assert s2.install_hint() == "pip install -e .[semantic]"


def test_banner_empty_when_all_ok():
    s = extras_status.ExtrasStatus(
        fastembed_available=True,
        nltk_available=True,
        numpy_available=True,
    )
    assert s.banner_message() == ""


def test_missing_tuple_consistent_with_flags():
    """ExtrasStatus is data-only; we don't recompute missing from flags."""
    s = extras_status.ExtrasStatus(
        fastembed_available=False,
        nltk_available=True,
        numpy_available=False,
        missing=("fastembed", "numpy"),
    )
    assert "fastembed" in s.banner_message()
    assert "numpy" in s.banner_message()
