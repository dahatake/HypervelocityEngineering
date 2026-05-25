"""D3: precheck_settings の単体テスト。"""

from __future__ import annotations

from hve.autopilot.precheck_model import PrecheckCategory
from hve.autopilot.precheck_settings import collect_missing_auth


class _FakeProvider:
    def __init__(self, pid: str, name: str, required: bool) -> None:
        self.id = pid
        self.display_name = name
        self._required = required

    def is_required(self, _settings):  # noqa: ANN001
        return self._required


_AUTH_OK = object()
_AUTH_NG = object()


def test_collect_missing_auth_skips_non_required() -> None:
    providers = [_FakeProvider("p1", "P1", required=False)]
    items = collect_missing_auth(
        providers,
        settings={},
        auth_states={"p1": _AUTH_NG},
        authenticated_marker=_AUTH_OK,
    )
    assert items == []


def test_collect_missing_auth_reports_required_unauth() -> None:
    providers = [
        _FakeProvider("p1", "P1", required=True),
        _FakeProvider("p2", "P2", required=True),
    ]
    items = collect_missing_auth(
        providers,
        settings={},
        auth_states={"p1": _AUTH_OK, "p2": _AUTH_NG},
        authenticated_marker=_AUTH_OK,
    )
    assert len(items) == 1
    it = items[0]
    assert it.category is PrecheckCategory.AUTH
    assert it.field_name == "p2"
