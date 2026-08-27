"""FR-PROMPT-03 / FR-PROMPT-04 — `hve prompt plan|run` と `--input-alias` の契約テスト。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

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
