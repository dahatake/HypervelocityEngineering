[日本語](02-daily-workflow.md) | **English**

# 2. Daily Workflow

In EABK Lite, every change goes through the following five steps. All of them use only the usual Copilot, git and CI.

```text
1. Ask                     ask the usual Copilot (the default agent) in chat (chapter 1)
2. Update in one change    Copilot fixes the requirements definition, catalog, tests and code in the same change
3. Check locally           python scripts/verify.py exits 0
4. Push / PR               CI ebak-verify and ebak-data-layer run the same checks
5. Audit at milestones     before a release etc., rd-auditor audits the meaning of the requirements
(any time)                 view the status in EABK Studio
```

> Migrating from 0.5.x: runs, stages, integration branches, `run-report.md` and the automatic merge into main no longer exist. Changes are merged through ordinary branches and PRs. Worktrees and `work/*` branches left by 0.5.x runs are not removed automatically; check them with `git worktree list` and `git branch --list "work/*"` and delete them by hand ([9. Versioning](09-versioning.en.md)).

## 2.1 Ask

Create a branch and ask in chat. How to write the request is in [1. Writing Requests](01-writing-requests.en.md).

```bash
git switch -c feature/draft-save
```

## 2.2 Check that everything was updated in the same change

After reading Copilot's report, check in the diff that the management data is part of the same change.

```bash
git status --short
git diff -- docs/requirements-definition.md   # requirements, ACs, decision log, question list
git diff -- docs/catalog.md docs/id-registry.md tests/system/ledger.json
```

| Kind of change | What must be in the same change |
|---|---|
| Add a feature | New requirement and ACs (IDs from `next-id.py`), ID registry rows, catalog rows, tests that name the requirement and AC IDs, ledger cases if needed |
| Change a feature | The changed requirement / AC text, affected tests, updated ledger cases (with `--reason`) |
| Remove a feature | Requirement set to "廃止" (retired); code, tests and catalog rows deleted; ledger cases stopped (`ledger.py block --reason`) |
| Change without behavior change (refactoring, wording) | Only the catalog rows of renamed or deleted files |

If something is missing, ask in the same chat, e.g. "FR-031 has no catalog row. Fix it according to the rules in AGENTS.md". Approvals and answers to the question list are also given in this chat ([1.3](01-writing-requests.en.md#13-approvals-happen-in-chat)).

## 2.3 Check locally

```bash
python scripts/verify.py          # management-data checks + verify.commands (build / tests)
```

Exit 0 means pass. Copilot normally runs it before finishing, but run it yourself before pushing. If it fails, fix it in this order.

| Output | Action |
|---|---|
| `ERROR CHK-07`, `CHK-08`, `CHK-17` etc. (inconsistencies in catalog, ledger or ID registry) | Fix automatically with `python scripts/rdfix.py --apply` (the requirements definition is never changed). Fix remaining `MANUAL` lines according to their "担当" (area in charge) and "次の行動" (next action) |
| `ERROR CHK-01` (duplicated ID, ID missing from the registry) | Re-allocate following [2.7](#27-several-people-and-several-pcs) |
| `ERROR CHK-12` (AC text changed but the ledger digest is old) | After confirming the tests verify the new AC, run `python scripts/ledger.py digests --update` |
| A build or test command failed | Full logs are in `/work`. `python scripts/summarize.py <log>` shows only the key lines |

The default check profile is `lite`, which reports only the structure and traceability checks (`CHK-01, 02, 03, 05, 09, 12, 17, 19, 24`). To see writing-style warnings too (vague words, hard-coded numbers, forbidden synonyms), use `full`.

```bash
python scripts/verify.py --docs-only --profile full --show-warnings
```

The list of checks is in [6. Quality Gates and Checks](06-quality-gates.en.md); the options are in [5. Scripts Reference](05-scripts-reference.en.md).

## 2.4 Push and PR (CI)

```bash
git add -A && git commit -m "FR-031 draft saving"
git push -u origin feature/draft-save
gh pr create --base main
```

Two workflows run on push and PR.

| Workflow | When | What it does |
|---|---|---|
| `ebak-verify` (`.github/workflows/ebak-verify.yml`) | push, PR | Runs `scripts/verify.sh --show-warnings`, the same checks as a local `verify.py` |
| `ebak-data-layer` (`.github/workflows/ebak-data-layer.yml`) | PR, push, manual, weekly | Checks the data layer and, if it fails, repairs it with `rdfix.py --full --apply`. When the repair passes, it commits the fix (to the PR branch for same-repository PRs; on push, to a fix branch with a PR). What cannot be fixed automatically becomes an Issue. The requirements definition is never changed |

Before merging, confirm at least the following.

1. `ebak-verify` and `ebak-data-layer` succeeded
2. The requirement changes in `git diff main...HEAD -- docs/requirements-definition.md` match the intent of the request
3. No requirement still "AI提案／承認待ち" (awaiting approval) was implemented (requirements listed by `python scripts/rdcheck.py list --state 承認待ち` have no matching code)

To stop `ebak-data-layer`, delete the workflow file or disable it on the GitHub Actions page ([4. Customization](04-customization.en.md)).

## 2.5 Audit at milestones (rd-auditor)

Deterministic checks (verify, CI) run on every change, but *semantic* contradictions between requirements and drift from the goals (G-IDs) are hard to find mechanically, so ask an independent auditor at milestones: before a release, before merging a large change, or after many requirements were added.

Select **rd-auditor** as the agent and ask in chat.

| How to ask | Scope |
|---|---|
| "Audit the diff" | Requirements changed against `base_branch` (default `main`) plus requirements sharing the same entities, states, PARAMs or terms. One pass by default |
| "Audit everything with 3 passes" | The whole requirements definition. The same judgment is made 3 times independently; a majority vote sets the confidence |
| "Audit FR-012 and FR-031" | The named requirements |

rd-auditor never changes files tracked by git. Results are written to `work/audit/<YYYYMMDD-HHMM>/` as one output per pass (`run<n>.md`) and the tally (`report.md`); the chat only gets a summary of the counts. Where subagents are available, the passes run in parallel.

You decide what to do with the findings. To fix them, ask the default agent in a separate request and change (e.g. "Fix the 2 high-confidence findings in work/audit/20261108-1000/report.md").

## 2.6 View the status (EABK Studio)

EABK Studio shows the requirements, acceptance criteria, catalog and System Test ledger as diagrams and tables. It is optional; work proceeds without it.

```bash
python EABK-Studio/studio.py          # opens a browser (listens on 127.0.0.1 only, read-only)
python EABK-Studio/studio.py --check  # print the counts it can read, then exit
```

How to use each screen is in the [EABK Studio guide](studio/README.en.md).

## 2.7 Several people and several PCs

The rules live in the repository (`AGENTS.md`), ID allocation in `next-id.py`, and the checks in CI. So whoever asks, on whatever PC and with whatever Copilot, the same rules and checks apply, independent of personal prompts or memory.

| Mechanism | Effect |
|---|---|
| `next-id.py` | Allocates the next number after the maximum found in the requirements definition, the ID registry, the same files on `base_branch` and the ledger. Other working trees of the same clone on the same PC share the allocation log |
| `docs/id-registry.md merge=union` in `.gitattributes` | Rows appended to the ID registry on different branches are both kept on merge, without conflicts |
| CI `ebak-verify` | Even if someone forgets to check locally, the PR runs the same checks |

When two PCs or branches allocate at the same time, the same ID can end up on two requirements. After the merge (or after taking in main), `verify.py` detects it as `ERROR CHK-01`; the side that merges later fixes it as follows.

1. On your branch (`git switch <your branch>`), take in main and confirm the duplicated ID with `python scripts/verify.py --docs-only`
2. Allocate a new ID with `python scripts/next-id.py FR` (use the kind that collided)
3. Replace the ID on your side in the requirement, ACs, test names and comments, and catalog rows. Fix ledger cases with `python scripts/ledger.py update <case ID> --req <new ID> --reason "re-allocated duplicated ID"`
4. Align the ID registry with `python scripts/next-id.py --sync`, then bring `python scripts/verify.py` to exit 0

You can also ask Copilot: "Fix the CHK-01 duplicate by re-allocating the ID on my branch with next-id.py".

## 2.8 About /work

`/work` is a working area not tracked by git (logs, check results, audit results in `work/audit/`, request drafts from `adopt.py` in `work/import/`, and so on). It is not deleted automatically. You may delete what you no longer need by hand.
