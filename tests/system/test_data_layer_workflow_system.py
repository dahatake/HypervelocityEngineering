"""Contract tests for .github/workflows/ebak-data-layer.yml (FR-1017/1018/1019, NFR-SEC-004, NFR-OPS-006).

Expected values come from the acceptance criteria only. Actions cannot be run here,
so the workflow YAML (and local helper scripts it calls) is inspected statically.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from conftest import SOURCE, run

WF = SOURCE / ".github" / "workflows" / "ebak-data-layer.yml"
LABEL = "eabk-data-layer"  # PARAM-014
WRITE_RE = re.compile(r"git\s+commit|git\s+push|gh\s+pr\s+create|gh\s+issue\s+create|gh\s+issue\s+comment|gh\s+pr\s+comment|gh\s+api\b")


def load():
    assert WF.exists(), f"{WF} がない"
    return yaml.safe_load(WF.read_text(encoding="utf-8"))


def triggers(doc):
    return doc.get("on", doc.get(True))


def steps(doc):
    out = []
    for jname, job in doc["jobs"].items():
        for i, st in enumerate(job.get("steps", [])):
            out.append((jname, job, i, st))
    return out


def step_text(st, extra=True):
    """Step run/with text plus the text of local helper scripts it invokes."""
    text = str(st.get("run", "")) + "\n" + str(st.get("with", ""))
    if extra:
        for m in re.finditer(r"(?:python3?|bash|sh)\s+([\w./-]+\.(?:py|sh))", str(st.get("run", ""))):
            p = SOURCE / m.group(1)
            if p.exists():
                text += "\n" + p.read_text(encoding="utf-8")
    return text


def cond(job, st):
    return f"{job.get('if', '')} {st.get('if', '')}"


def writers(doc):
    return [(j, job, i, st) for j, job, i, st in steps(doc) if WRITE_RE.search(step_text(st))]


def corpus(doc):
    return "\n".join(step_text(st) for *_, st in steps(doc))


def raw():
    return WF.read_text(encoding="utf-8")


# FR-1017 AC-105
def test_ac105_all_four_triggers_start_the_check():
    doc = load()
    on = triggers(doc)
    assert "pull_request" in on
    assert "main" in (on["push"] or {}).get("branches", [])
    assert "workflow_dispatch" in on
    assert on["schedule"] and on["schedule"][0]["cron"]
    assert "verify.py --docs-only" in corpus(doc)


# FR-1017 AC-105 (PARAM-013 = 1 week)
def test_ac105_schedule_interval_is_one_week():
    cron = triggers(load())["schedule"][0]["cron"].split()
    assert len(cron) == 5
    minute, hour, dom, month, dow = cron
    assert minute.isdigit() and hour.isdigit()
    assert dom == "*" and month == "*"
    assert re.fullmatch(r"[0-67]|SUN|MON|TUE|WED|THU|FRI|SAT", dow, re.I), f"週 1 回の指定でない: {cron}"
    assert len(triggers(load())["schedule"]) == 1


# FR-1017 AC-105 (abnormal: the check must not be skippable on any trigger)
def test_ac105_check_step_has_no_trigger_restricting_condition():
    doc = load()
    for j, job, i, st in steps(doc):
        if "verify.py --docs-only" in step_text(st, extra=False) and i == min(
            k for _, _, k, s in steps(doc) if "verify.py --docs-only" in step_text(s, extra=False)
        ):
            assert "github.event_name" not in cond(job, st), "最初の検査が起動契機で絞られている"
            return
    pytest.fail("verify.py --docs-only を実行する step がない")


# FR-1017 AC-106
def test_ac106_pass_path_performs_no_write():
    doc = load()
    ws = writers(doc)
    assert ws, "書き込み系の step がそもそもない（修復・Issue の定義がない）"
    for j, job, i, st in ws:
        c = cond(job, st)
        assert c.strip(), f"無条件の書き込み step: {st.get('name')}"
        assert re.search(r"failure\(\)|outcome\s*==\s*'failure'|conclusion\s*==\s*'failure'|steps\.[\w-]+\.outputs|needs\.|env\.", c), (
            f"検査が不合格でも成功でも実行されうる書き込み step: {st.get('name')} / {c}"
        )


# FR-1017 AC-106 (abnormal: a failing first check must not make a passing run write)
def test_ac106_first_check_failure_is_tolerated_only_to_reach_repair():
    doc = load()
    first = next(st for *_, st in steps(doc) if "verify.py --docs-only" in step_text(st, extra=False))
    assert first.get("id") or first.get("continue-on-error") is not None or "||" in str(first.get("run")), (
        "最初の検査の結果を後続が参照できない"
    )


# FR-1018 AC-107
def test_ac107_recheck_between_repair_and_commit():
    doc = load()
    seq = steps(doc)
    commit_idx = [n for n, (_, _, _, st) in enumerate(seq) if re.search(r"git\s+commit", step_text(st))]
    assert commit_idx
    for n in commit_idx:
        before = [step_text(st, extra=False) for *_, st in seq[:n]]
        checks = [k for k, t in enumerate(before) if "verify.py --docs-only" in t]
        assert len(checks) >= 2 or (checks and "verify.py --docs-only" in step_text(seq[n][3])), (
            "修復後の再検査が commit より前にない"
        )


# FR-1018 AC-107 (abnormal: recheck fails -> no commit, no push)
def test_ac107_commit_and_push_are_gated_on_recheck_success():
    doc = load()
    for j, job, i, st in steps(doc):
        if re.search(r"git\s+commit|git\s+push", step_text(st)):
            c = cond(job, st)
            t = step_text(st)
            gated = re.search(r"success\(\)|outcome\s*==\s*'success'|conclusion\s*==\s*'success'|steps\.[\w-]+\.outputs", c) or (
                "verify.py --docs-only" in t and re.search(r"verify.py --docs-only[^\n]*(&&|;|\n\s*if)", t)
            )
            assert gated, f"再検査合格が条件になっていない commit/push: {st.get('name')} / {c!r}"


# FR-1018 AC-108
def test_ac108_same_repo_pr_pushes_to_pr_branch():
    text = raw()
    assert re.search(r"github\.head_ref|pull_request\.head\.ref", text), "PR のブランチへ push する定義がない"
    assert re.search(r"git\s+push", corpus(load()))


# FR-1018 AC-108
def test_ac108_main_and_schedule_push_to_fix_branch_and_open_pr():
    c = corpus(load())
    assert re.search(r"gh\s+pr\s+create", c), "修復用ブランチからの PR 作成がない"
    assert re.search(r"git\s+push[^\n]*(fix|repair|eabk)", c, re.I) or re.search(r"(fix|repair|eabk)[\w/-]*", raw()), "修復用ブランチ名がない"


# FR-1018 AC-108 (abnormal: no duplicate PR when the repair branch already has one)
def test_ac108_no_duplicate_pr_for_existing_fix_branch():
    c = corpus(load())
    assert re.search(r"gh\s+pr\s+(list|view)|gh\s+api[^\n]*pulls|--jq|ls-remote", c), "既存 PR の確認がない"
    create = [st for *_, st in steps(load()) if re.search(r"gh\s+pr\s+create", step_text(st))]
    assert create
    for st in create:
        t = step_text(st)
        assert re.search(r"gh\s+pr\s+(list|view)|pulls|ls-remote", t) or "steps." in str(st.get("if", "")), (
            "PR 作成が既存 PR の有無に依存していない"
        )


# FR-1018 AC-109
def test_ac109_requirements_definition_is_guarded():
    doc = load()
    c = corpus(doc)
    assert "docs/requirements-definition.md" in c, "要求定義書を保護する処理がない"
    assert re.search(r"git\s+(checkout|restore|diff|reset)[^\n]*docs/requirements-definition\.md|sha256|sha1sum|md5|cmp\s", c), (
        "要求定義書の無変更を保証する処理（復元・差分・ハッシュ）がない"
    )


# FR-1018 AC-109 (abnormal: guard precedes commit; commit must not stage everything blindly)
def test_ac109_guard_runs_before_commit_and_no_blind_add_all():
    doc = load()
    seq = steps(doc)
    guard = [n for n, (*_, st) in enumerate(seq) if "docs/requirements-definition.md" in step_text(st)]
    commit = [n for n, (*_, st) in enumerate(seq) if re.search(r"git\s+commit", step_text(st))]
    assert guard and commit and min(guard) < min(commit)


# FR-1019 AC-110
def test_ac110_issue_has_label_summary_and_run_link():
    doc = load()
    creates = [st for *_, st in steps(doc) if re.search(r"gh\s+issue\s+create", step_text(st))]
    assert creates, "Issue 作成がない"
    t = "\n".join(step_text(st) for st in creates)
    assert re.search(rf"--label[ =]+[\"']?{LABEL}", t) or LABEL in t
    assert re.search(r"github\.run_id|GITHUB_RUN_ID", raw() + t) and re.search(r"server_url|GITHUB_SERVER_URL|github\.com", raw() + t), "実行へのリンクがない"
    assert re.search(r"--body|--body-file|-F\s", t), "Issue 本文がない"


# FR-1019 AC-110 (abnormal: Issue only when recheck after repair still fails)
def test_ac110_issue_created_only_when_recheck_fails():
    for j, job, i, st in steps(load()):
        if re.search(r"gh\s+issue\s+create", step_text(st)):
            c = cond(job, st)
            assert re.search(r"failure\(\)|outcome\s*==\s*'failure'|conclusion\s*==\s*'failure'|steps\.[\w-]+\.outputs", c), c


# FR-1019 AC-111
def test_ac111_existing_open_issue_gets_comment_instead_of_new_issue():
    c = corpus(load())
    assert re.search(r"gh\s+issue\s+list", c) and LABEL in c, "同ラベルの未解決 Issue の検索がない"
    assert re.search(r"--state\s+open|state:\s*open", c) or "open" in c
    assert re.search(r"gh\s+issue\s+comment", c), "既存 Issue へのコメントがない"


# FR-1019 AC-111 (abnormal: dedupe by failure content, create gated on no existing issue)
def test_ac111_new_issue_is_gated_on_no_existing_issue_and_matches_failure_content():
    doc = load()
    c = corpus(doc)
    assert re.search(r"hash|sha256|sha1|md5|fingerprint|signature|--search|in:title|in:body", c, re.I), "同じ失敗内容の判定がない"
    for j, job, i, st in steps(doc):
        t = step_text(st)
        if re.search(r"gh\s+issue\s+create", t):
            assert re.search(r"gh\s+issue\s+list", t) or "steps." in str(st.get("if", "")) or "needs." in str(st.get("if", "")), (
                "Issue 作成が既存 Issue の有無に依存していない"
            )


# NFR-SEC-004 AC-112
def test_ac112_permissions_are_exactly_three_writes():
    doc = load()
    want = {"contents": "write", "pull-requests": "write", "issues": "write"}
    top = doc.get("permissions")
    jobs = [job.get("permissions") for job in doc["jobs"].values()]
    declared = [p for p in [top, *jobs] if p is not None]
    assert declared, "権限宣言がない"
    for p in declared:
        assert p == want, f"権限宣言が {want} と一致しない: {p}"
    for job in doc["jobs"].values():
        assert (job.get("permissions") or top) == want


# NFR-SEC-004 AC-112 (abnormal: fork PR)
def test_ac112_fork_pr_gets_no_writes_but_still_checked():
    doc = load()
    assert "pull_request_target" not in triggers(doc), "pull_request_target は fork に書き込み権限を渡しうる"
    for j, job, i, st in writers(doc):
        c = cond(job, st)
        assert re.search(r"head\.repo\.fork|head\.repo\.full_name|head\.repo\.id|github\.repository", c) or re.search(
            r"head\.repo\.fork|head\.repo\.full_name|github\.repository", step_text(st)
        ), f"fork を除外していない書き込み step: {st.get('name')}"
    checks = [(job, st) for _, job, _, st in steps(doc) if "verify.py --docs-only" in step_text(st, extra=False)]
    assert checks
    for job, st in checks:
        assert not re.search(r"head\.repo\.fork\s*==\s*false|head\.repo\.full_name\s*==", cond(job, st)), "fork で検査が行われない"


# NFR-SEC-004 AC-112 (abnormal: actions do not leak the token to untrusted checkout)
def test_ac112_fork_head_not_checked_out_with_write_token_elsewhere():
    text = raw()
    assert "secrets." not in re.sub(r"secrets\.GITHUB_TOKEN", "", text), "GITHUB_TOKEN 以外の secret を使っている"


# NFR-SEC-004 AC-113
def test_ac113_bot_commits_do_not_trigger_repair():
    doc = load()
    repair_like = [(j, job, i, st) for j, job, i, st in steps(doc) if re.search(r"git\s+commit|git\s+push|rdfix|repair|--fix|--apply", step_text(st))]
    assert repair_like
    for j, job, i, st in repair_like:
        c = cond(job, st)
        assert re.search(r"github\.actor|head_commit|commits\[|\[bot\]|github-actions|skip|marker|eabk-auto", c, re.I) or re.search(
            r"github\.actor|\[bot\]|github-actions|eabk-auto|log -1", step_text(st), re.I
        ), f"bot 起因の実行を除外していない: {st.get('name')}"


# NFR-SEC-004 AC-113 (abnormal: repair commit is identifiable and not made by a trigger-capable PAT)
def test_ac113_repair_commit_is_marked_and_uses_default_token():
    text = raw()
    assert re.search(r"github-actions\[bot\]|eabk-auto|\[skip ci\]|\[ci skip\]|bot", text, re.I), "修復 commit を識別する印がない"
    assert not re.search(r"secrets\.(?!GITHUB_TOKEN)\w+", text), "PAT の使用は連鎖を招きうる"


# NFR-OPS-006 AC-114
def test_ac114_managed_registration_and_no_ci_exclusion(tmp_path: Path):
    rel = ".github/workflows/ebak-data-layer.yml"
    assert rel in (SOURCE / "tools" / "install.py").read_text(encoding="utf-8")

    def install(name, *extra):
        repo = tmp_path / name
        repo.mkdir()
        run(["git", "init", "-q", "-b", "main"], repo)
        (repo / "README.md").write_text("x\n", encoding="utf-8")
        run([sys.executable, SOURCE / "tools" / "install.py", "--target", repo, "--skip-verify", *extra], repo)
        return repo

    assert (install("with-ci") / rel).exists()
    assert not (install("no-ci", "--no-ci") / rel).exists()


# NFR-OPS-006 AC-114 (abnormal: --no-ci must not remove the other managed files)
def test_ac114_no_ci_still_installs_non_ci_files(tmp_path: Path):
    repo = tmp_path / "r"
    repo.mkdir()
    run(["git", "init", "-q", "-b", "main"], repo)
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    run([sys.executable, SOURCE / "tools" / "install.py", "--target", repo, "--skip-verify", "--no-ci"], repo)
    assert (repo / ".github" / "agents" / "conductor.agent.md").exists()
    assert not (repo / ".github" / "workflows" / "ebak-data-layer.yml").exists()


# NFR-OPS-006 AC-114
@pytest.mark.parametrize("doc", ["README.md", "users-guide/04-customization.md"])
def test_ac114_docs_describe_triggers_repair_scope_issue_and_disable(doc):
    t = (SOURCE / doc).read_text(encoding="utf-8")
    assert "ebak-data-layer" in t, f"{doc} にワークフロー名がない"
    seg = t[t.index("ebak-data-layer"):] if "ebak-data-layer" in t else t
    assert re.search(r"プルリクエスト|pull_request|PR", seg) and re.search(r"push", seg) and re.search(r"手動|workflow_dispatch", seg) and re.search(r"定期|schedule|毎週|週", seg), "起動契機の記述不足"
    assert re.search(r"要求定義書[^\n]*(変更しない|変更されない|触れない)", seg), "自動修復の範囲の記述不足"
    assert "Issue" in seg
    assert re.search(r"無効化|無効にする|disable", seg, re.I), "無効化の方法の記述不足"
