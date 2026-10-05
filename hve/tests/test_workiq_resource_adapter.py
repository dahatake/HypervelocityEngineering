"""FR-CLI-91「汎用 snapshot への互換化」: Work IQ を共通 snapshot の adapter にする。

Work IQ 専用の discovery / cache を持たず、FR-TS-12 の process snapshot から
exact ``workiq`` の enabled 状態だけを射影することを固定する。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hve import workiq
from hve.toolsearch import resource_inventory
from hve.toolsearch.resource_inventory import ResourceItem, ResourceSnapshot


class _InventorySession:
    """FR-TS-12 が明示的に許可する no-prompt inventory session。"""

    def __init__(self) -> None:
        self.disconnect_calls = 0
        self.rpc = SimpleNamespace()

    async def disconnect(self) -> None:
        self.disconnect_calls += 1


class _FakeClient:
    def __init__(self, *servers: Any) -> None:
        self.discover_calls = 0
        self.stop_calls = 0
        self.sessions: list[_InventorySession] = []
        owner = self

        class _Mcp:
            async def discover(self, _request: Any, **_kwargs: Any) -> Any:
                owner.discover_calls += 1
                return SimpleNamespace(servers=list(servers))

        self.rpc = SimpleNamespace(mcp=_Mcp())

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        self.stop_calls += 1

    async def create_session(self, **_kwargs: Any) -> _InventorySession:
        session = _InventorySession()
        self.sessions.append(session)
        return session


def _server(name: str, *, enabled: bool = True) -> Any:
    return SimpleNamespace(name=name, enabled=enabled, source="user")


def _mcp_item(name: str, *, enabled: bool) -> ResourceItem:
    return ResourceItem(
        kind="mcp_server",
        name=name,
        enabled=enabled,
        source_kind="user",
    )


def _snapshot(*items: ResourceItem, mcp_state: str = "ready") -> ResourceSnapshot:
    return ResourceSnapshot(
        plugin_state="unverified",
        mcp_state=mcp_state,  # type: ignore[arg-type]
        skill_state="unverified",
        skill_ownership_state="unverified",
        plugins=(),
        mcp_servers=items,
        skills=(),
    )


@pytest.fixture(autouse=True)
def _reset_shared_cache():
    resource_inventory._CACHE.clear()
    yield
    resource_inventory._CACHE.clear()


class TestNoPrivateDiscoveryOrCache:
    def test_workiq_private_discovery_helpers_are_removed(self) -> None:
        for removed in (
            "_probe_workiq_plugin_capability_async",
            "_run_workiq_discovery_sync",
            "_workiq_plugin_capability_cache",
            "_workiq_plugin_capability_cache_key",
        ):
            assert not hasattr(workiq, removed), (
                f"{removed} は共有 snapshot への移行で廃止された実装です"
            )

    def test_capability_reuses_the_shared_process_snapshot(self, tmp_path: Path) -> None:
        clients: list[_FakeClient] = []

        def factory(**_kwargs: Any) -> _FakeClient:
            client = _FakeClient(_server("workiq"), _server("azure"))
            clients.append(client)
            return client

        resource_inventory.discover_sdk_resources(
            working_directory=tmp_path,
            cli_path="sdk-runtime-copilot",
            client_factory=factory,
            force_refresh=True,
        )
        capability = workiq.probe_workiq_plugin_capability(
            cli_path="sdk-runtime-copilot",
            working_directory=tmp_path,
            client_factory=factory,
        )

        assert capability.state == "ready"
        assert capability.enabled_server_names == ("azure", "workiq")
        assert len(clients) == 1, "Work IQ 用に別 client を start してはならない"
        assert clients[0].discover_calls == 1

    def test_separate_runtime_or_endpoint_does_not_share_the_snapshot(
        self,
        tmp_path: Path,
    ) -> None:
        clients: list[_FakeClient] = []

        def factory(**_kwargs: Any) -> _FakeClient:
            client = _FakeClient(_server("workiq"))
            clients.append(client)
            return client

        for cli_url in (None, "http://127.0.0.1:4321"):
            workiq.probe_workiq_plugin_capability(
                cli_path="sdk-runtime-copilot",
                cli_url=cli_url,
                working_directory=tmp_path,
                client_factory=factory,
            )

        assert len(clients) == 2


class TestSnapshotProjection:
    def test_unverified_mcp_snapshot_is_not_reported_as_absent(self) -> None:
        snapshot = _snapshot(_mcp_item("workiq", enabled=True), mcp_state="unverified")

        assert workiq.workiq_capability_from_snapshot(snapshot).state == "unverified"

    def test_only_enabled_names_are_projected(self) -> None:
        snapshot = _snapshot(
            _mcp_item("workiq", enabled=True),
            _mcp_item("azure", enabled=False),
            _mcp_item("github", enabled=True),
        )

        capability = workiq.workiq_capability_from_snapshot(snapshot)
        assert capability.state == "ready"
        assert capability.reason_code == "ready"
        assert capability.enabled_server_names == ("github", "workiq")

    @pytest.mark.parametrize("name", ["workiq-preview", "_hve_workiq", "azure"])
    def test_alias_or_absent_exact_name_is_not_configured(self, name: str) -> None:
        capability = workiq.workiq_capability_from_snapshot(
            _snapshot(_mcp_item(name, enabled=True))
        )

        assert capability.state == "not-configured"

    def test_disabled_exact_workiq_is_not_configured(self) -> None:
        capability = workiq.workiq_capability_from_snapshot(
            _snapshot(_mcp_item("workiq", enabled=False))
        )

        assert capability.state == "not-configured"


class TestPreservedFailClosedContracts:
    """1 リリース維持すると規定された既存契約。"""

    def test_plugin_and_skill_failures_do_not_change_the_workiq_verdict(
        self,
        tmp_path: Path,
    ) -> None:
        client = _FakeClient(_server("workiq"))

        capability = workiq.probe_workiq_plugin_capability(
            working_directory=tmp_path,
            client_factory=lambda **_kwargs: client,
            force_refresh=True,
        )

        assert capability.state == "ready"
        assert client.stop_calls == 1

    def test_malformed_enabled_is_unverified_not_absent(self, tmp_path: Path) -> None:
        client = _FakeClient(SimpleNamespace(name="workiq", enabled=1, source="user"))

        capability = workiq.probe_workiq_plugin_capability(
            working_directory=tmp_path,
            client_factory=lambda **_kwargs: client,
            force_refresh=True,
        )

        assert capability.state == "unverified"

    @pytest.mark.parametrize(
        "servers_field",
        [None, {}, "workiq"],
        ids=["none", "mapping", "text"],
    )
    def test_non_list_servers_field_is_unverified(
        self,
        tmp_path: Path,
        servers_field: Any,
    ) -> None:
        class _BadClient(_FakeClient):
            async def create_session(self, **_kwargs: Any) -> _InventorySession:
                raise AssertionError("schema 検証失敗時に session を作ってはならない")

        client = _BadClient()

        class _Mcp:
            async def discover(self, _request: Any, **_kwargs: Any) -> Any:
                return SimpleNamespace(servers=servers_field)

        client.rpc = SimpleNamespace(mcp=_Mcp())

        capability = workiq.probe_workiq_plugin_capability(
            working_directory=tmp_path,
            client_factory=lambda **_kwargs: client,
            force_refresh=True,
        )

        assert capability.state == "unverified"
        assert capability.enabled_server_names == ()
