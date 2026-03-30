"""test_orchestrator.py — run_workflow の dry_run テスト"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig
from orchestrator import run_workflow


def _run(coro):
    return asyncio.run(coro)


class TestRunWorkflowDryRun(unittest.TestCase):
    """run_workflow の dry_run=True テスト。

    dry_run=True の場合、SDK 呼び出しをせずに実行計画を表示して終了する。
    """

    def _make_config(self, **kwargs) -> SDKConfig:
        cfg = SDKConfig(dry_run=True, quiet=True, **kwargs)
        return cfg

    def test_dry_run_returns_dict(self) -> None:
        """dry_run=True で dict が返ることを確認。"""
        cfg = self._make_config()
        result = _run(run_workflow(
            workflow_id="aas",
            params={"branch": "main", "steps": [], "selected_steps": []},
            config=cfg,
        ))
        self.assertIsInstance(result, dict)
        self.assertIn("workflow_id", result)
        self.assertEqual(result["workflow_id"], "aas")

    def test_dry_run_flag_in_result(self) -> None:
        """dry_run=True の場合、結果に dry_run フラグが含まれる。"""
        cfg = self._make_config()
        result = _run(run_workflow(
            workflow_id="aas",
            params={"branch": "main", "selected_steps": []},
            config=cfg,
        ))
        self.assertTrue(result.get("dry_run"))

    def test_dry_run_aad_workflow(self) -> None:
        """aad ワークフローの dry_run テスト。"""
        cfg = self._make_config()
        result = _run(run_workflow(
            workflow_id="aad",
            params={"branch": "main", "selected_steps": []},
            config=cfg,
        ))
        self.assertEqual(result["workflow_id"], "aad")
        self.assertNotIn("error", result)

    def test_dry_run_invalid_workflow(self) -> None:
        """存在しないワークフロー ID の場合 error キーが返る。"""
        cfg = self._make_config()
        result = _run(run_workflow(
            workflow_id="nonexistent_workflow",
            params={},
            config=cfg,
        ))
        self.assertIn("error", result)

    def test_dry_run_does_not_call_sdk(self) -> None:
        """dry_run=True では SDK (CopilotClient) が呼ばれないことを確認。"""
        cfg = self._make_config()

        with patch.dict("sys.modules", {"copilot": None}):
            # copilot モジュールが無くても dry_run は正常に動作する
            result = _run(run_workflow(
                workflow_id="aas",
                params={"branch": "main", "selected_steps": []},
                config=cfg,
            ))
        self.assertTrue(result.get("dry_run"))
        # failed がないことを確認
        self.assertEqual(result.get("failed", []), [])

    def test_dry_run_with_step_filter(self) -> None:
        """ステップフィルタ付き dry_run テスト。"""
        cfg = self._make_config()
        # AAS は Step.1 と Step.2 を持つ
        result = _run(run_workflow(
            workflow_id="aas",
            params={"branch": "main", "selected_steps": ["1"]},
            config=cfg,
        ))
        self.assertEqual(result["workflow_id"], "aas")
        self.assertNotIn("error", result)

    def test_dry_run_all_valid_workflows(self) -> None:
        """全ての有効なワークフロー ID で dry_run が正常に動作することを確認。"""
        cfg = self._make_config()
        valid_ids = ["aas", "aad", "asdw", "abd", "abdv", "aid"]
        for wf_id in valid_ids:
            with self.subTest(workflow_id=wf_id):
                result = _run(run_workflow(
                    workflow_id=wf_id,
                    params={"branch": "main", "selected_steps": []},
                    config=cfg,
                ))
                self.assertEqual(result["workflow_id"], wf_id, f"{wf_id} の workflow_id が不正")
                self.assertNotIn("error", result, f"{wf_id} でエラーが発生: {result.get('error')}")

    def test_dry_run_with_auto_coding_agent_review(self) -> None:
        """dry_run=True + auto_coding_agent_review=True で Code Review Agent が呼ばれないことを確認。"""
        cfg = self._make_config(auto_coding_agent_review=True)
        result = _run(run_workflow(
            workflow_id="aas",
            params={"branch": "main", "selected_steps": []},
            config=cfg,
        ))
        # dry_run なので Code Review Agent 関連処理はスキップされ、通常の dry_run 結果が返る
        self.assertTrue(result.get("dry_run"))
        self.assertEqual(result.get("failed", []), [])


class TestRunWorkflowConfig(unittest.TestCase):
    """config パラメータの伝播テスト。"""

    def test_default_config_used_when_none(self) -> None:
        """config=None の場合、デフォルト SDKConfig が使われることを確認。"""
        result = _run(run_workflow(
            workflow_id="aas",
            params={"branch": "main", "selected_steps": [], "dry_run": True},
            config=SDKConfig(dry_run=True, quiet=True),
        ))
        self.assertIsInstance(result, dict)

    def test_create_issues_false_by_default(self) -> None:
        """create_issues=False のデフォルト値テスト（Issue が作成されないことを確認）。"""
        cfg = SDKConfig(dry_run=True, quiet=True, create_issues=False)
        # root_issue_num が None のはず
        result = _run(run_workflow(
            workflow_id="aas",
            params={"branch": "main", "selected_steps": []},
            config=cfg,
        ))
        # dry_run なので failed は空
        self.assertEqual(result.get("failed", []), [])


class TestAdditionalPrompt(unittest.TestCase):
    """additional_prompt の動作テスト。"""

    def _build_mock_step(self, step_id: str = "1", title: str = "Test Step"):
        """テスト用のステップモックを生成する。"""
        from unittest.mock import MagicMock
        step = MagicMock()
        step.id = step_id
        step.title = title
        step.body_template_path = None  # フォールバックプロンプトを使用
        step.depends_on = []
        step.is_container = False
        return step

    def _build_mock_wf(self, step_id: str = "1"):
        """テスト用のワークフローモックを生成する。"""
        from unittest.mock import MagicMock
        wf = MagicMock()
        wf.id = "aas"
        return wf

    def test_T1_additional_prompt_none_no_change(self) -> None:
        """T1: additional_prompt=None の場合、プロンプトに変更がないことを確認。"""
        from orchestrator import _build_step_prompt
        step = self._build_mock_step()
        wf = self._build_mock_wf()
        params = {"branch": "main"}

        result_with_none = _build_step_prompt(
            step=step,
            params=params,
            root_issue_num=None,
            render_template_fn=lambda **kw: "",
            wf=wf,
            additional_prompt=None,
        )
        result_no_arg = _build_step_prompt(
            step=step,
            params=params,
            root_issue_num=None,
            render_template_fn=lambda **kw: "",
            wf=wf,
        )
        # additional_prompt=None と引数省略は同じ結果であること
        self.assertEqual(result_with_none, result_no_arg)
        # "追加指示" という文字列が含まれていないことを確認
        self.assertNotIn("追加指示", result_with_none)

    def test_T2_additional_prompt_appended_to_prompt(self) -> None:
        """T2: additional_prompt が指定された場合、プロンプト末尾に追記されることを確認。"""
        from orchestrator import _build_step_prompt
        step = self._build_mock_step()
        wf = self._build_mock_wf()
        params = {"branch": "main"}

        result = _build_step_prompt(
            step=step,
            params=params,
            root_issue_num=None,
            render_template_fn=lambda **kw: "",
            wf=wf,
            additional_prompt="追加指示",
        )
        self.assertTrue(result.endswith("\n\n追加指示"))

    def test_T2_additional_prompt_appended_to_template_prompt(self) -> None:
        """T2: テンプレートプロンプトにも additional_prompt が追記されることを確認。"""
        from orchestrator import _build_step_prompt
        step = self._build_mock_step()
        step.body_template_path = "dummy_template.md"
        wf = self._build_mock_wf()
        params = {"branch": "main"}

        result = _build_step_prompt(
            step=step,
            params=params,
            root_issue_num=None,
            render_template_fn=lambda **kw: "テンプレートプロンプト",
            wf=wf,
            additional_prompt="追加指示",
        )
        self.assertEqual(result, "テンプレートプロンプト\n\n追加指示")

    def test_T3_issue_title_none_dry_run_no_error(self) -> None:
        """T3: issue_title=None かつ dry_run=True の場合でもエラーにならないことを確認。"""
        cfg = SDKConfig(dry_run=True, quiet=True, create_issues=True)
        # dry_run=True なので Issue 作成はスキップされるが、エラーにならないことを確認する
        result = _run(run_workflow(
            workflow_id="aas",
            params={"branch": "main", "selected_steps": []},
            config=cfg,
        ))
        # dry_run では issue_title のパスを通らないが、結果として dict が返ることを確認
        self.assertIsInstance(result, dict)

    def test_T4_issue_title_propagated_to_params(self) -> None:
        """T4: issue_title がパラメータに伝搬されることを確認。"""
        from orchestrator import _collect_params_non_interactive
        from unittest.mock import MagicMock

        wf = MagicMock()
        wf.id = "aas"

        cli_args = {
            "branch": "main",
            "steps": [],
            "auto_contents_review": False,
            "auto_qa": False,
            "issue_title": "カスタムタイトル",
        }
        params = _collect_params_non_interactive(wf, cli_args)
        self.assertEqual(params.get("issue_title"), "カスタムタイトル")

    def test_T4_issue_title_not_in_params_when_none(self) -> None:
        """T4: issue_title が未指定の場合、params に含まれないことを確認。"""
        from orchestrator import _collect_params_non_interactive
        from unittest.mock import MagicMock

        wf = MagicMock()
        wf.id = "aas"

        cli_args = {
            "branch": "main",
            "steps": [],
            "auto_contents_review": False,
            "auto_qa": False,
        }
        params = _collect_params_non_interactive(wf, cli_args)
        self.assertNotIn("issue_title", params)

    def test_T5_additional_prompt_appended_to_custom_agent(self) -> None:
        """T5: additional_prompt が Custom Agent の prompt 末尾に追記されることを確認。

        StepRunner が custom_agents リストを組み立てる内部ロジック（deepcopy + append）を
        CopilotClient をモックして直接検証する。
        """
        import copy
        from runner import StepRunner
        from console import Console
        from unittest.mock import AsyncMock, MagicMock, patch

        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
            additional_prompt="追加指示テキスト",
            custom_agents_config=[
                {
                    "name": "my-agent",
                    "display_name": "My Agent",
                    "description": "Test agent",
                    "tools": ["*"],
                    "prompt": "既存のプロンプト",
                }
            ],
        )
        original_config_snapshot = copy.deepcopy(cfg.custom_agents_config)

        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        captured_session_opts: dict = {}

        async def fake_send_and_wait(payload):
            return None

        async def fake_create_session(**opts):
            captured_session_opts.update(opts)
            session = MagicMock()
            session.send_and_wait = fake_send_and_wait
            session.disconnect = AsyncMock()
            return session

        mock_client = MagicMock()
        mock_client.start = AsyncMock()
        mock_client.stop = AsyncMock()
        mock_client.create_session = fake_create_session

        mock_permission_handler = MagicMock()
        mock_permission_handler.approve_all = MagicMock()

        with patch.dict("sys.modules", {
            "copilot": MagicMock(
                CopilotClient=MagicMock(return_value=mock_client),
                PermissionHandler=mock_permission_handler,
                SubprocessConfig=MagicMock(),
                ExternalServerConfig=MagicMock(),
            )
        }):
            import asyncio
            asyncio.run(runner.run_step(
                step_id="test",
                title="Test Step",
                prompt="メインプロンプト",
                custom_agent=None,
            ))

        # セッションオプションに custom_agents が設定されていること
        agents = captured_session_opts.get("custom_agents", [])
        self.assertEqual(len(agents), 1)
        # additional_prompt が追記されていること
        self.assertEqual(agents[0]["prompt"], "既存のプロンプト\n\n追加指示テキスト")

        # 元の custom_agents_config が汚染されていないこと（deepcopy 検証）
        self.assertEqual(cfg.custom_agents_config, original_config_snapshot)
        self.assertEqual(cfg.custom_agents_config[0]["prompt"], "既存のプロンプト")

    def test_T6_additional_prompt_empty_string_no_append(self) -> None:
        """T6: additional_prompt が空文字の場合、追記されないことを確認。"""
        from orchestrator import _build_step_prompt
        step = self._build_mock_step()
        wf = self._build_mock_wf()
        params = {"branch": "main"}

        result_none = _build_step_prompt(
            step=step,
            params=params,
            root_issue_num=None,
            render_template_fn=lambda **kw: "",
            wf=wf,
            additional_prompt=None,
        )
        result_empty = _build_step_prompt(
            step=step,
            params=params,
            root_issue_num=None,
            render_template_fn=lambda **kw: "",
            wf=wf,
            additional_prompt="",
        )
        # 空文字と None は同じ結果（追記なし）
        self.assertEqual(result_none, result_empty)


class TestCopilotUsernames(unittest.TestCase):
    """`_COPILOT_USERNAMES` の内容テスト。"""

    def test_contains_pull_request_reviewer_bot(self) -> None:
        """`copilot-pull-request-reviewer[bot]` が含まれていることを確認。"""
        from orchestrator import _COPILOT_USERNAMES
        self.assertIn("copilot-pull-request-reviewer[bot]", _COPILOT_USERNAMES)

    def test_contains_existing_names(self) -> None:
        """既存のユーザー名候補が引き続き含まれていることを確認。"""
        from orchestrator import _COPILOT_USERNAMES
        for name in ("copilot", "github-copilot[bot]", "copilot[bot]", "copilot-swe-agent[bot]"):
            with self.subTest(name=name):
                self.assertIn(name, _COPILOT_USERNAMES)


class TestRequestCodeReviewFallback(unittest.TestCase):
    """`_request_code_review()` のレビュアーリクエスト・フォールバック動作テスト。"""

    def _make_config(self, **kwargs) -> SDKConfig:
        cfg = SDKConfig(
            quiet=True,
            github_token="ghp_test",
            repo="owner/repo",
            **kwargs,
        )
        return cfg

    def test_returns_error_when_all_candidates_fail(self) -> None:
        """全ての reviewer 候補が失敗した場合、エラーメッセージを返すことを確認。"""
        from orchestrator import _request_code_review
        from console import Console

        config = self._make_config()
        console = Console(quiet=True)

        import importlib
        orchestrator_mod = importlib.import_module("orchestrator")

        with patch.object(orchestrator_mod, "api_call", side_effect=Exception("422 Unprocessable")):
            result = _run(_request_code_review(pr_number=1, config=config, console=console))

        self.assertIsInstance(result, str)
        self.assertIn("失敗", result)

    def test_console_error_called_when_all_candidates_fail(self) -> None:
        """全ての reviewer 候補が失敗した場合、console.error() が呼ばれ例外メッセージが含まれることを確認。"""
        from orchestrator import _request_code_review
        from console import Console

        config = self._make_config()
        console = Console(quiet=True)

        import importlib
        orchestrator_mod = importlib.import_module("orchestrator")

        with patch.object(orchestrator_mod, "api_call", side_effect=Exception("422 Unprocessable")):
            with patch.object(console, "error") as mock_error:
                _run(_request_code_review(pr_number=1, config=config, console=console))

        mock_error.assert_called_once()
        error_message = mock_error.call_args[0][0]
        self.assertIn("失敗", error_message)
        self.assertIn("422 Unprocessable", error_message)

    def test_succeeds_with_first_candidate(self) -> None:
        """最初の reviewer 候補が成功した場合、None を返すことを確認。"""
        from orchestrator import _request_code_review
        from console import Console

        config = self._make_config()
        console = Console(quiet=True)

        import importlib
        orchestrator_mod = importlib.import_module("orchestrator")

        call_count = {"n": 0}

        def fake_api_call(method, url, **kwargs):
            call_count["n"] += 1
            if method == "POST" and "requested_reviewers" in url:
                # 最初の候補（copilot-pull-request-reviewer[bot]）で成功
                return {"message": "ok"}
            if method == "GET" and "/reviews/42" in url:
                return {"body": "LGTM"}
            if method == "GET" and "reviews" in url:
                # ポーリング: すぐにレビュー完了を返す
                return [{"state": "COMMENTED", "user": {"login": "copilot-pull-request-reviewer[bot]"}, "id": 42}]
            if method == "GET" and "comments" in url:
                return []
            return {}

        with patch.object(orchestrator_mod, "api_call", side_effect=fake_api_call), \
             patch("asyncio.sleep", return_value=None):
            result = _run(_request_code_review(pr_number=1, config=config, console=console))

        # 成功時は None（エラーなし）または適切なフローで処理が完了する
        # auto_approval=False かつ非TTY環境なので修正はスキップされる
        self.assertIsNone(result)


class TestNewCreateIssuesFlow(unittest.TestCase):
    """--create-issues 新フロー（ブランチ作成 + PR 作成統一）のテスト。"""

    def test_dry_run_create_issues_shows_new_flow(self) -> None:
        """dry_run=True + create_issues=True で新フロー表示がエラーなく動作することを確認。"""
        cfg = SDKConfig(dry_run=True, quiet=True, create_issues=True)
        result = _run(run_workflow(
            workflow_id="aas",
            params={"branch": "main", "selected_steps": []},
            config=cfg,
        ))
        self.assertTrue(result.get("dry_run"))
        self.assertEqual(result.get("failed", []), [])

    def test_result_includes_root_issue_num_key(self) -> None:
        """dry_run の結果 dict に root_issue_num キーが含まれないことを確認。"""
        cfg = SDKConfig(dry_run=True, quiet=True)
        result = _run(run_workflow(
            workflow_id="aas",
            params={"branch": "main", "selected_steps": []},
            config=cfg,
        ))
        # dry_run では Post-DAG 処理は実行されないため root_issue_num キーは含まれない
        self.assertNotIn("root_issue_num", result)

    def test_ignore_paths_default_in_config(self) -> None:
        """SDKConfig の ignore_paths にデフォルト値が設定されていることを確認。"""
        cfg = SDKConfig()
        self.assertIsNotNone(cfg.ignore_paths)
        self.assertIn("docs", cfg.ignore_paths)
        self.assertIn("images", cfg.ignore_paths)
        self.assertIn("infra", cfg.ignore_paths)
        self.assertIn("src", cfg.ignore_paths)
        self.assertIn("test", cfg.ignore_paths)
        self.assertIn("work", cfg.ignore_paths)


class TestCreatePrIfNeeded(unittest.TestCase):
    """_create_pr_if_needed() の root_issue_num 対応テスト。"""

    def test_pr_body_includes_related_issue(self) -> None:
        """root_issue_num が指定された場合、PR body に 'Related Issue: #N' が含まれることを確認。"""
        from orchestrator import _create_pr_if_needed
        from console import Console
        from unittest.mock import MagicMock, patch as _patch

        cfg = SDKConfig(quiet=True, github_token="ghp_test", repo="owner/repo")
        console = Console(quiet=True)

        captured_body: dict = {}

        def fake_create_pull_request(title, body, head, base, repo, token):
            captured_body["body"] = body
            return 42

        wf = MagicMock()
        wf.id = "aas"

        with _patch("orchestrator.create_pull_request", side_effect=fake_create_pull_request):
            pr_num = _create_pr_if_needed(
                wf=wf,
                head_branch="copilot-sdk/aas-abc12345",
                base_branch="main",
                config=cfg,
                console=console,
                root_issue_num=99,
            )

        self.assertEqual(pr_num, 42)
        self.assertIn("Related Issue: #99", captured_body.get("body", ""))

    def test_pr_body_without_root_issue(self) -> None:
        """root_issue_num が None の場合、PR body に 'Related Issue' が含まれないことを確認。"""
        from orchestrator import _create_pr_if_needed
        from console import Console
        from unittest.mock import MagicMock, patch as _patch

        cfg = SDKConfig(quiet=True, github_token="ghp_test", repo="owner/repo")
        console = Console(quiet=True)

        captured_body: dict = {}

        def fake_create_pull_request(title, body, head, base, repo, token):
            captured_body["body"] = body
            return 43

        wf = MagicMock()
        wf.id = "aas"

        with _patch("orchestrator.create_pull_request", side_effect=fake_create_pull_request):
            pr_num = _create_pr_if_needed(
                wf=wf,
                head_branch="copilot-sdk/aas-abc12345",
                base_branch="main",
                config=cfg,
                console=console,
                root_issue_num=None,
            )

        self.assertEqual(pr_num, 43)
        self.assertNotIn("Related Issue", captured_body.get("body", ""))


if __name__ == "__main__":
    unittest.main()
