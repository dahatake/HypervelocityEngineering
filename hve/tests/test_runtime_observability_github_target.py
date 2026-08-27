"""FR-RTO-08: GitHub target lifecycle イベントの契約。

RED 先行。`build_github_target_event` は本テスト作成時点で未実装。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hve import runtime_observability as rto


def _build(**kwargs):
    builder = getattr(rto, "build_github_target_event", None)
    if builder is None:  # pragma: no cover - RED 期間のみ
        pytest.fail("build_github_target_event が未実装です（FR-RTO-08）")
    return builder(**kwargs)


class TestEventKind:
    """FR-RTO-08: `kind` は `github_target` の 1 種類だけ。"""

    def test_kind_is_github_target(self) -> None:
        payload = _build(repo="owner/repo", issue_number=12)
        assert payload["kind"] == "github_target"

    def test_kind_is_registered_as_known(self) -> None:
        assert "github_target" in rto.KNOWN_KINDS

    def test_no_additional_github_kind_is_introduced(self) -> None:
        github_kinds = {k for k in rto.KNOWN_KINDS if "github" in k or "issue" in k or "pull" in k}
        assert github_kinds == {"github_target"}

    def test_envelope_keys_are_preserved(self) -> None:
        payload = _build(repo="owner/repo", pr_number=5)
        for key in ("schema_version", "ts", "seq", "pid", "kind", "step"):
            assert key in payload
        assert payload["step"] == ""


class TestAllowedFields:
    """FR-RTO-08: payload に載せてよいキーの限定。"""

    def test_all_allowed_fields_are_emitted(self) -> None:
        payload = _build(
            repo="owner/repo",
            issue_number=12,
            pr_number=34,
            branch="copilot-sdk/asdw-1234abcd",
            base_branch="main",
            created_by_hve=True,
            delete_local_merged_branch=True,
        )
        assert payload["repo"] == "owner/repo"
        assert payload["issue_number"] == 12
        assert payload["pr_number"] == 34
        assert payload["branch"] == "copilot-sdk/asdw-1234abcd"
        assert payload["base_branch"] == "main"
        assert payload["created_by_hve"] is True
        assert payload["delete_local_merged_branch"] is True

    def test_undetermined_fields_are_omitted(self) -> None:
        payload = _build(repo="owner/repo", issue_number=12)
        for key in ("pr_number", "branch", "base_branch", "created_by_hve"):
            assert key not in payload

    def test_unknown_fields_are_rejected(self) -> None:
        with pytest.raises(TypeError):
            _build(repo="owner/repo", token="ghp_secret")  # type: ignore[call-arg]

    def test_created_by_hve_requires_branch(self) -> None:
        payload = _build(repo="owner/repo", created_by_hve=True)
        assert "created_by_hve" not in payload

    def test_created_by_hve_false_is_emitted_with_branch(self) -> None:
        payload = _build(repo="owner/repo", branch="feature/current", created_by_hve=False)
        assert payload["created_by_hve"] is False


class TestValueValidation:
    """FR-RTO-08: 推定値で補わず、不正値は載せない。"""

    @pytest.mark.parametrize("value", [0, -1, True, False, "12", 1.5, None])
    def test_invalid_issue_number_is_omitted(self, value) -> None:
        payload = _build(repo="owner/repo", issue_number=value)
        assert "issue_number" not in payload

    @pytest.mark.parametrize("value", [0, -1, True, "34", 2.5, None])
    def test_invalid_pr_number_is_omitted(self, value) -> None:
        payload = _build(repo="owner/repo", pr_number=value)
        assert "pr_number" not in payload

    @pytest.mark.parametrize("value", ["", "   ", None, 5])
    def test_invalid_branch_is_omitted(self, value) -> None:
        payload = _build(repo="owner/repo", branch=value)
        assert "branch" not in payload

    @pytest.mark.parametrize("value", ["owner", "owner/repo/extra", "", None, "owner repo"])
    def test_invalid_repo_is_omitted(self, value) -> None:
        payload = _build(repo=value, issue_number=1)
        assert "repo" not in payload

    def test_repo_is_not_inferred_from_remote_url(self) -> None:
        payload = _build(repo="https://github.com/owner/repo.git", issue_number=1)
        assert "repo" not in payload


class TestSecretExclusion:
    """FR-RTO-04 / NFR-SEC-01: 機微情報を含めない。"""

    def test_serialized_event_has_no_secret_like_key(self) -> None:
        payload = _build(
            repo="owner/repo",
            issue_number=12,
            pr_number=34,
            branch="copilot-sdk/asdw-1234abcd",
            base_branch="main",
            created_by_hve=True,
            delete_local_merged_branch=False,
        )
        forbidden = {
            "token", "body", "title", "prompt", "response", "comment",
            "url", "html_url", "remote", "headers", "payload",
        }
        assert forbidden.isdisjoint(payload.keys())

    def test_sanitize_event_keeps_only_allowed_github_fields(self, tmp_path: Path) -> None:
        payload = _build(
            repo="owner/repo",
            issue_number=12,
            pr_number=34,
            branch="copilot-sdk/asdw-1234abcd",
            base_branch="main",
            created_by_hve=True,
            delete_local_merged_branch=True,
        )
        payload["token"] = "ghp_secret"
        payload["body"] = "Issue 本文"

        clean = rto.sanitize_event(payload, repo_root=tmp_path)
        assert clean is not None
        assert "token" not in clean
        assert "body" not in clean
        assert clean["repo"] == "owner/repo"
        assert clean["issue_number"] == 12
        assert clean["pr_number"] == 34
        assert clean["branch"] == "copilot-sdk/asdw-1234abcd"
        assert clean["base_branch"] == "main"
        assert clean["created_by_hve"] is True
        assert clean["delete_local_merged_branch"] is True

    def test_github_keys_are_not_persisted_for_other_kinds(self, tmp_path: Path) -> None:
        """kind 限定 allowlist: 他 kind の同名キーを永続化しない。"""
        payload = {
            "kind": "step_status",
            "step": "1",
            "status": "done",
            "repo": "attacker/repo",
            "branch": "attacker-branch",
            "base_branch": "main",
            "issue_number": 1,
            "pr_number": 2,
            "created_by_hve": True,
            "delete_local_merged_branch": True,
        }

        clean = rto.sanitize_event(payload, repo_root=tmp_path)
        assert clean is not None
        assert clean["status"] == "done"
        for key in (
            "repo", "branch", "base_branch", "issue_number",
            "pr_number", "created_by_hve", "delete_local_merged_branch",
        ):
            assert key not in clean


class TestBackwardCompatibility:
    """FR-RTO-01 / NFR-RTO-02: 既存消費者を壊さない。"""

    def test_line_round_trips_through_existing_parser(self) -> None:
        payload = _build(repo="owner/repo", pr_number=34, branch="b", base_branch="main")
        line = rto.format_stats_line(payload)
        assert rto.is_stats_line(line)
        assert rto.parse_stats_line(line) == payload

    def test_existing_metrics_reducer_accepts_it_as_known_kind(self) -> None:
        metrics = rto.RuntimeMetrics()
        payload = _build(repo="owner/repo", pr_number=34)
        assert metrics.apply(payload) is True
        assert metrics.unknown_kind_count == 0
        assert metrics.unknown_kinds == set()

    def test_consumer_without_the_kind_counts_it_instead_of_dropping(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """旧 `KNOWN_KINDS` しか知らない消費者でも未知 kind として計上できる。"""
        legacy_kinds = frozenset(rto.KNOWN_KINDS - {"github_target"})
        monkeypatch.setattr(rto, "KNOWN_KINDS", legacy_kinds)

        metrics = rto.RuntimeMetrics()
        payload = _build(repo="owner/repo", pr_number=34)
        metrics.apply(payload)
        assert metrics.unknown_kind_count == 1
        assert "github_target" in metrics.unknown_kinds
