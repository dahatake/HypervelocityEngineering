[日本語](05-scripts-reference.md) | **English**

# 5. Scripts Reference

All scripts run on the Python 3.9+ standard library only. They can be run from anywhere in the repository and operate relative to the git root. Detailed usage can be displayed with `--help`. Output is short and in a form an LLM can read as is (one finding per line, with a one-line summary at the end).

## verify (L1 deterministic checks)

```bash
python scripts/verify.py                  # Checks of managed data (CHK-01 to 28. CHK-28 is the external integration catalog; it reports nothing when there is none) + verify.commands
python scripts/verify.py --docs-only      # Managed data checks only (gate for rd-author and test-designer)
python scripts/verify.py --quick          # Skip commands with "slow": true (gate for implementer)
python scripts/verify.py --run current    # Also check consistency with the running run's queue.json (CHK-21)
python scripts/verify.py --strict         # For the final stage and integration. Treats important warnings as errors
python scripts/verify.py --strict-ledger  # Treat missing correspondence between system ACs and the ledger (CHK-10/11) as errors (automatic from stage 4 onward)
python scripts/verify.py --show-warnings  # Also show warnings
python scripts/verify.py --no-cache       # Always run without using the cache
./scripts/verify.sh   /  .\scripts\verify.ps1   # Same thing (wrappers that find Python and call verify.py)
```

Exit 0 means pass. Full logs are saved in `/work`.

**Cache:** A PASS when the working tree is clean (no uncommitted changes and no untracked files) is recorded in `/work/.ebak/verify-cache.json`. The key is HEAD, the arguments, `scripts/ebak.config.json`, and the run state (stage; queue.json when `--run` is used). Running the same verify on the same commit immediately returns `PASS (cached …)` from the cache. For example, the verify that hook G-4 runs right after the implementer's gate is such a case. FAIL is not recorded. To disable it, use `--no-cache` or the environment variable `EBAK_VERIFY_NO_CACHE=1`.

## rdcheck.py (parser for the requirements definition)

```bash
python scripts/rdcheck.py check [--base REF|none] [--run RUN_ID|current] [--strict] [--json]
python scripts/rdcheck.py show FR-012 AC-031 Q-007     # Show only the sections of the specified requirements, ACs, and questions (no need to read the whole text)
python scripts/rdcheck.py list --state 承認済み --priority MUST
python scripts/rdcheck.py list --level system          # ACs that are targets of System Test
python scripts/rdcheck.py list --area 受付              # Filter by area (--by-area groups by area. Deprecated items are not counted)
python scripts/rdcheck.py index FR-012 [--kind 検証] [--json]   # Relationships with kinds (upstream, source, reference, implementation, verification, usage). Generated each time, not saved. Passing an ID gives a reverse lookup
python scripts/rdcheck.py stats                        # Audit metrics (JSON. similar_pairs = pairs of similar requirements/ACs, ledger_shared_acs = duplicate cases for the same AC)
python scripts/rdcheck.py similar "入力を中断して再開できる"   # Before creating something new, show similar existing requirements/ACs in descending order of similarity (--kind FR|AC|CASE|CAT, --top N, --min 0.2)
python scripts/rdcheck.py similar FR-012               # Items similar to an existing item
python scripts/rdcheck.py similar --pairs [--min 0.35] [--kind CASE] [--json] # Pairs of similar requirements, ACs, System Test cases, and catalog rows (merge candidates; ACs within the same requirement and cases tied to the same requirement are excluded). Merging is done with `/dedupe`
python scripts/rdcheck.py digest AC-031                # Digest of an AC
python scripts/rdcheck.py trace FR-012 [--json]        # Trace a requirement upstream (G, sources), sideways (terms, states, PARAM), and downstream (ACs, ledger cases, catalog, code)
python scripts/rdcheck.py trace G-002 申請 PARAM-004 下書き保存   # Trace related requirements in reverse from goals, entities, PARAM, and common components (impact analysis)
python scripts/rdcheck.py trace INT-001                # List requirements and acceptance criteria that reference an external integration
```

The default of `--base` is the merge-base with main. It is used for diff checks (CHK-12/13).

## rdfix.py (automatic repair of data layer inconsistencies)

```bash
python scripts/rdfix.py                           # Show the repair plan (no writes). Exit 1 if anything can be fixed
python scripts/rdfix.py --apply                   # Write the repairs and verify with rdcheck
python scripts/rdfix.py --only catalog,ledger     # Narrow the targets: registry, catalog, ledger, gitignore, history
python scripts/rdfix.py --adopt --apply           # Also adopt IDs that are not in the ID registry (when you have confirmed they are not hand-assigned IDs)
python scripts/rdfix.py --json
python scripts/ledger.py repair [--apply]         # Only the ledger part (used internally by rdfix)
```

With the requirements definition as the source of truth, it aligns the catalog, the ID registry, the System Test ledger, the run history, and `.gitignore` to it. It does not change the requirements definition. The output consists of `FIX <CHK> <location> <description>` (fixed automatically) and `MANUAL <CHK> <location> <description>（担当: <role>）` (needs judgment; 担当 = owner) lines, followed by one final line `rdfix: fix=N manual=M mode=…`. Exit 0 means "nothing remains to be fixed automatically". The scope of repairs is in [6.3](06-quality-gates.en.md#63-automatic-repair-of-data-layer-inconsistencies-rdfix).

To perform the data layer check (the same rdcheck as `verify.py --docs-only`) and the repair together, add `--full`.

```bash
python scripts/rdfix.py --full                    # Check only (no writes, does not wait for the lock)
python scripts/rdfix.py --full --apply            # Check → automatic repair → re-check (up to 3 times until it converges = PARAM-026)
python scripts/rdfix.py --full --apply --json     # The same result as JSON (manual items have the fields chk, file, line, owner, action)
```

Exit codes: 0 = passed or repaired; 1 = manual action remains, a repair plan exists, or it does not converge; 2 = not executed or canceled (a worker's branch, lock wait timeout, cancellation, or an unexpected error). `MANUAL` lines carry the check item ID, `file:line`, the owner role, and the next action. Apply runs only one at a time in the same repository (`work/.ebak/rdfix.lock`; an apply started later waits up to 30 seconds = PARAM-027, changeable with `--lock-wait`), and writes are done by replacing temporary files. When the requirements definition or the external integration catalog changes, when a write fails, when an error that did not exist before the repair appears, or on an unexpected error, all changes are rolled back to the pre-repair contents and it ends with exit 2.

There are three entry points, and each calls the same `rdfix.py --full [--apply]`. (1) The GitHub Actions `ebak-data-layer.yml` (`--full --apply` on failure). (2) The installer `tools/install.py` (by default runs `--full --apply` once after installation or update; `--no-repair` runs only `--full` with no writes; `--skip-verify` performs neither check nor repair; `--dry-run`, `--check`, `--uninstall`, and `--purge` do not repair. Even if a repair is canceled or manual action remains, the toolkit stays installed, and the exit code does not change with the data layer result). (3) Manual execution by the user or conductor. `--apply` on a worker's branch (`work/<run-id>/<item>`) does not write and exits with 2. At every entry point the requirements definition and the external integration catalog are not changed and repairs are not committed (only Actions commits a repair that passed).

## entities.py (consistency between the entity ledger and the enterprise data catalog)

```bash
python scripts/entities.py list  [--repo DIR] [--json]          # Entity ledger (name, description, managed table, use cases, usage, columns), relationships, clusters, and DDL/schema supplements (FR-1025/1026/1030)
python scripts/entities.py check [--repo DIR] [--json] [--strict] # Cross-check with the enterprise data catalog (match / EABK only / enterprise catalog only / name variant candidates)
python scripts/entities.py todo  [--repo DIR] [--json]          # ToDos for uncovered entities (in the row format of the question list)
```

The ledger is derived from the glossary, the state table, and each requirement's "target entities" (no dedicated file or table is created). Entities whose description, managed table, or usage is absent from the managed data are shown as "description not written", "table not written", and "usage not written", and nothing is guessed. The reference source of the enterprise data catalog is optionally specified with `enterprise_data_catalog` in `scripts/ebak.config.json` ([Chapter 4](04-customization.en.md)). It works even when unset and reports "Enterprise data catalog: not set (not cross-checked)". The reference source is read-only; its body is neither stored nor copied (only names and `source:line` are output), URLs are limited to http and https, and a URL with embedded credentials is not fetched and is reported as "cannot be verified". `todo` only outputs question-list rows (IDs not yet assigned) and does not change the managed data. rd-author assigns IDs with `next-id.py` and copies them into the question list. The reasons are "enterprise catalog not verified", "not in the enterprise catalog", and "name to be confirmed"; nothing is output if the question list already has an unanswered question for the same entity and the same reason. Exit 0 (`check --strict` exits 1 on differences or when verification is impossible).

## next-id.py (ID assignment. G-3)

```bash
python scripts/next-id.py FR                    # FR-013
python scripts/next-id.py NFR-SEC               # NFR-SEC-004
python scripts/next-id.py AC --count 3          # AC-041 AC-042 AC-043
python scripts/next-id.py Q | PARAM | G | SRC | E2E | IT
python scripts/next-id.py INT                   # INT-001 (ID of the external integration catalog docs/integrations.md)
python scripts/next-id.py INT                   # INT-001 (ID of the external integration catalog docs/integrations.md. [Chapter 11](11-integration-catalog.en.md))
python scripts/next-id.py --peek FR             # Show the next ID without assigning it
python scripts/next-id.py --sync                # Align the ID registry state with the body (in use, deprecated, deleted)
python scripts/next-id.py --sync --adopt        # Adopt existing IDs that are not in the registry (right after installation)
python scripts/next-id.py --sync --finalize     # Mark assigned IDs that were not used as missing numbers (stage 6)
```

The next number is determined by max(requirements definition, ID registry, the same file on main, System Test ledger, the numbering record shared across worktrees) + 1.

## ledger.py (System Test ledger. G-2)

```bash
python scripts/ledger.py summary [-v]
python scripts/ledger.py --by test-designer add --req FR-012 --ac AC-031 --title "…" --layer e2e --command "…" [--canary]
python scripts/ledger.py --by test-designer update E2E-001 --command "…" --reason "…"   # A reason is required
python scripts/ledger.py --by test-designer block E2E-001 --reason "…"                 # Use instead of deleting
python scripts/ledger.py set E2E-001 blocked --reason "…"
python scripts/ledger.py digests [--update]
python scripts/ledger.py repair [--apply]          # Fix the ledger to match the requirements definition (used from rdfix.py)
python scripts/ledger.py preflight [--cases ID,..] [--all]   # Check pytest with collect-only (0 collected means a syntax/import/-k/node id error). Must exit 0 before test-designer finishes and before stage 4 completes
python scripts/ledger.py --by conductor run --select changed|failed|all [--canary-first] [--stop-on-canary-fail] [--max-minutes N]
python scripts/ledger.py run --cases E2E-001,IT-002 --no-record   # In a worker's worktree, only run without updating the ledger
```

The output of `run` is in the report format defined by the original Prompt (`<id> <requirement_ids> <pass|fail> <seconds> <evidence>` and `結果: …` (result)). Details of the results are in `work/runs/<run-id>/results.json`.

## select-tests.py (test selection by impact scope)

```bash
python scripts/select-tests.py [--base REF] [--req FR-012] [--json]
```

From the requirement IDs and AC IDs written in the changed files and the IDs specified with `--req`, it selects the System Test cases (`CASE`) and the unit/integration test files (`TEST`) that should be run. The canary and cases that are not_run or fail are always included.

## next-impl.py and build-request.py (next implementation candidates, and a /build request built from time alone)

```bash
python scripts/next-impl.py [--json]        # Ranked table of requirements to implement next, list of exclusions, and list of IDs for scope (read-only)
python scripts/build-request.py 60分        # 60分 / 24時間 / 90m / 1.5h → outputs a request that can be pasted into /build
```

`next-impl.py` orders requirements that are approved and either not started or registered for implementation (tests not registered or not passing) by: dependencies first, then priority (MUST, SHOULD, MAY), the number of other candidates that depend on it, those registered for implementation first, and then requirement ID. Excluded requirements are shown with the reason (not approved, BLOCKED, dependency incomplete, completed, running). A dependency is another requirement ID written under "related existing assets". `build-request.py` divides the allowed time by 60 minutes per requirement (PARAM-012) to get a count (minimum 1), puts that many requirements from the top into `scope`, and outputs `<request>`, `<answers>`, `<references>`, and `<run_options>` with the allowed time in `max_hours`. It only generates; it does not start a run. When there are no candidates, it outputs no request and shows the reasons for exclusion.

## summarize.py (log summary)

```bash
python scripts/summarize.py work/runs/<run-id>/logs/verify-…-unit.log [--max-lines 15]
npm test 2>&1 | python scripts/summarize.py -
```

It outputs only the test runner's summary line, the first few (non-duplicate) error lines, and the last few lines.

## run-state.py (conductor state management)

```bash
python scripts/run-state.py start --options "max_hours: 2.5\ngit_push: しない"   # RESUME if a run is in progress (しない = do not)
python scripts/run-state.py status
python scripts/run-state.py stage 4 [--done]
python scripts/run-state.py progress "工程 2: 直接矛盾 0。Q-012 を BLOCKED"   # (Stage 2: 0 direct contradictions. Q-012 set to BLOCKED)
python scripts/run-state.py queue add --id I-01 --req FR-012,FR-013 --ac AC-031 --boundary 申請 --shared 下書き保存 --depends I-00   # 1 to 5 requirement IDs
python scripts/run-state.py queue ready --parallel 5
python scripts/run-state.py queue set I-01 --status doing --branch work/<run-id>/I-01 --attempts +1   # Normally done by integrate.py
python scripts/run-state.py time                  # Exit 3 when more than 85% of the time budget is used
python scripts/run-state.py complete-check        # Judge the completion conditions
python scripts/run-state.py lane decide --changed 2 [--flags security,conflict,shared,unresolved,goal_unmapped]   # Decide fast / full (fast skips independent audit, reviewer, and the full majority vote)
python scripts/run-state.py lane confirm   # Re-decide by the queue count after planning (never goes back from full to fast)
python scripts/run-state.py human answers --note "Q-003: B"   # Record the user's Prompt as one occurrence (answers / resume / instruction)
python scripts/run-state.py finish --result "全件完了" --credits "…"   # Append one line to docs/run-history.md (全件完了 = all items completed)
python scripts/run-state.py land [--wait 1800]    # Merge a fully completed run into main (one at a time under a common lock. 0 merged, 1 verify failed (rolled back), 2 conflict, 3 the main working tree is not on main or has uncommitted changes)
```

`start` records the first request of a new run as `request`. `human` is run by the conductor only once when a run is resumed with a user's Prompt. The recorded count becomes "human interventions" in the KPI.

`queue set --status` records the time an item became doing, the time it spent in doing (`work_sec`), and the time it finished; `stage` records the start and completion time of each stage (used for the flow metrics of kpi.py).

## integrate.py (worktree pool and integration. The implementation loop)

```bash
python scripts/integrate.py prepare I-01                       # Assign a worktree from the pool, create work/<run-id>/I-01, and set it to doing
python scripts/integrate.py merge I-01 --summary "…"           # Integrate: merge → verify --quick → System Test → commit the ledger → release → done
python scripts/integrate.py merge I-01 --full                  # Also run verify's slow commands (automatically every 5 items)
python scripts/integrate.py abandon I-01 [--blocked] [--reason "…"]   # Return to todo (or blocked) and release the worktree
python scripts/integrate.py pool [--prune]                     # List the pool. --prune deletes worktrees that are not in use (stage 6)
```

- Worktrees are reused during a run as a pool at `work/worktrees/<run-id>-w<N>`. Ignored build artifacts (node_modules, bin/obj, .venv, and so on) remain, so the second and later builds are incremental. `prepare` uses the branch from the previous attempt, if there is one, and hands it over after merging in the integration branch.
- `merge` performs the entire serial integration in a single call on top of the integration branch and outputs only a few lines. System Test runs only the cases related to the diff since the commit just before the merge, plus the canary. Cases for requirements that have not been integrated yet are excluded because they are known not to pass.
- On a conflict (exit 2) or a failure of verify or System Test (exit 1), the integration is rolled back (`git reset --hard`) and the item returns to todo. The integration branch is always kept green.
- Integration is limited to one at a time by a lock (`work/.ebak/integrate.lock`).

## kpi.py (KPI aggregation)

```bash
python scripts/kpi.py run                          # Show the KPI of the running run (or the latest if none) in Markdown
python scripts/kpi.py run --run 202610080900 --format json
python scripts/kpi.py run --format html --out work/runs/<run-id>/kpi.html
python scripts/kpi.py history                      # Aggregate the whole of docs/run-history.md
```

The North Star is "verified requirements per human intervention". A **verified requirement** is an implemented requirement that is approved, has a catalog row, has no BLOCKED AC, and all of whose system ACs are `pass` in the ledger. For requirements that did not become verified, the reason (such as "no catalog row") is shown. The metrics and targets are in [8.2 of 08-roadmap.en.md](08-roadmap.en.md#82-kpis).

As flow (speed) metrics, it also outputs the time per stage, the effective parallelism of the implementation loop (total working time of the items ÷ elapsed time of the loop), the working time per item, the serial time of integration and its share, and the models actually used (`work/runs/<run-id>/models.jsonl`, recorded by hooks). For a slow run, use this table first to separate whether parallelism is low (workers waiting) or the serial integration time is long (verify and System Test are heavy).

## import-speckit.py (import from GitHub Spec Kit)

```bash
python scripts/import-speckit.py [--source DIR] [--feature 001] [--implement] [--no-constitution] [--out F | --stdout | --json]
```

It reads `specs/*/spec.md` and `.specify/memory/constitution.md` and writes a mapping table and the `/build` request text to `work/import/speckit-<datetime>.md`. It does not edit the requirements definition and assigns no IDs. Usage is in [1.7](01-writing-requests.en.md#17-importing-github-spec-kit-specifications).

## adopt.py (adopting an existing app)

```text
python scripts/adopt.py scan [--since-days 365]                  # Inventory → docs/baseline/inventory.{json,md}
python scripts/adopt.py request [--clusters 6] [--implement]      # /build request text → work/import/
python scripts/adopt.py anchor SRC-003 src/a.py:10-48           # Pin the evidence of a source → docs/baseline/evidence.json
python scripts/adopt.py check [--strict] [--json]               # Check DRIFT, recovery rate, and reverse-generated requirements (exit 1 = error)
python scripts/adopt.py golden add NAME -- CMD ARG...           # Characterization test (golden master)
python scripts/adopt.py golden record|check|list [NAME] [--update]
```n
For details and rationale, see [10. Adopting an existing app](10-adopting-existing-apps.en.md). It does not edit the requirements definition and assigns no IDs.

## clean-work.py (cleanup of /work)

```bash
python scripts/clean-work.py [--days 14] [--dry-run]
```

Only when a fully completed run has been merged into main and both the post-merge verify and the finalization of the pre-cleanup run-report have succeeded, it cleans up the run-owned pool worktrees, working branches, the integration branch, temporary assets, and the run-dedicated worktree that has the integration branch checked out (`run-worktree`; kept if it has uncommitted changes; `work/runs/<id>` is moved to the main working tree). `--dry-run` shows candidates, the reasons for protection, and the planned operations. `--days` is accepted for compatibility, but failed, aborted, and unfinished runs are kept with no automatic expiry. Immediately before deletion, it re-checks the run record, Git registration, the normalized real path, and the dirty/lock/protection state. On partial failure, diagnostics are left in the report and it exits non-zero; on re-run, already deleted items are treated as succeeded and only the remaining candidates are handled.

## watch.py (run monitoring: leftover processes and items over time)

```bash
python scripts/watch.py scan
python scripts/watch.py reap [--under PATH]
python scripts/watch.py stuck [--item-minutes N]
```

- `scan`: only displays processes suspected to be leftovers (node, browsers, and so on) as `SUSPECT pid=… 理由=孤児|古い` (理由 = reason; 孤児 = orphan, 古い = old), and terminates nothing. If there are none, it prints "疑わしいプロセス: なし" (suspicious processes: none).
- `reap`: among suspicious processes, terminates those that contain the repository path and were started more than 10 minutes ago and either have no parent (orphan) or are older than 120 minutes (`KILL`, `FAIL`, and `KEEP` for those protected and left). `reap --under PATH` narrows to those whose command line contains PATH. If PATH is empty or the filesystem root, nothing is terminated and it exits with 2.
- `stuck`: shows items in the current run's queue that have been `doing` for more than `--item-minutes` (default 60) minutes as `STUCK <item> <elapsed minutes>`. If there is no current run, it prints nothing and exits 0.

Exit codes: 0 = normal (`scan` and `reap` always return 0, except that `reap` rejecting its arguments returns 2), 1 = `stuck` found items over the limit, 2 = rejection due to arguments or safety. The conductor runs `stuck` and `reap` before and after filling the slots.

## hooks/gate.py (the hook body)

Users do not run it directly. It is called from `.github/hooks/quality-gates.json` on the events `session-start`, `user-prompt`, `pre-tool`, `subagent-start`, `subagent-stop`, and `agent-stop`. A record of the decisions is in `work/.ebak/gate.log`.

## EABK-Studio (data layer viewer)

When installed, it is placed in `EABK-Studio/` of the target repository. It is a local web app that lets you view the data layer (requirements definition, catalog, ledger) as 2D/3D diagrams, tables, and search (Japanese and English).

```text
python EABK-Studio/studio.py [--repo DIR] [--port 8765] [--no-open] [--role pm|architect|swe] [--check]
```

| Option | Behavior |
|---|---|
| `--repo DIR` | Target repository (default: current directory. Searches up through parents for the data layer) |
| `--port N` | Listening port (default 8765. If in use, tries the next numbers, up to 20) |
| `--no-open` | Do not open the browser automatically |
| `--role pm\|architect\|swe` | The screen to open first (dashboard / 2D map / table) |
| `--check` | Show whether the managed data files exist, the number of items parsed (requirements, acceptance criteria, catalog rows, ledger cases, run history), and warnings, then exit. Exit 0 if the data layer exists, exit 1 if not. The server is not started |

- If you specify a `--repo` that has no data layer, it shows guidance without starting the server and exits with 1.
- Wrappers: `EABK-Studio/start.ps1 [-Repo DIR] [-Port N] [-Role …] [-Check] [-NoOpen]`, `EABK-Studio/start.sh [DIR] [PORT] [studio.py options…]`.
- It does not read source code and listens only on 127.0.0.1. It is read-only; the only things it writes are the title and decision state of `docs/catalog.md` that you confirmed and executed in "consistency maintenance".
- Role-based guides (Product Manager, Architect, Software Engineer) and the list of data that each screen reads are in [studio/README.en.md](studio/README.en.md). For details, see `EABK-Studio/README.md`.
