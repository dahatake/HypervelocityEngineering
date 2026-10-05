"""FR-PROMPT-03 / FR-PROMPT-04 — `hve prompt plan|run` と `--input-alias` の契約テスト。"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from hve import __main__ as hve_main
from hve import prompt_execution


def _write_request(tmp_path: Path, **overrides) -> Path:
    data = {
        "schema_version": 1,
        "goal": "設計を進めたい",
        "workflows": [{"workflow_id": "aas"}],
    }
    data.update(overrides)
    path = tmp_path / "request.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


class _Recorder:
    def __init__(self, codes=(0,)):
        self.codes = list(codes)
        self.calls: list = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        return subprocess.CompletedProcess(argv, self.codes.pop(0) if self.codes else 0)


@pytest.fixture()
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from hve.gui import settings_store

    monkeypatch.setattr(settings_store, "_SETTINGS_PATH", tmp_path / ".settings.txt")
    monkeypatch.setattr(settings_store, "settings_path", lambda: tmp_path / ".settings.txt")
    return tmp_path


class TestParser:
    def test_prompt_is_registered(self):
        parser = hve_main._build_parser()
        args = parser.parse_args(["prompt", "plan", "--request", "r.json"])
        assert args.command == "prompt"
        assert args.prompt_command == "plan"
        assert args.request == "r.json"

    def test_run_requires_expected_sha256(self):
        parser = hve_main._build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["prompt", "run", "--request", "r.json"])

    def test_run_accepts_expected_sha256(self):
        parser = hve_main._build_parser()
        args = parser.parse_args(
            ["prompt", "run", "--request", "r.json", "--expected-sha256", "a" * 64]
        )
        assert args.expected_sha256 == "a" * 64


class TestInputAliasOption:
    def test_orchestrate_accepts_repeated_pairs(self):
        parser = hve_main._build_parser()
        args = parser.parse_args(
            [
                "orchestrate",
                "--workflow",
                "aas",
                "--input-alias",
                "docs/catalog/app-catalog.md",
                "inputs/a.md",
                "--input-alias",
                "docs/catalog/use-case-catalog.md",
                "inputs/b.md",
            ]
        )
        assert args.input_alias == [
            ["docs/catalog/app-catalog.md", "inputs/a.md"],
            ["docs/catalog/use-case-catalog.md", "inputs/b.md"],
        ]

    def test_default_is_empty(self):
        parser = hve_main._build_parser()
        args = parser.parse_args(["orchestrate", "--workflow", "aas"])
        assert not getattr(args, "input_alias", None)

    def test_odd_arity_is_rejected(self):
        parser = hve_main._build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(
                ["orchestrate", "--workflow", "aas", "--input-alias", "only-one"]
            )

    def test_params_carry_normalized_aliases(self):
        parser = hve_main._build_parser()
        args = parser.parse_args(
            [
                "orchestrate",
                "--workflow",
                "aas",
                "--input-alias",
                "docs\\catalog\\app-catalog.md",
                "README.md",
            ]
        )
        params = hve_main._build_params(args)
        assert params["input_aliases"] == [("docs/catalog/app-catalog.md", "README.md")]

    def test_params_omit_the_key_when_unused(self):
        parser = hve_main._build_parser()
        args = parser.parse_args(["orchestrate", "--workflow", "aas"])
        assert "input_aliases" not in hve_main._build_params(args)

    @pytest.mark.parametrize(
        "canonical,actual,reason",
        [
            ("docs/catalog/app-catalog.md", "../../../etc/passwd", "リポジトリ外"),
            ("docs/catalog/*.md", "README.md", "glob canonical"),
            ("docs/catalog/app-catalog.md", "does/not/exist.md", "実ファイル不在"),
            ("docs/nope.md", "README.md", "active Step の入力でない"),
        ],
    )
    def test_unsafe_alias_is_rejected_on_the_orchestrate_path(
        self, canonical: str, actual: str, reason: str
    ):
        """`prompt` 経由でなくても FR-PROMPT-08 の安全契約を適用する。

        検証しないと、repo 外パスが Step Prompt へ注入される。
        """
        from hve.input_aliases import InputAliasError

        parser = hve_main._build_parser()
        args = parser.parse_args(
            ["orchestrate", "--workflow", "aas", "--input-alias", canonical, actual]
        )
        with pytest.raises(InputAliasError):
            hve_main._build_params(args)

    def test_duplicate_canonical_is_rejected_before_execution(self):
        from hve.input_aliases import InputAliasError

        parser = hve_main._build_parser()
        args = parser.parse_args(
            [
                "orchestrate",
                "--workflow",
                "aas",
                "--input-alias",
                "docs/catalog/app-catalog.md",
                "inputs/a.md",
                "--input-alias",
                "docs/catalog/app-catalog.md",
                "inputs/b.md",
            ]
        )
        with pytest.raises(InputAliasError):
            hve_main._build_params(args)


class TestPromptPlan:
    def test_runs_dry_run_for_each_workflow_and_prints_hash(
        self, tmp_path: Path, isolated_settings: Path, capsys, monkeypatch
    ):
        recorder = _Recorder([0, 0])
        monkeypatch.setattr(prompt_execution, "_default_runner", recorder)
        request = _write_request(
            tmp_path, workflows=[{"workflow_id": "aas"}, {"workflow_id": "aad-web"}]
        )
        code = hve_main.main(["prompt", "plan", "--request", str(request)])
        assert code == 0
        assert len(recorder.calls) == 2
        for argv, _ in recorder.calls:
            assert "--dry-run" in argv
        out = capsys.readouterr().out
        assert "plan SHA-256:" in out

    def test_propagates_dry_run_failure_and_prints_no_hash(
        self, tmp_path: Path, isolated_settings: Path, capsys, monkeypatch
    ):
        recorder = _Recorder([7])
        monkeypatch.setattr(prompt_execution, "_default_runner", recorder)
        request = _write_request(tmp_path)
        code = hve_main.main(["prompt", "plan", "--request", str(request)])
        assert code == 7
        assert "plan SHA-256:" not in capsys.readouterr().out

    def test_invalid_request_fails_closed(self, tmp_path: Path, isolated_settings: Path, monkeypatch):
        recorder = _Recorder([0])
        monkeypatch.setattr(prompt_execution, "_default_runner", recorder)
        bad = tmp_path / "bad.json"
        bad.write_text('{"schema_version": 99, "workflows": []}', encoding="utf-8")
        assert hve_main.main(["prompt", "plan", "--request", str(bad)]) != 0
        assert recorder.calls == []


class TestPromptRunApprovalGate:
    @pytest.fixture(autouse=True)
    def _isolate_durable_registration(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        def _register(plan, _repo_root):
            return (
                "execution-prompt-cli-test",
                tuple(
                    f"instance-{index}"
                    for index, _workflow in enumerate(plan.workflows)
                ),
            )

        monkeypatch.setattr(
            prompt_execution,
            "_register_durable_execution",
            _register,
        )
        monkeypatch.setattr(
            prompt_execution,
            "_verify_durable_child_completion",
            lambda _execution_id, _instance_id: True,
        )

    def _plan_hash(self, tmp_path: Path, request: Path) -> str:
        from hve import prompt_execution
        from hve.gui import settings_store
        from hve.prompt_request import load_request

        plan = prompt_execution.build_execution_plan(
            load_request(request),
            settings=settings_store.load(),
            repo_root=Path.cwd(),
            head_commit=prompt_execution.resolve_head_commit(Path.cwd()),
        )
        return plan.sha256

    def test_mismatched_hash_starts_no_orchestrate_subprocess(
        self, tmp_path: Path, isolated_settings: Path, monkeypatch
    ):
        recorder = _Recorder([0])
        monkeypatch.setattr(prompt_execution, "_default_runner", recorder)
        request = _write_request(tmp_path)
        code = hve_main.main(
            ["prompt", "run", "--request", str(request), "--expected-sha256", "b" * 64]
        )
        assert code != 0
        assert recorder.calls == []

    def test_malformed_hash_starts_no_orchestrate_subprocess(
        self, tmp_path: Path, isolated_settings: Path, monkeypatch
    ):
        recorder = _Recorder([0])
        monkeypatch.setattr(prompt_execution, "_default_runner", recorder)
        request = _write_request(tmp_path)
        code = hve_main.main(
            ["prompt", "run", "--request", str(request), "--expected-sha256", "nope"]
        )
        assert code != 0
        assert recorder.calls == []

    def test_matching_hash_executes_without_dry_run(
        self, tmp_path: Path, isolated_settings: Path, monkeypatch
    ):
        request = _write_request(tmp_path)
        expected = self._plan_hash(tmp_path, request)
        recorder = _Recorder([0])
        monkeypatch.setattr(prompt_execution, "_default_runner", recorder)
        code = hve_main.main(
            ["prompt", "run", "--request", str(request), "--expected-sha256", expected]
        )
        assert code == 0
        assert len(recorder.calls) == 1
        argv, kwargs = recorder.calls[0]
        assert "--dry-run" not in argv
        assert "--execution-id" in argv
        assert "--instance-id" in argv
        assert kwargs.get("shell", False) is False

    def test_fail_fast_between_workflows(
        self, tmp_path: Path, isolated_settings: Path, monkeypatch
    ):
        request = _write_request(
            tmp_path, workflows=[{"workflow_id": "aas"}, {"workflow_id": "aad-web"}]
        )
        expected = self._plan_hash(tmp_path, request)
        recorder = _Recorder([5, 0])
        monkeypatch.setattr(prompt_execution, "_default_runner", recorder)
        code = hve_main.main(
            ["prompt", "run", "--request", str(request), "--expected-sha256", expected]
        )
        assert code == 5
        assert len(recorder.calls) == 1

    def test_saved_settings_drift_starts_no_child(
        self, tmp_path: Path, isolated_settings: Path, monkeypatch, capsys
    ):
        """FR-PROMPT-04 / 05: 保存設定による実 argv の変更にも再承認が必要。"""
        from hve.gui import settings_store
        from hve.prompt_request import load_request

        request = _write_request(tmp_path)
        settings = settings_store.defaults()
        settings_store.save(settings)
        approved = prompt_execution.build_execution_plan(
            load_request(request),
            settings=settings_store.load(),
            repo_root=Path.cwd(),
            head_commit=prompt_execution.resolve_head_commit(Path.cwd()),
        )
        settings["options"]["model"] = "gpt-5.5"
        settings_store.save(settings)
        saved_bytes = settings_store.settings_path().read_bytes()
        rebuilt = prompt_execution.build_execution_plan(
            load_request(request),
            settings=settings_store.load(),
            repo_root=Path.cwd(),
            head_commit=approved.head_commit,
        )
        assert rebuilt.workflows[0].argv != approved.workflows[0].argv
        assert rebuilt.sha256 != approved.sha256
        argv = rebuilt.workflows[0].argv
        assert argv[argv.index("--model") + 1] == "gpt-5.5"
        recorder = _Recorder([0])
        monkeypatch.setattr(prompt_execution, "_default_runner", recorder)

        code = hve_main.main(
            [
                "prompt", "run", "--request", str(request),
                "--expected-sha256", approved.sha256,
            ]
        )

        assert code == 2
        assert "stale" in capsys.readouterr().err
        assert recorder.calls == []
        assert settings_store.settings_path().read_bytes() == saved_bytes

    def test_approved_run_preserves_resource_routing_failure(
        self, tmp_path: Path, isolated_settings: Path, monkeypatch
    ):
        """FR-PROMPT-04 / FR-TS-13: Fake child の routing 失敗を成功へ丸めない。"""
        from hve import workiq
        from hve.gui import settings_store
        from hve.toolsearch import resource_routing

        settings = settings_store.defaults()
        settings["options"]["workiq"] = True
        settings_store.save(settings)
        saved_bytes = settings_store.settings_path().read_bytes()
        monkeypatch.setattr(
            workiq, "probe_workiq_plugin_capability",
            lambda **_kwargs: workiq.WorkIQCapability("ready", "ready", ("workiq",)),
        )
        request = _write_request(
            tmp_path, workflows=[{"workflow_id": "aas"}, {"workflow_id": "aad-web"}]
        )
        expected = self._plan_hash(tmp_path, request)
        send = Mock(side_effect=AssertionError("routing failure must precede send"))
        session = SimpleNamespace(
            rpc=SimpleNamespace(
                tools=SimpleNamespace(initialize_and_validate=AsyncMock()),
                mcp=SimpleNamespace(
                    list=AsyncMock(return_value=SimpleNamespace(
                        host=SimpleNamespace(),
                        servers=[SimpleNamespace(name="workiq", status="connected")],
                    )),
                    list_tools=AsyncMock(return_value=SimpleNamespace(
                        tools=[SimpleNamespace(name="ask")],
                    )),
                ),
                options=SimpleNamespace(update=AsyncMock(
                    return_value=SimpleNamespace(success=False),
                )),
            ),
            disconnect=AsyncMock(),
            send=send,
            send_and_wait=send,
        )
        client = SimpleNamespace(create_session=AsyncMock(return_value=session))
        route = resource_routing.ResourceRoute(
            enabled_mcp_servers=("workiq",),
            required_mcp_servers=("workiq",),
            mcp_tool_allowlists={"workiq": ("ask",)},
        )
        children: list[list[str]] = []

        def failed_child(argv, **kwargs):
            children.append(list(argv))
            assert kwargs["shell"] is False
            assert kwargs["cwd"] == str(Path.cwd())
            assert "--dry-run" not in argv
            assert "--workiq" in argv
            # 実 child/SDK は起動しない。共有 routing だけを Fake SDK で実行する。
            with pytest.raises(
                resource_routing.ResourceRoutingError, match="required MCP servers: workiq"
            ):
                asyncio.run(resource_routing.create_session_from_route(
                    client=client, session_options={"model": "fake"}, route=route,
                ))
            return subprocess.CompletedProcess(argv, 1)

        completed = Mock(return_value=True)
        monkeypatch.setattr(prompt_execution, "_default_runner", failed_child)
        monkeypatch.setattr(prompt_execution, "_verify_durable_child_completion", completed)

        code = hve_main.main(
            ["prompt", "run", "--request", str(request), "--expected-sha256", expected]
        )

        assert code == 1
        assert len(children) == 1
        client.create_session.assert_awaited_once()
        session.rpc.tools.initialize_and_validate.assert_awaited_once()
        session.rpc.mcp.list.assert_awaited_once()
        session.rpc.mcp.list_tools.assert_awaited_once()
        session.rpc.options.update.assert_awaited_once()
        session.disconnect.assert_awaited_once()
        send.assert_not_called()
        completed.assert_not_called()
        assert settings_store.settings_path().read_bytes() == saved_bytes

    @pytest.mark.parametrize(
        ("approved_state", "runtime_state"),
        [("ready", "not-configured"), ("not-configured", "ready")],
    )
    def test_workiq_capability_drift_starts_no_child(
        self,
        approved_state: str,
        runtime_state: str,
        tmp_path: Path,
        isolated_settings: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys,
    ):
        from hve import workiq
        from hve.gui import settings_store
        from hve.prompt_request import load_request

        def capability(state: str) -> workiq.WorkIQCapability:
            return workiq.WorkIQCapability(
                state=state,
                reason_code=state,
                enabled_server_names=("workiq",) if state == "ready" else (),
            )

        settings = settings_store.defaults()
        settings["options"]["workiq"] = True
        settings_store.save(settings)
        saved_bytes = settings_store.settings_path().read_bytes()
        request = _write_request(tmp_path)
        approved = prompt_execution.build_execution_plan(
            load_request(request),
            settings=settings,
            repo_root=Path.cwd(),
            head_commit=prompt_execution.resolve_head_commit(Path.cwd()),
            workiq_capability=capability(approved_state),
        )

        runtime_capability = capability(runtime_state)
        rebuilt = prompt_execution.build_execution_plan(
            load_request(request),
            settings=settings,
            repo_root=Path.cwd(),
            head_commit=approved.head_commit,
            workiq_capability=runtime_capability,
        )
        assert ("--workiq" in approved.workflows[0].argv) is (approved_state == "ready")
        assert ("--workiq" in rebuilt.workflows[0].argv) is (runtime_state == "ready")
        assert approved.workflows[0].argv != rebuilt.workflows[0].argv
        assert approved.sha256 != rebuilt.sha256
        monkeypatch.setattr(
            workiq,
            "probe_workiq_plugin_capability",
            lambda **_kwargs: runtime_capability,
        )
        recorder = _Recorder([0])
        monkeypatch.setattr(prompt_execution, "_default_runner", recorder)

        code = hve_main.main(
            [
                "prompt",
                "run",
                "--request",
                str(request),
                "--expected-sha256",
                approved.sha256,
            ]
        )

        assert code == 2
        assert "stale" in capsys.readouterr().err
        assert recorder.calls == []
        assert settings_store.settings_path().read_bytes() == saved_bytes

    @pytest.mark.parametrize("prompt_command", ["plan", "run"])
    def test_unknown_head_fails_before_orchestrate(
        self,
        prompt_command: str,
        tmp_path: Path,
        isolated_settings: Path,
        capsys,
        monkeypatch,
    ):
        recorder = _Recorder([0])
        monkeypatch.setattr(prompt_execution, "_default_runner", recorder)
        monkeypatch.setattr(prompt_execution, "resolve_head_commit", lambda _root: "unknown")
        request = _write_request(tmp_path)
        argv = ["prompt", prompt_command, "--request", str(request)]
        if prompt_command == "run":
            argv.extend(["--expected-sha256", "a" * 64])

        assert hve_main.main(argv) != 0
        assert recorder.calls == []
        assert "HEAD" in capsys.readouterr().err


class TestSubcommandDocumentationParity:
    def test_prompt_is_documented(self):
        text = Path("hve-dev/requirement-definition.md").read_text(encoding="utf-8")
        assert "| `prompt` |" in text


class TestNoShellEvaluation:
    def test_main_never_builds_a_shell_string_for_prompt(self):
        source = Path("hve/__main__.py").read_text(encoding="utf-8")
        assert "shell=True" not in source
