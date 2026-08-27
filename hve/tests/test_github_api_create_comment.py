"""FR-GUI-36 / FR-MAINT-07: comment ID を返す単一 GitHub API の契約。

RED 先行。`create_comment` は本テスト作成時点で未実装。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from hve import github_api
from hve.github_api import GitHubAPIError, post_comment


def _create_comment(*args, **kwargs):
    fn = getattr(github_api, "create_comment", None)
    if fn is None:  # pragma: no cover - RED 期間のみ
        pytest.fail("create_comment が未実装です（FR-GUI-36）")
    return fn(*args, **kwargs)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("REPO", "o/r")


class TestCreateComment:
    """comment ID を返す新 API。"""

    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.api_call")
    def test_returns_comment_id(self, mock_api, mock_sleep) -> None:
        mock_api.return_value = {"id": 987, "body": "hello"}

        assert _create_comment(42, "hello") == 987
        mock_api.assert_called_once_with(
            "POST",
            "https://api.github.com/repos/o/r/issues/42/comments",
            data={"body": "hello"},
            token=None,
        )
        mock_sleep.assert_called_once_with(1)

    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.api_call")
    def test_uses_explicit_repo_and_token(self, mock_api, _sleep) -> None:
        mock_api.return_value = {"id": 5}

        _create_comment(7, "body", repo="other/repo", token="tok2")

        method, url = mock_api.call_args.args
        assert method == "POST"
        assert url == "https://api.github.com/repos/other/repo/issues/7/comments"
        assert mock_api.call_args.kwargs["token"] == "tok2"

    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.api_call")
    def test_body_is_sent_verbatim(self, mock_api, _sleep) -> None:
        mock_api.return_value = {"id": 5}
        body = "# 見出し\n\n| a | b |\n| --- | --- |\n\n  末尾空白  "

        _create_comment(7, body)

        assert mock_api.call_args.kwargs["data"] == {"body": body}

    @pytest.mark.parametrize("payload", [None, [], "ok", 5, {"body": "x"}])
    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.api_call")
    def test_non_object_or_missing_id_returns_none(self, mock_api, _sleep, payload) -> None:
        mock_api.return_value = payload
        assert _create_comment(42, "hello") is None

    @pytest.mark.parametrize("value", [0, -1, True, "987", 9.5, None])
    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.api_call")
    def test_invalid_id_returns_none(self, mock_api, _sleep, value) -> None:
        mock_api.return_value = {"id": value}
        assert _create_comment(42, "hello") is None

    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.api_call")
    def test_api_error_propagates(self, mock_api, mock_sleep) -> None:
        mock_api.side_effect = GitHubAPIError("forbidden", status=403)

        with pytest.raises(GitHubAPIError):
            _create_comment(42, "hello")
        mock_sleep.assert_not_called()


class TestPostCommentWrapper:
    """FR-MAINT-07: endpoint 実装は 1 箇所。`post_comment` は戻り値契約を維持する。"""

    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.api_call")
    def test_still_returns_true(self, mock_api, mock_sleep) -> None:
        mock_api.return_value = {"id": 1}

        assert post_comment(42, "hello") is True
        mock_api.assert_called_once_with(
            "POST",
            "https://api.github.com/repos/o/r/issues/42/comments",
            data={"body": "hello"},
            token=None,
        )
        mock_sleep.assert_called_once_with(1)

    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.api_call")
    def test_missing_id_fails_closed(self, mock_api, _sleep) -> None:
        mock_api.return_value = {}
        with pytest.raises(GitHubAPIError, match="confirm"):
            post_comment(42, "hello")

    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.api_call")
    def test_delegates_to_create_comment(self, mock_api, _sleep) -> None:
        mock_api.return_value = {"id": 3}

        with patch.object(github_api, "create_comment", return_value=3) as delegate:
            post_comment(42, "hello", repo="o/r2", token="t2")

        delegate.assert_called_once_with(42, "hello", repo="o/r2", token="t2")

    def test_endpoint_url_is_built_once(self) -> None:
        import inspect

        source = inspect.getsource(github_api.post_comment)
        assert "/comments" not in source
        assert "api_call(" not in source

    def test_is_exported(self) -> None:
        assert "create_comment" in github_api.__all__
