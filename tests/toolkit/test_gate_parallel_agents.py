"""FR-1010 AC-448・449（取り込み待ちの再差し戻し抑制）。並列の作業役（同じ名前の implementer など）が止まったとき、動いている別の作業役の記録を消さない。hooks の保守用の許可設定。"""
import json
import sys

from conftest import SOURCE, git

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


def _finished_run_waiting_to_land(sample):
    wt = start_in_worktree(sample)
    (wt / "x.txt").write_text("x\n", encoding="utf-8")
    git(wt, "add", "-A")
    git(wt, "commit", "-q", "-m", "work")
    patch_meta(wt, status="finished", result="全件完了", session_id="sA")
    return wt


def test_same_land_blocker_is_pushed_back_once_then_allowed_ac448(sample):
    wt = _finished_run_waiting_to_land(sample)
    first = sample.gate("agent-stop", {"sessionId": "sA"})
    assert first.get("decision") == "block"
    second = sample.gate("agent-stop", {"sessionId": "sA"})
    assert second.get("decision") != "block" and "取り込み待ち" in second.get("systemMessage", "")
    assert sample.gate("agent-stop", {"sessionId": "sA"}) == {}  # the next step is shown only once
    assert wt.exists() and git(sample.path, "branch", "--list", "run/*").strip()  # nothing is cleaned or changed


def test_changed_land_blocker_is_pushed_back_again_ac449(sample):
    _finished_run_waiting_to_land(sample)
    assert sample.gate("agent-stop", {"sessionId": "sA"}).get("decision") == "block"
    assert sample.gate("agent-stop", {"sessionId": "sA"}).get("decision") != "block"
    dirty = sample.path / "README.md"
    before = dirty.read_text(encoding="utf-8")
    dirty.write_text(before + "unrelated edit\n", encoding="utf-8")  # the primary tree's state changed
    assert sample.gate("agent-stop", {"sessionId": "sA"}).get("decision") == "block"
    assert dirty.read_text(encoding="utf-8") == before + "unrelated edit\n"  # never touched by the hook
    assert not git(sample.path, "stash", "list").strip()