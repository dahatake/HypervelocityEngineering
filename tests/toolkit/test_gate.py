import json

from conftest import git


def edit(repo, path, tool="edit"):
    return repo.gate("pre-tool", {"toolName": tool, "toolArgs": {"path": str(repo.path / path), "old_str": "a", "new_str": "b"}})


def shell(repo, cmd, tool="bash"):
    return repo.gate("pre-tool", {"toolName": tool, "toolArgs": {"command": cmd}})


def denied(res, gate=None):
    ok = res.get("permissionDecision") == "deny"
    return ok and (gate is None or f"[{gate}]" in res.get("permissionDecisionReason", ""))


def start(repo, opts="max_hours: 24"):
    return repo.py("run-state.py", "start", "--options", opts, check=True).stdout.split()[1]


def test_no_run_allows_normal_edits_but_guards_records(sample):
    assert edit(sample, "src/app.py") == {}
    assert edit(sample, "docs/requirements-definition.md") == {}
    assert denied(edit(sample, "docs/id-registry.md"), "G-3")
    assert denied(edit(sample, "tests/system/ledger.json"), "G-2")
    assert denied(edit(sample, "docs/build.log", tool="create"), "G-6")
    assert edit(sample, "work/runs/x/build.log", tool="create") == {}


def test_requirements_writer_is_rd_author_only(sample):
    start(sample)
    assert denied(edit(sample, "docs/requirements-definition.md"), "G-1")
    sample.gate("subagent-start", {"agentName": "rd-author"})
    assert edit(sample, "docs/requirements-definition.md") == {}
    assert edit(sample, "docs/catalog.md") == {}
    assert denied(edit(sample, "src/app.py"), "G-5")  # rd-author edits docs only
    sample.gate("subagent-stop", {"agentName": "rd-author", "agentId": "a1", "response": "RESULT: done"})
    assert denied(edit(sample, "docs/requirements-definition.md"), "G-1")


def test_system_tests_are_immutable_for_implementer(sample):
    start(sample)
    sample.gate("subagent-start", {"agentName": "test-designer"})
    assert edit(sample, "tests/system/e2e/a.spec.ts", tool="create") == {}
    assert denied(edit(sample, "src/app.ts"), "G-5")
    sample.gate("subagent-stop", {"agentName": "test-designer", "agentId": "t1", "response": "RESULT: done"})
    sample.gate("subagent-start", {"agentName": "implementer"})
    assert denied(edit(sample, "tests/system/e2e/a.spec.ts"), "G-2")
    assert denied(shell(sample, "rm tests/system/e2e/a.spec.ts"), "G-2")
    assert denied(shell(sample, "python scripts/ledger.py update E2E-001 --command x --reason y"), "G-2")
    wt = "work/worktrees/run-I-01/"
    assert edit(sample, wt + "src/app.ts") == {}
    assert denied(edit(sample, wt + "tests/system/e2e/a.spec.ts"), "G-2")
    assert denied(edit(sample, wt + "docs/requirements-definition.md"), "G-1")


def test_read_only_roles_and_conductor_scope(sample):
    start(sample)
    assert denied(edit(sample, "src/app.ts"), "G-5")  # conductor itself
    assert edit(sample, "docs/run-history.md") == {}
    assert edit(sample, "work/runs/x/run-report.md", tool="create") == {}
    sample.gate("subagent-start", {"agentName": "rd-auditor"})
    assert denied(edit(sample, "docs/catalog.md"), "G-5")
    assert edit(sample, "work/runs/x/audit/r1.md", tool="create") == {}


def test_apply_patch_paths_are_checked(sample):
    start(sample)
    patch = "*** Begin Patch\n*** Update File: docs/requirements-definition.md\n@@\n-a\n+b\n*** End Patch"
    res = sample.gate("pre-tool", {"toolName": "apply_patch", "toolArgs": {"input": patch}})
    assert denied(res, "G-1")
    res = sample.gate("pre-tool", {"tool_name": "Edit", "tool_input": {"file_path": str(sample.path / "docs/requirements-definition.md")}})
    assert denied(res, "G-1")


def test_dangerous_shell_commands(sample):
    assert denied(shell(sample, "git push --force origin work/x"), "G-5")
    assert denied(shell(sample, "git push origin main"), "G-5")
    assert denied(shell(sample, "git push origin HEAD:main", tool="powershell"), "G-5")
    assert shell(sample, "git push origin feature/x") == {}  # outside a run: allowed
    assert denied(shell(sample, "rm -rf work/runs"), "G-6")
    assert shell(sample, "python scripts/clean-work.py") == {}
    start(sample)
    assert denied(shell(sample, "git push origin run/x"), "G-5")  # git_push: しない
    assert denied(shell(sample, "azd up"), "G-5")
    assert denied(shell(sample, "terraform apply -auto-approve"), "G-5")
    assert shell(sample, "git worktree add work/worktrees/r-I-01 -b work/r/I-01 HEAD") == {}
    assert shell(sample, "git worktree remove --force work/worktrees/r-I-01") == {}
    assert shell(sample, "npm test") == {}


def test_options_allow_push_and_deploy(sample):
    start(sample, "git_push: 作業ブランチへ push する\ndeploy: する")
    assert shell(sample, "git push origin run/x") == {}
    assert shell(sample, "azd deploy") == {}
    assert denied(shell(sample, "git push origin main"), "G-5")


def test_commit_on_main_is_denied_during_run(sample):
    start(sample)
    git(sample.path, "switch", "-q", "main")
    assert denied(shell(sample, "git commit -m x"), "G-5")


def tool(repo, name, args=None):
    return repo.gate("pre-tool", {"toolName": name, "toolArgs": args or {}})


def test_external_tools_read_always_write_only_when_allowed(sample):
    # outside a run: user-configured MCP / plugin tools are not restricted (the user approves in the client)
    assert tool(sample, "workiq-create_entity") == {}
    start(sample)
    for name in ("workiq-ask", "workiq-retrieve", "microsoft-learn-microsoft_docs_fetch",
                 "mcp_azure_query_azure_resource_graph", "github-mcp-server-get_file_contents", "doSearch"):
        assert tool(sample, name) == {}, name
    for name in ("workiq-create_entity", "workiq-do_action", "mcp_outlook_sendMail",
                 "github-mcp-server-create_or_update_file", "Foundry-MCP-agent_delete", "addComment"):
        assert denied(tool(sample, name, {"path": "README.md"}), "G-5"), name
    assert "external_write" in tool(sample, "workiq-update_entity")["permissionDecisionReason"]
    assert "deploy" in tool(sample, "Foundry-MCP-model_deploy")["permissionDecisionReason"]
    # built-in tools keep their own (path based) rules
    assert edit(sample, "work/runs/x/a.md", tool="create") == {}
    assert edit(sample, "work/runs/x/a.md", tool="create_file") == {}
    assert shell(sample, "npm test", tool="run_in_terminal") == {}


def test_copilot_app_session_tools(sample):
    # GitHub Copilot app tools: local app state only, never treated as external writes
    assert tool(sample, "rename_branch", {"name": "feature-x"}) == {}  # before a run: allowed
    start(sample)
    assert tool(sample, "rename_session", {"title": "x"}) == {}
    assert tool(sample, "send_session_message", {"message": "x"}) == {}
    res = tool(sample, "rename_branch", {"name": "feature-x"})
    assert denied(res, "G-5") and "integration_branch" in res["permissionDecisionReason"]
    sample.gate("subagent-start", {"agentName": "rd-auditor"})
    assert tool(sample, "rename_session", {"title": "y"}) == {}


def test_external_write_and_deploy_options(sample):
    start(sample, "external_write: する")
    assert tool(sample, "workiq-create_entity") == {}
    assert denied(tool(sample, "mcp_copilotstudio_publish_agent"), "G-5")  # deploy: しない
    sample.gate("subagent-start", {"agentName": "reviewer"})
    assert denied(tool(sample, "workiq-create_entity"), "G-5")  # read-only role
    assert tool(sample, "workiq-ask") == {}


def test_external_deploy_allowed_and_allow_list(sample):
    start(sample, "deploy: する")
    assert tool(sample, "mcp_azure_deploy_app") == {}
    assert denied(tool(sample, "mcp_myindex_update_index"), "G-5")
    cfg_path = sample.path / "scripts" / "hve.config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["gates"]["external_tool_allow"] = ["^mcp_myindex_update_index$"]
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    assert tool(sample, "mcp_myindex_update_index") == {}


def test_subagent_stop_runs_verify(sample):
    start(sample)
    sample.gate("subagent-start", {"agentName": "rd-author"})
    bad = sample.read("docs/requirements-definition.md").replace("- 上位: G-001", "- 上位: G-999")
    sample.write("docs/requirements-definition.md", bad)
    res = sample.gate("subagent-stop", {"agentName": "rd-author", "agentId": "x", "response": "RESULT: done"})
    assert res.get("decision") == "block" and "G-4" in res["reason"] and "CHK-04" in res["reason"]
    for _ in range(2):
        sample.gate("subagent-stop", {"agentName": "rd-author", "agentId": "x", "response": "RESULT: done"})
    res = sample.gate("subagent-stop", {"agentName": "rd-author", "agentId": "x", "response": "RESULT: done"})
    assert "decision" not in res and res["modifiedResponse"].startswith("GATE G-4")


def test_subagent_stop_uses_worktree(sample):
    start(sample)
    wt = sample.path / "work" / "worktrees" / "r-I-01"
    git(sample.path, "worktree", "add", "-q", str(wt), "-b", "work/r/I-01")
    sample.gate("subagent-start", {"agentName": "implementer"})
    res = sample.gate("subagent-stop", {"agentName": "implementer", "agentId": "i1", "response": f"WORKTREE: {wt}\nGATE: pass"})
    assert res == {}


def test_agent_stop_blocks_until_complete(sample):
    rid = start(sample)
    res = sample.gate("agent-stop", {"sessionId": "s1", "stopReason": "end_turn"})
    assert res.get("decision") == "block" and "run-state.py status" in res["reason"]
    assert sample.gate("agent-stop", {"sessionId": "other"}) == {}  # different session is not the conductor
    sample.py("run-state.py", "stage", "3", "--done", check=True)
    sample.py("run-state.py", "stage", "6", "--done", check=True)
    sample.write(f"work/runs/{rid}/run-report.md", "done\n")
    assert sample.gate("agent-stop", {"sessionId": "s1"}) == {}


def test_session_start_injects_resume_hint(sample):
    assert sample.gate("session-start", {"source": "new"}) == {}
    rid = start(sample)
    res = sample.gate("session-start", {"source": "resume"})
    assert rid in res["additionalContext"]


def test_gate_never_bricks_on_bad_input(sample):
    import subprocess
    import sys
    proc = subprocess.run([sys.executable, str(sample.path / "scripts" / "hooks" / "gate.py"), "pre-tool"],
                          cwd=str(sample.path), input="not json", capture_output=True, text=True)
    assert proc.returncode == 0


def test_hooks_config_is_valid(sample):
    cfg = json.loads(sample.read(".github/hooks/quality-gates.json"))
    assert cfg["version"] == 1
    for ev in ("sessionStart", "preToolUse", "subagentStart", "subagentStop", "agentStop"):
        entry = cfg["hooks"][ev][0]
        assert "gate.py" in entry["bash"] and "gate.py" in entry["powershell"]
