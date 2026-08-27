"""FR-GUI-36 / FR-GUI-28: comment ID を返す GUI service 境界の契約。

RED 先行。`github_service.create_comment` は本テスト作成時点で未実装。
"""

from __future__ import annotations

import inspect
from typing import Any, List, Tuple

import pytest

from hve.github_api import GitHubAPIError
from hve.gui import github_service


def _create_comment(*args, **kwargs):
    fn = getattr(github_service, "create_comment", None)
    if fn is None:  # pragma: no cover - RED 期間のみ
        pytest.fail("github_service.create_comment が未実装です（FR-GUI-36）")
    return fn(*args, **kwargs)


class TestCreateComment:
    def test_delegates_and_returns_comment_id(self, monkeypatch) -> None:
        calls: List[Tuple[Any, ...]] = []

        def _create(number, body, repo=None, token=None):
            calls.append((number, body, repo, token))
            return 987

        monkeypatch.setattr(github_service.github_api, "create_comment", _create)

        assert _create_comment("o/r", "12", "hello") == 987
        assert calls == [(12, "hello", "o/r", None)]

    def test_body_is_passed_verbatim(self, monkeypatch) -> None:
        captured: List[str] = []

        def _create(number, body, repo=None, token=None):
            captured.append(body)
            return 1

        monkeypatch.setattr(github_service.github_api, "create_comment", _create)
        body = "| a | b |\n| --- | --- |\n\n  末尾空白  "
        _create_comment("o/r", 12, body)

        assert captured == [body]

    @pytest.mark.parametrize("body", ["", "   ", "\n\t"])
    def test_rejects_blank_body(self, monkeypatch, body) -> None:
        called: List[Any] = []
        monkeypatch.setattr(
            github_service.github_api,
            "create_comment",
            lambda *a, **kw: called.append(a),
        )

        with pytest.raises(github_service.GitHubServiceError):
            _create_comment("o/r", 12, body)
        assert called == []

    @pytest.mark.parametrize("raw", ["0", "-1", "abc", "", None])
    def test_rejects_invalid_number(self, monkeypatch, raw) -> None:
        called: List[Any] = []
        monkeypatch.setattr(
            github_service.github_api,
            "create_comment",
            lambda *a, **kw: called.append(a),
        )

        with pytest.raises(github_service.GitHubServiceError):
            _create_comment("o/r", raw, "hello")
        assert called == []

    def test_api_error_becomes_service_error(self, monkeypatch) -> None:
        def _boom(*_a, **_kw):
            raise GitHubAPIError("forbidden", 403)

        monkeypatch.setattr(github_service.github_api, "create_comment", _boom)

        with pytest.raises(github_service.GitHubServiceError):
            _create_comment("o/r", 12, "hello")

    def test_is_exported(self) -> None:
        assert "create_comment" in github_service.__all__

    def test_signature_matches_github_api(self) -> None:
        params = list(
            inspect.signature(github_service.github_api.create_comment).parameters
        )
        assert params == ["issue_num", "body", "repo", "token"]


class TestPostCommentUnchanged:
    """既存の手動コメント投稿の契約を変えない。"""

    def test_returns_none(self, monkeypatch) -> None:
        monkeypatch.setattr(
            github_service.github_api, "post_comment", lambda *a, **kw: True
        )
        assert github_service.post_comment("o/r", 12, "hello") is None
