[日本語](02-during-and-after-run.md) | **English**

# 2. During and After a Run

## 2.1 Checking progress

Run the following commands in the conductor's working tree (for VS Code's New Worktree or a new working tree in the GitHub Copilot app, that is the session's worktree). All of them are read-only and do not affect a run in progress. The GitHub Copilot app's worktree is, by default, at `<parent of repository>/copilot-worktrees/<repository name>/<branch name>` (you can check with `git worktree list`).

```bash
python scripts/run-state.py status          # run-id, elapsed time and time budget, integration branch, step, queue counts, tail of progress
python scripts/run-state.py queue show      # status, attempt count, and branch for each item
python scripts/ledger.py summary -v         # System Test pass / fail / blocked / not_run
git log --oneline --graph -20               # [RD] [ST] [FR-xxx] commits and integrations
```

Operations that hooks rejected or sent back are recorded in `work/.ebak/gate.log`.

## 2.2 Resuming after a stop

State is persisted in files under `/work` and in git, so you can resume from where you left off no matter when it stopped.

| Situation | Action |
|---|---|
| Autopilot ended its turn but the completion conditions are not met | Send "continue" in the same session. The agentStop hook automatically keeps it going until the completion conditions are met (up to 40 times) |
| PC restart or Agent Host stopped | In a new session, send the same Prompt again. The conductor resumes from the state files under `/work` and git as `RESUME <run-id>` |
| GitHub Copilot app restart or session interruption | Open the **same session** from the sidebar and send "continue". Creating a new session with a new working tree results in a different worktree, and because there is no `/work` state it would start as a new run. If you were running in the local repository, you can also resume in a new session |
| You want to quit midway | Stop the session. Items integrated up to that point are already committed to the integration branch. If you delete `work/current-run.txt`, the next request starts as a new run |

Conditions under which the conductor stops by itself:

| Condition | Behavior |
|---|---|
| All items in the queue are done or blocked | Proceed to step 6 and finish |
| 85% of `max_hours` exceeded | Do not start new items; proceed to step 6 |
| The same item failed the gate 3 times in a row | Retry once with a higher-tier model; if it still fails, mark it blocked and record the cause |
| The canary fails and is not fixed after 3 repair attempts | Stop the implementation loop and proceed to step 6 |
| In the latest integration, verify on the integration branch turned to failure | Revert that integration and return the item to todo |

Completion is determined not by the model's self-declared "done" but by `python scripts/run-state.py complete-check` returning exit 0. Exit 0 requires three things: the queue has no todo or doing items, step 6 is finished, and run-report.md exists. For a run whose result is "all complete," the agentStop hook further rejects termination until it has been merged into main with `python scripts/run-state.py land` (even if multiple runs complete at the same time, merges are performed one at a time under a shared lock. On a conflict or verify failure, it is reverted automatically, and the conductor resolves it and re-runs). A run with "blocked items" is not merged even if the completion conditions are met, and is not regarded as fully successful.

## 2.3 What to read after a run

`work/runs/<run-id>/run-report.md` contains the following.

- Line 1: result (all complete / has blocked items / stopped by time budget / stopped by canary failure), elapsed time, AI credits
- Requirement IDs implemented, BLOCKED requirement IDs and their reasons
- **Blanket-approved items** (in descending order of impact) … if they differ from your intent, revoke them in the next `<answers>`
- **Unanswered questionnaire** (in descending order of importance) … in a format you can write into the next `<answers>` as is
- Quality metrics: verify, AC pass rate, audit findings (counts of CRITICAL and HIGH)
- **KPI**: the North Star "verified requirements per human intervention," first-time gate pass rate, traceability coverage, and so on. The HTML version is `work/runs/<run-id>/kpi.html`. An aggregate across past runs can be shown with `python scripts/kpi.py history`
- Merge method: the integration branch name and the merge command

`/work` is deleted after 14 days, but the key points are transcribed to the following permanent locations. The state of requirements, the catalog, and tests can be viewed as diagrams and tables in [EABK Studio](studio/README.en.md) (`python EABK-Studio/studio.py`).

| Information | Location |
|---|---|
| Run summary and KPI (one line per run) | `docs/run-history.md` |
| Decisions reflecting blanket approvals and answers | "Decision log" in the requirements definition document |
| Unanswered questionnaire and approval requests | "Assumptions and open issues" in the requirements definition document |
| Unresolved audit findings | "Audit findings" in the requirements definition document |
| Latest System Test state | `tests/system/ledger.json` |

## 2.4 Merging

### Running multiple runs in parallel

You may start multiple `/build` runs from the main VS Code and main working tree as they are. Each run operates in a dedicated worktree `<repository>-run-<run-id>` (integration branch `run/<run-id>`), and you do not need to open another VS Code. Completed runs are merged into main with `run-state.py land` in the order they finish (one at a time under a shared lock). The merge performs the merge and verify in a temporary git worktree before advancing main, so it works even if the main working tree has uncommitted changes or is on a different branch (only when uncommitted changes overlap the same files as the incoming changes does it wait with `LAND-WAIT` until resolved). When it conflicts with a run that was merged earlier, it re-merges the base into the run's worktree and retries (`tests/system/ledger.json` is merged automatically per case id), and stops with `LAND-CONFLICT` only when there are files it cannot resolve.

For a run whose automatic merge succeeded, the integration branch and worktree are cleaned up.

For a run whose result is "all complete" and whose final verify passed, the conductor merges the integration branch `run/<run-id>` into the local main with `--no-ff` and deletes the integration branch (it does not push to main). If the merge conflicts or verify fails, and for runs that are "has blocked items," "stopped by time budget," or "stopped by canary failure," the branch is left without being merged. In those cases, and for VS Code's New Worktree or a new working tree in the GitHub Copilot app (that session's branch), merge manually as follows.

```bash
git switch main
git merge --no-ff run/202610080900          # Merge locally
# or
git push origin run/202610080900 && gh pr create --base main --head run/202610080900   # Merge via PR (CI's ebak-verify re-verifies)
```

If you specified `git_push: 作業ブランチへ push する`, the conductor pushes the integration branch before merging (as a backup; no PR is created).

For a run executed in a new working tree in the GitHub Copilot app, the session's branch is the integration branch (`integration:` in `run-state.py status`). The conductor does not merge into main, so either create a PR with the app's pull-request creation feature, or merge by replacing `run/<run-id>` in the commands above with the session's branch name. Do not archive or delete the session until merging is done (the worktree and the `/work` report may disappear).

If you want to check before the automatic merge, note that you cannot view `git diff main...<integration branch>` before it is merged; revert afterward with `git revert -m 1 <merge commit>`.

When merging manually, first confirm at least the following 3 points.

1. The result and "Blanket-approved items" in `run-report.md`
2. `git diff main...<integration branch> -- docs/requirements-definition.md` (changes to requirements)
3. `python scripts/verify.py --strict` passes

## 2.5 The next request

You can send answers and new requests together in a single Prompt.

```text
<request>
(New request. Leave empty if none)
</request>
<answers>
Q-003: B
残りはすべて推奨どおり
</answers>
```

## 2.5b Merging similar items (/dedupe)

When duplicates have accumulated among requirements, acceptance criteria, System Test cases, and catalog rows, you can merge them on their own with `/dedupe` (the Agent is conductor; to narrow the scope, write it afterward). Candidates can be checked with `python scripts/rdcheck.py similar --pairs` (`--kind FR|AC|CASE|CAT`). rd-author changes the requirement to keep and retires the other, test-designer merges and disables the corresponding cases via `ledger.py`, and the work is fixed until `verify.py --docs-only` returns exit 0. No new features are implemented.

## 2.6 Cleaning up /work

Cleanup is permitted by evidence of normal completion, not by a retention period. Only runs whose result is "all complete," for which the completion conditions, final verify, target tests, integration into main, and post-integration verify on main succeeded in order, and whose pre-cleanup `run-report.md` is finalized, are cleaned up. Everything else (blocked, aborted, failed, unmet, missing report) is kept with no automatic expiry so that it can be resumed.

The pre-cleanup report contains the integration commit on main, the structured results of each gate, the cleanup candidates, and the assets that are protected or kept along with the reasons. After cleanup, only the per-candidate deletion, retention, and failure results and the run's final state are appended. If it fails midway, further deletion stops and it exits non-zero, and only the remaining candidates are re-inspected so that it can be safely retried.

```bash
python scripts/clean-work.py --dry-run   # Check candidates, protection reasons, and planned actions (no changes)
```

A run-dedicated worktree that has the integration branch `run/<run-id>` checked out (other than the main working tree; e.g., `<repo>-run-<run-id>`) is also deleted automatically at the end if it has no uncommitted changes (the integration branch is detached first, then deleted). Because `work/` exists per worktree, `work/runs/<run-id>` is moved to the main `work/runs/<run-id>` before deletion, and the per-candidate results are appended to the main side's `run-report.md`. If there are uncommitted changes, the worktree and integration branch are kept.
