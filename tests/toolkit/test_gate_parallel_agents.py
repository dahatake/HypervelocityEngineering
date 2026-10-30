"""並列の作業役（同じ名前の implementer など）が止まったとき、動いている別の作業役の記録を消さない。hooks の保守用の許可設定。"""
import json
import sys

from conftest import SOURCE

from test_multi_run import _real_subagent_start, meta_path, patch_meta, start_in_worktree
from test_parallel_hook import denied, create, start_primary_run

sys.path.insert(0, str(SOURCE / "scripts"))


def _stop(sample, parent, agent_id, name="reviewer"):
    return sample.gate("subagent-stop", {"sessionId": parent, "agentId": agent_id, "agentType": name,
                                         "agentName": name, "cwd": str(sample.path)})


def test_stopping_one_parallel_agent_keeps_the_others_session_mapping(sample):
    # real incident: three same-name agents; the first stop released "the first one named X" (another running agent's record)
    # and that agent's writes were then judged as coming from an unknown session (spurious G-5)
    run = start_in_worktree(sample)
    patch_meta(run, session_id="sA")
    for aid in ("agent-1", "agent-2", "agent-3"):
        _real_subagent_start(sample, "sA", aid, name="reviewer")
    _stop(sample, "sA", "agent-3")
    edit = {"sessionId": "agent-1", "cwd": str(sample.path), "toolName": "create", "toolArgs": {
        "path": str(run / "work" / "peek.py"), "file_text": "x"}}
    assert sample.gate("pre-tool", edit) == {}
    assert sample.gate("pre-tool", dict(edit, sessionId="agent-2")) == {}


def test_agent_id_is_released_exactly_once(sample):
    run = start_in_worktree(sample)
    patch_meta(run, session_id="sA")
    for aid in ("agent-1", "agent-2"):
        _real_subagent_start(sample, "sA", aid, name="reviewer")
    _stop(sample, "sA", "agent-1")
    records = json.loads((run / "work" / ".ebak" / "active-agents.json").read_text(encoding="utf-8"))
    assert [r.get("agent_id") for r in records] == ["agent-2"]


def test_hook_edit_is_allowed_only_when_the_repository_opts_in(sample):
    start_primary_run(sample, "owner")
    _real_subagent_start(sample, "owner", "agent-1", name="implementer")  # the conductor itself never edits hooks
    hooks = sample.path / "scripts" / "hooks" / "gate.py"
    assert denied(create(sample, "agent-1", hooks))
    cfg_path = sample.path / "scripts" / "ebak.config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg.setdefault("gates", {})["allow_hook_edit"] = True
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    assert not denied(create(sample, "agent-1", hooks))
    assert denied(create(sample, "agent-1", sample.path / "docs" / "id-registry.md"))  # other gates stay
