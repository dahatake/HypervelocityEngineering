"""Tests for ``mdq.graphrag_runtime`` (T5.1).

Coverage targets:

- R2 loopback validation (``validate_loopback_url``) including
  ``allow_remote=True`` RuntimeWarning.
- ``_http_post_json`` exception mapping (HTTPError / URLError /
  TimeoutError / OSError -> GraphRAGRuntimeUnavailable).
- ``make_ollama_completion`` payload composition, including the
  ``keyword_extraction`` / ``response_format`` -> ``format=json`` mapping
  that LightRAG expects for its extract_keywords path.
- Deterministic mock backends (``make_mock_completion`` /
  ``make_mock_embedding``).
- Top-level provider router (``get_completion_func`` /
  ``get_embedding_func``).
"""
from __future__ import annotations

import asyncio
import io
import urllib.error
import warnings

import pytest

# graphrag extras (numpy) is optional; skip the whole module if missing.
np = pytest.importorskip("numpy")

from mdq import graphrag_runtime as gr


# --- validate_loopback_url -------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:11434",
        "http://localhost:11434",
        "http://[::1]:11434",
        "https://127.0.0.1:11434",
    ],
)
def test_validate_loopback_url_accepts_loopback(url: str) -> None:
    """All loopback hosts are accepted without warning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # promote warnings to errors
        out = gr.validate_loopback_url(url)
    assert out == url


def test_validate_loopback_url_rejects_remote() -> None:
    with pytest.raises(ValueError, match="non-loopback"):
        gr.validate_loopback_url("http://example.com:11434")


def test_validate_loopback_url_allow_remote_warns() -> None:
    """allow_remote=True must still emit a RuntimeWarning for non-loopback."""
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        out = gr.validate_loopback_url(
            "http://example.com:11434", allow_remote=True
        )
    assert out == "http://example.com:11434"
    rw = [w for w in captured if issubclass(w.category, RuntimeWarning)]
    assert len(rw) == 1
    assert "remote Ollama" in str(rw[0].message)


def test_validate_loopback_url_allow_remote_no_warn_on_loopback() -> None:
    """allow_remote=True must NOT warn when the URL is still loopback."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = gr.validate_loopback_url(
            "http://127.0.0.1:11434", allow_remote=True
        )
    assert out == "http://127.0.0.1:11434"


@pytest.mark.parametrize("bad", ["", None, 0, "not-a-url", "ftp://127.0.0.1"])
def test_validate_loopback_url_rejects_bad_inputs(bad) -> None:
    with pytest.raises(ValueError):
        gr.validate_loopback_url(bad)  # type: ignore[arg-type]


def test_validate_loopback_url_rejects_missing_host() -> None:
    with pytest.raises(ValueError, match="no host"):
        gr.validate_loopback_url("http:///path")


# --- _http_post_json exception mapping -------------------------------------


def _patched_urlopen(monkeypatch, raise_exc: Exception | None = None,
                     response_body: bytes | None = None):
    """Install a fake urlopen that either raises or returns response_body."""
    def fake_urlopen(req, timeout=None):  # noqa: ARG001
        if raise_exc is not None:
            raise raise_exc
        # Context-manager-style mock with .read()
        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return response_body or b"{}"

        return _Resp()

    monkeypatch.setattr(gr.urllib.request, "urlopen", fake_urlopen)


def test_http_post_json_http_error(monkeypatch) -> None:
    err = urllib.error.HTTPError(
        url="http://127.0.0.1:11434/api/x",
        code=500,
        msg="server error",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(b"internal"),
    )
    _patched_urlopen(monkeypatch, raise_exc=err)
    with pytest.raises(gr.GraphRAGRuntimeUnavailable, match="HTTP 500"):
        gr._http_post_json(
            "http://127.0.0.1:11434/api/x", {"k": "v"}, timeout=1.0
        )


def test_http_post_json_url_error(monkeypatch) -> None:
    _patched_urlopen(
        monkeypatch, raise_exc=urllib.error.URLError("refused")
    )
    with pytest.raises(gr.GraphRAGRuntimeUnavailable, match="connection failed"):
        gr._http_post_json("http://127.0.0.1:11434/x", {}, timeout=1.0)


def test_http_post_json_timeout(monkeypatch) -> None:
    _patched_urlopen(monkeypatch, raise_exc=TimeoutError("slow"))
    with pytest.raises(gr.GraphRAGRuntimeUnavailable, match="timed out"):
        gr._http_post_json("http://127.0.0.1:11434/x", {}, timeout=1.0)


def test_http_post_json_os_error(monkeypatch) -> None:
    _patched_urlopen(monkeypatch, raise_exc=ConnectionResetError("reset"))
    with pytest.raises(gr.GraphRAGRuntimeUnavailable, match="I/O error"):
        gr._http_post_json("http://127.0.0.1:11434/x", {}, timeout=1.0)


def test_http_post_json_invalid_json(monkeypatch) -> None:
    _patched_urlopen(monkeypatch, response_body=b"not-json{")
    with pytest.raises(gr.GraphRAGRuntimeUnavailable, match="non-JSON"):
        gr._http_post_json("http://127.0.0.1:11434/x", {}, timeout=1.0)


def test_http_post_json_success(monkeypatch) -> None:
    _patched_urlopen(monkeypatch, response_body=b'{"response": "ok"}')
    out = gr._http_post_json("http://127.0.0.1:11434/x", {}, timeout=1.0)
    assert out == {"response": "ok"}


# --- make_ollama_completion payload composition ----------------------------


def _capture_post(monkeypatch):
    """Return a list that will be appended with each (url, payload) call."""
    captured: list[tuple[str, dict]] = []

    def fake_post(url, payload, timeout):  # noqa: ARG001
        captured.append((url, payload))
        return {"response": "ok"}

    monkeypatch.setattr(gr, "_http_post_json", fake_post)
    return captured


def test_make_ollama_completion_basic(monkeypatch) -> None:
    captured = _capture_post(monkeypatch)
    fn = gr.make_ollama_completion("http://127.0.0.1:11434", "qwen2.5:7b")
    out = asyncio.run(fn("hello"))
    assert out == "ok"
    assert len(captured) == 1
    url, payload = captured[0]
    assert url == "http://127.0.0.1:11434/api/generate"
    assert payload["model"] == "qwen2.5:7b"
    assert payload["prompt"] == "hello"
    assert payload["stream"] is False
    assert "format" not in payload


def test_make_ollama_completion_system_prompt(monkeypatch) -> None:
    captured = _capture_post(monkeypatch)
    fn = gr.make_ollama_completion("http://127.0.0.1:11434", "m")
    asyncio.run(fn("hi", system_prompt="be brief"))
    _, payload = captured[0]
    assert payload["system"] == "be brief"


def test_make_ollama_completion_history(monkeypatch) -> None:
    captured = _capture_post(monkeypatch)
    fn = gr.make_ollama_completion("http://127.0.0.1:11434", "m")
    asyncio.run(fn("now", history_messages=[
        {"role": "user", "content": "before"},
        {"role": "assistant", "content": "ack"},
    ]))
    _, payload = captured[0]
    # Composed prompt must keep history order and append the new prompt last.
    expected = "user: before\nassistant: ack\nnow"
    assert payload["prompt"] == expected


def test_make_ollama_completion_keyword_extraction_sets_format_json(
    monkeypatch,
) -> None:
    """LightRAG passes keyword_extraction=True for its extract_keywords path."""
    captured = _capture_post(monkeypatch)
    fn = gr.make_ollama_completion("http://127.0.0.1:11434", "m")
    asyncio.run(fn("p", keyword_extraction=True))
    _, payload = captured[0]
    assert payload.get("format") == "json"


@pytest.mark.parametrize(
    "rf",
    [
        {"type": "json_object"},
        {"type": "json"},
        "json",
        "JSON",
    ],
)
def test_make_ollama_completion_response_format_json(monkeypatch, rf) -> None:
    captured = _capture_post(monkeypatch)
    fn = gr.make_ollama_completion("http://127.0.0.1:11434", "m")
    asyncio.run(fn("p", response_format=rf))
    _, payload = captured[0]
    assert payload.get("format") == "json"


def test_make_ollama_completion_response_format_other_no_json(monkeypatch) -> None:
    captured = _capture_post(monkeypatch)
    fn = gr.make_ollama_completion("http://127.0.0.1:11434", "m")
    asyncio.run(fn("p", response_format={"type": "text"}))
    _, payload = captured[0]
    assert "format" not in payload


def test_make_ollama_completion_num_predict(monkeypatch) -> None:
    captured = _capture_post(monkeypatch)
    fn = gr.make_ollama_completion(
        "http://127.0.0.1:11434", "m", num_predict=42
    )
    asyncio.run(fn("p"))
    _, payload = captured[0]
    assert payload["options"]["num_predict"] == 42


def test_make_ollama_completion_rejects_remote() -> None:
    """The completion factory itself must reject remote base URLs."""
    with pytest.raises(ValueError, match="non-loopback"):
        gr.make_ollama_completion("http://example.com:11434", "m")


# --- Mock backends ---------------------------------------------------------


def test_make_mock_completion_is_deterministic() -> None:
    fn = gr.make_mock_completion()
    out1 = asyncio.run(fn("hello"))
    out2 = asyncio.run(fn("hello"))
    assert out1 == out2
    assert out1.startswith("mock:")


def test_make_mock_completion_differs_on_input() -> None:
    fn = gr.make_mock_completion()
    out1 = asyncio.run(fn("a"))
    out2 = asyncio.run(fn("b"))
    assert out1 != out2


def test_make_mock_completion_system_prompt_in_hash() -> None:
    """system_prompt must affect the digest (else cache collisions occur)."""
    fn = gr.make_mock_completion()
    out1 = asyncio.run(fn("p", system_prompt=None))
    out2 = asyncio.run(fn("p", system_prompt="s"))
    assert out1 != out2


def test_make_mock_embedding_shape_and_norm() -> None:
    fn, dim = gr.make_mock_embedding(dim=32)
    assert dim == 32
    arr = asyncio.run(fn(["a", "bb", "ccc"]))
    assert arr.shape == (3, 32)
    assert arr.dtype == np.float32
    norms = np.linalg.norm(arr, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)


def test_make_mock_embedding_deterministic() -> None:
    fn, _ = gr.make_mock_embedding(dim=16)
    a = asyncio.run(fn(["hello"]))
    b = asyncio.run(fn(["hello"]))
    assert np.array_equal(a, b)


def test_make_mock_embedding_different_inputs() -> None:
    fn, _ = gr.make_mock_embedding(dim=16)
    a = asyncio.run(fn(["alpha"]))
    b = asyncio.run(fn(["beta"]))
    assert not np.array_equal(a, b)


def test_make_mock_embedding_empty_input() -> None:
    fn, dim = gr.make_mock_embedding(dim=8)
    arr = asyncio.run(fn([]))
    assert arr.shape == (0, dim)


def test_make_mock_embedding_rejects_bad_dim() -> None:
    with pytest.raises(ValueError):
        gr.make_mock_embedding(dim=0)


# --- Top-level factories ---------------------------------------------------


def test_get_completion_func_mock_returns_callable() -> None:
    fn = gr.get_completion_func(provider="mock")
    assert callable(fn)
    out = asyncio.run(fn("x"))
    assert out.startswith("mock:")


def test_get_completion_func_unknown_provider() -> None:
    with pytest.raises(ValueError, match="provider"):
        gr.get_completion_func(provider="bogus")


def test_get_embedding_func_mock_returns_pair() -> None:
    fn, dim = gr.get_embedding_func(provider="mock", mock_dim=16)
    assert callable(fn)
    assert dim == 16


def test_get_embedding_func_unknown_provider() -> None:
    with pytest.raises(ValueError, match="provider"):
        gr.get_embedding_func(provider="bogus")
