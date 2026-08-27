"""FR-GUI-36: rolling comment state machineのRED契約。"""

from __future__ import annotations

import importlib


def _types():
    module = importlib.import_module("hve.gui.github_progress_poster")
    return module.GitHubProgressPoster, module.ProgressPostRequest


class TestRollingCommentState:
    def test_target_create_then_update_same_comment(self) -> None:
        poster_type, _request_type = _types()
        poster = poster_type()
        request = poster.set_target("issue", 12)
        assert request is None

        requests = poster.submit("first")
        assert len(requests) == 1
        assert requests[0].operation == "create"
        assert requests[0].target_number == 12

        follow_up = poster.complete("issue", comment_id=500)
        assert follow_up is None
        requests = poster.submit("second")
        assert len(requests) == 1
        assert requests[0].operation == "update"
        assert requests[0].comment_id == 500

    def test_inflight_updates_are_coalesced_to_latest_snapshot(self) -> None:
        poster_type, _request_type = _types()
        poster = poster_type()
        poster.set_target("issue", 12)
        first = poster.submit("v1")
        assert len(first) == 1
        assert poster.submit("v2") == []
        assert poster.submit("v3") == []

        next_request = poster.complete("issue", comment_id=500)
        assert next_request is not None
        assert next_request.operation == "update"
        assert next_request.body == "v3"

    def test_late_target_uses_latest_snapshot(self) -> None:
        poster_type, _request_type = _types()
        poster = poster_type()
        assert poster.submit("running") == []
        request = poster.set_target("pr", 44)
        assert request is not None
        assert request.operation == "create"
        assert request.body == "running"

    def test_issue_and_pr_have_independent_comment_ids(self) -> None:
        poster_type, _request_type = _types()
        poster = poster_type()
        poster.set_target("issue", 12)
        poster.set_target("pr", 44)
        requests = poster.submit("snapshot")
        assert {(request.kind, request.target_number) for request in requests} == {
            ("issue", 12),
            ("pr", 44),
        }
        poster.complete("issue", comment_id=501)
        poster.complete("pr", comment_id=502)
        updates = poster.submit("next")
        assert {(request.kind, request.comment_id) for request in updates} == {
            ("issue", 501),
            ("pr", 502),
        }

    def test_failure_is_best_effort_and_next_submit_retries(self) -> None:
        poster_type, _request_type = _types()
        poster = poster_type()
        poster.set_target("issue", 12)
        poster.submit("v1")
        assert poster.complete("issue", error="network") is None
        retry = poster.submit("v2")
        assert len(retry) == 1
        assert retry[0].operation == "create"
        assert retry[0].body == "v2"

    def test_update_failure_preserves_comment_id_for_retry(self) -> None:
        poster_type, _request_type = _types()
        poster = poster_type()
        poster.set_target("issue", 12)
        poster.submit("created")
        poster.complete("issue", comment_id=500)
        update = poster.submit("v2")
        assert update[0].operation == "update"
        assert poster.complete("issue", error="network") is None
        retry = poster.submit("v3")
        assert retry[0].operation == "update"
        assert retry[0].comment_id == 500
        assert retry[0].body == "v3"

    def test_failure_for_one_target_does_not_reset_the_other(self) -> None:
        poster_type, _request_type = _types()
        poster = poster_type()
        poster.set_target("issue", 12)
        poster.set_target("pr", 44)
        poster.submit("first")
        poster.complete("issue", error="network")
        poster.complete("pr", comment_id=502)
        requests = poster.submit("second")
        by_kind = {request.kind: request for request in requests}
        assert by_kind["issue"].operation == "create"
        assert by_kind["pr"].operation == "update"
        assert by_kind["pr"].comment_id == 502

    def test_changing_target_does_not_reuse_old_comment_id(self) -> None:
        poster_type, _request_type = _types()
        poster = poster_type()
        poster.set_target("issue", 12)
        poster.submit("first")
        poster.complete("issue", comment_id=500)
        request = poster.set_target("issue", 13)
        assert request is not None
        assert request.operation == "create"
        assert request.target_number == 13
        assert request.comment_id is None

    def test_close_stops_new_requests_without_deleting_remote_comment(self) -> None:
        poster_type, _request_type = _types()
        poster = poster_type()
        poster.set_target("issue", 12)
        poster.close()
        assert poster.submit("ignored") == []
        assert poster.set_target("pr", 44) is None

    def test_inflight_completion_after_close_does_not_emit_pending_request(self) -> None:
        poster_type, _request_type = _types()
        poster = poster_type()
        poster.set_target("issue", 12)
        poster.submit("v1")
        poster.submit("pending")
        poster.close()
        assert poster.complete("issue", comment_id=500) is None


class TestStaleCompletion:
    """FR-GUI-36: 旧 target の完了通知を新 target へ持ち込まない。"""

    def test_stale_completion_does_not_bind_comment_id_to_new_target(self) -> None:
        poster_type, _request_type = _types()
        poster = poster_type()
        poster.set_target("issue", 12)
        first = poster.submit("v1")
        assert first[0].operation == "create"
        stale_generation = first[0].generation

        replaced = poster.set_target("issue", 13)
        assert replaced is not None
        assert replaced.generation != stale_generation

        # 旧 target の create 完了が遅れて到着しても新 target へは反映しない。
        assert poster.complete("issue", comment_id=500, generation=stale_generation) is None

        poster.complete("issue", comment_id=600, generation=replaced.generation)
        follow_up = poster.submit("v2")
        assert follow_up[0].operation == "update"
        assert follow_up[0].comment_id == 600

    def test_generation_is_unique_per_target_registration(self) -> None:
        poster_type, _request_type = _types()
        poster = poster_type()
        poster.set_target("issue", 12)
        poster.set_target("pr", 44)
        requests = poster.submit("snapshot")
        generations = {request.generation for request in requests}
        assert len(generations) == len(requests)

    def test_completion_without_generation_is_treated_as_current(self) -> None:
        poster_type, _request_type = _types()
        poster = poster_type()
        poster.set_target("issue", 12)
        poster.submit("v1")
        poster.complete("issue", comment_id=500)
        assert poster.submit("v2")[0].comment_id == 500

    def test_replacing_target_while_inflight_starts_from_latest_snapshot(self) -> None:
        poster_type, _request_type = _types()
        poster = poster_type()
        poster.set_target("issue", 12)
        first = poster.submit("v1")
        assert first[0].operation == "create"
        assert poster.submit("v2") == []  # in-flight のため pending へ畳み込む

        replaced = poster.set_target("issue", 13)
        assert replaced is not None
        assert replaced.operation == "create"
        assert replaced.target_number == 13
        assert replaced.comment_id is None
        assert replaced.body == "v2"

        # 旧 target の pending は新 target へ二重送出されない。
        assert poster.complete("issue", comment_id=500, generation=first[0].generation) is None
        assert poster.submit("v3") == []

        follow_up = poster.complete("issue", comment_id=600, generation=replaced.generation)
        assert follow_up is not None
        assert follow_up.operation == "update"
        assert follow_up.comment_id == 600
        assert follow_up.body == "v3"

    def test_close_prevents_pending_creation_for_inflight_target(self) -> None:
        poster_type, _request_type = _types()
        poster = poster_type()
        poster.set_target("issue", 12)
        poster.submit("v1")
        poster.close()

        assert poster.submit("v2") == []
        assert poster.complete("issue", comment_id=500) is None
        assert poster.submit("v3") == []
