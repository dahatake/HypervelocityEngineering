[日本語](06-quality-gates.md) | **English**

# 6. Quality Gates and Checks

There are two layers of quality gates. Hooks enforce the rules before tool execution and before exit, and verify checks the same rules deterministically ([the "Two-layer quality gates" section of the README](../README.en.md#two-layer-quality-gates)).

## 6.1 Hook gates

`.github/hooks/quality-gates.json` (in the Copilot CLI format; it is also loaded by the Copilot harness in VS Code and by the GitHub Copilot app, which is built on top of Copilot CLI) calls `scripts/hooks/gate.py`. When the local sandbox is enabled in the GitHub Copilot app, hooks also run inside the sandbox, with the same permissions as the agent's shell.

| Gate | Target | Behavior |
|---|---|---|
| **G-1** Limit the requirements writer to one | Everyone other than rd-author | While a run is in progress, rejects edits to `docs/requirements*`. Edits from a worker's worktree are always rejected |
| **G-2** No changes to System Test | implementer, reviewer, worker worktrees | Rejects edits and deletions of `tests/system/**`, and operations of `ledger.py` that update the ledger. Direct edits to the ledger `ledger.json` are rejected for everyone (use `ledger.py`) |
| **G-3** ID numbering | All agents | Rejects direct edits to `docs/id-registry.md` (use `next-id.py`). IDs assigned by hand are detected by CHK-01 |
| **G-4** Verification before exit | implementer, test-designer, rd-author | Runs verify before a worker exits, and sends the worker back if it fails (up to 3 times). For the implementer, the check runs in the worktree given by `WORKTREE:` in its result |
| **G-5** Reject dangerous operations | All agents | Rejects push to main, force push, history rewriting, direct commits to main during a run, deployment while `deploy: no` is in effect, push while `git_push: no` is in effect, writes outside the working directory, changes to hooks during a run, and renaming the branch during a run (`rename_branch` in the GitHub Copilot app). It also enforces the write scope for each role (conductor: `work/` and run-history; rd-author: `docs/`; test-designer: `tests/system/`; rd-auditor and reviewer: read-only). Changes to external systems through tools from MCP servers, plugins, or extensions configured by the user (tools whose names include `create`, `update`, `delete`, `send`, and so on) are allowed during a run only when `external_write: yes`; deployment and publishing (`deploy`, `publish`, and so on) are allowed only when `deploy: yes`. External changes by rd-auditor and reviewer are always rejected ([4.4](04-customization.en.md#44-using-mcp-servers-plugins-and-extensions)) |
| **G-6** Location of temporary files | All agents | Rejects writing logs, evidence, and run results (`*.log`, `*.har`, `*.trace`, `trace*.zip`, `results*.json`, `evidence/`, `screenshots/`, `test-results/`, `playwright-report/`) anywhere other than `/work`. Deleting `/work` is allowed only for `clean-work.py` and `git worktree remove` |
| Completion check | conductor | Sends the conductor back at turn end until the completion conditions are met (no todo or doing items in the queue, stage 6 complete, run-report.md exists) (up to 40 times; it does not send it back once 125% of the time budget is exceeded) |
| Resume guidance | All agents | At session start, if a run is in progress, shows the run-id and the resume procedure |
| `/build template` | All agents | In a turn whose prompt is only `/build template`, rejects tools other than reading and skills (commands, writes, and worker invocations), and does not send the turn back at its end even if a run is in progress. This prevents showing the template from turning into starting or resuming a run (it is determined by the `userPromptSubmitted` event and recorded per session in `work/.ebak/template-request-<session>.json`; it is not cleared by another session's prompt. Input without a session identifier does not clear other sessions' records) |

### 6.1.1 Separate sessions when a run is placed in the primary tree (FR-1076)

When a run is placed in the primary working tree with `require_worktree: false`, `--allow-primary`, or `EABK_ALLOW_PRIMARY=1`, chats that do not own the run also work in the same tree. Only when the `session_id` in `meta.json` differs from the caller's session (and the call carries a session identifier) does the hook **lift the run-dependent gates**. The owner's chat, runs with no owner, and calls without a session identifier are subject to all gates as before.

| Gate | Treatment for a separate session | Reason |
|---|---|---|
| G-5 conductor's edit scope (rejecting edits other than `work/` and run-history) | **Lifted** | A rule for the run's owner |
| G-5 ban on changing hooks during a run (`.github/hooks/`, `scripts/hooks/`) | **Lifted** | Protects the run in progress |
| G-5 ban on direct commits and merges to main during a run | **Lifted** | Protects the run's integration branch |
| G-5 rejections that depend on the run_options `deploy`, `git_push`, and `external_write`, and the ban on renaming the branch during a run | **Lifted** | run_options are instructions to the run's owner |
| G-1 only rd-author may edit the requirements definition (rejection of the conductor while a run is in progress) | **Lifted** (rejection of edits from a worker's worktree and from `work/<run-id>/<item>` branches remains) | A rule for the run's owner |
| G-1 (workers), G-2 ban on direct edits to System Test and the ledger, G-3 ban on direct edits to the ID registry | **Kept** | Role boundaries. Always applied regardless of any run |
| G-5 force push, history rewriting, push to main, writes outside the working directory | **Kept** | Always-on gates |
| G-6 location of temporary files and restrictions on deleting `/work` | **Kept** | Always-on gates |
| Completion check (sending the turn back at its end) | **Not applied** (a separate session's exit is not sent back) | The owner run's completion condition |

**Rescuing runs with no owner (FR-1075)**: The hook binds an ownerless run to a session (R-2) only when there is exactly one candidate run, there is a session identifier, and there is no unconsumed start-claim from another session. If there are multiple candidates, or no identifier, it binds no run. A run whose owner has been fixed by a start-claim is never re-bound to another session. Writes to `meta.json` happen within the same exclusion as start (`work/.ebak/start-claims.lock`, waiting up to 10 seconds).

**How agents are identified**: The Copilot hook `preToolUse` event does not include the calling agent's name. So the currently running custom agent is recorded in `work/.ebak/active-agents.json` from the `subagentStart` / `subagentStop` events, and the decision combines it with the destination path of the write, the worker's worktree (`work/worktrees/…`), and the branch (`work/<run-id>/<item>`).

**Fail-open design**: Internal errors and invalid input in gate.py are treated as "allow" and logged (to prevent a gate defect from halting the whole session). Because verify checks the same rules, integration is always stopped at that point.

Hook speed: pre-tool is called thousands of times in a single run. Read-only built-in tools (view, grep, glob, read_powershell, and so on) are subject to none of the gates, so gate.py returns "allow" before loading the config file or calling git. Hooks are launched with `python -S`, which also skips site-packages initialization (gate.py uses only the standard library).

## 6.2 Checks performed by verify

These are the checks run by `scripts/verify.py`.

| ID | What is checked | Severity | How to fix |
|---|---|---|---|
| CHK-00 | The requirements definition is missing | warn (error with `--strict`) | rd-author creates it in the first run |
| CHK-01 | Duplicate IDs. IDs not in the ID registry (IDs assigned by hand) | error | Reassign with `next-id.py`. For existing documents, use `next-id.py --sync --adopt` |
| CHK-02 | Reuse of a deleted or missing-number ID | error | Assign a new ID |
| CHK-03 | An AC does not reference an existing requirement | error | Write it under the requirement's heading, or add `対応する要求:` |
| CHK-04 | A requirement has no upstream G-ID (or default constraint). It references a nonexistent G-ID. There is a G-ID with no approved requirement | error / warn | Fix the upstream field |
| CHK-05 | A MUST requirement has neither an AC nor an unanswered Q | error | Add an AC, or raise a Q |
| CHK-06 | An approved requirement has no decision record (rationale and date) | error | Use the form `承認済み（依頼 YYYY-MM-DD）` |
| CHK-07 | A catalog requirement ID is not in the requirements definition / decision status or title does not match / a row is missing for an approved, pending-approval, or on-hold requirement / rows for the same requirement are duplicated / the feature table is missing | error | Align with the requirements definition using `rdfix.py --apply` (6.3) |
| CHK-08 | A file written in the catalog does not exist | error | Fix the path or mark it "not implemented". Renames and deletions can be followed with `rdfix.py --apply` |
| CHK-09 | The ID of an implemented MUST requirement appears in neither the test code nor manual-tests (warn if not implemented) | error / warn | Write `FR-012 AC-031` in the test name or a comment |
| CHK-10 | System ACs and ledger cases do not correspond in both directions | warn (error from stage 4 onward and with `--strict-ledger`) | test-designer adds cases. Block the cases of ACs that are no longer in scope |
| CHK-11 | `ac_digests` does not match the AC text | Same as above | test-designer reviews the cases and runs `ledger.py digests --update` |
| CHK-12 | Deleting a ledger case, changing command or ac_ids without a reason, a decrease in asserts in tests/system, a change to tests/system by a worker's branch | error | Revert. Make changes with `ledger.py update --reason` |
| CHK-13 | Ambiguous words in new or changed requirements and ACs | warn (error for MUST requirements with `--strict`) | Rephrase into observable terms |
| CHK-14 | Numbers and units are hard-coded | warn | Make them PARAMs and reference them as `{PARAM-xxx}` |
| CHK-15 | A prohibited synonym from the glossary is used | warn | Fix to the correct term |
| CHK-16 | A reference to an undefined PARAM, or a PARAM not in the PARAM table | error | Add it to the PARAM table |
| CHK-17 | Code, tests, or catalog remain for a deprecated requirement (inconsistency) | error / warn | Remove it from the body once deletion is complete |
| CHK-18 | A BLOCKED AC does not reference an unanswered Q, TBD, or conflict / references an answered Q | error | Write the cause of the block / reflect the answer and remove BLOCKED |
| CHK-19 | A requirement ID or AC ID in code or tests is not in the requirements definition (paths in `checks.id_scan_exclude` are excluded; by default docs, scripts, SVG diagrams, `EABK-Studio/**` (because it is distributed to a separate repository), Spec Kit `specs/**/*.md`, `.specify/**`, and so on are excluded) | error | Fix the ID (delete remnants of deprecated IDs) |
| CHK-20 | The default-constraints section, the required columns of the persona table, a requirement's structured fields, or the verification level of an approved AC is missing. The decision status is not a prescribed value | error | Use the format in [03-requirements-format.en.md](03-requirements-format.en.md) |
| CHK-21 | (With `--run`) whether the requirement of a done item is listed in the catalog as implemented, and its system AC cases are pass | error | Redo the integration |
| CHK-22 | An approved decision record points to none of a request, a Q, an approval request, or a blanket approval as its rationale (or points to a nonexistent Q) | error | Fix the rationale |
| CHK-23 | `/work` is not in .gitignore. Temporary files are committed in docs or tests. run-ids in run-history are duplicated | error | Add `/work/` to .gitignore. Move temporary files to /work |
| CHK-24 | Missing reference target: an ID written in the body or tables (sources, related items, decision records, and so on) of the requirements definition, or in the catalog's API, table, and shared-component tables, is not defined in the requirements definition. Only IDs that the ID registry shows as deleted or deprecated are allowed within the change history, decision records, and audit findings. The catalog references a deprecated or rejected requirement (warn) | error / warn | Fix the ID, or define the referenced target |
| CHK-25 | A structured field does not point to a definition: the target entity is in neither the glossary table nor the state table. The related state is not in that target entity's state table. A `{PARAM-xxx}` in the body or acceptance criteria is not in the referenced-parameters field (a PARAM that is in the field but unused is a warn) | error / warn | Define it in the glossary or state table, or fix the field |
| CHK-26 | Orphaned definitions: a PARAM or source (SRC) referenced from nowhere, or an entity in the state table that is not the target entity of any requirement | warn | Add a reference, or deprecate it if unneeded |
| CHK-27 | Inconsistency between catalog tables: a "shared components used" entry in the feature table is not in the shared-components table. The "using requirement IDs" of the shared-components table do not match the feature table. Duplicate component, API, or table names. A shared component "…", API "…", or table "…" written in a requirement's "related existing assets" is not in the catalog | error | For requirement IDs in the shared-components table, align them with the feature table using `rdfix.py --only catalog --apply`. Otherwise, add rows to the table |
| CHK-33 | Duplicate System Tests: two or more non-blocked ledger cases guarantee the same acceptance criterion | warn | Consolidate command and AC into the one to keep with `ledger.py update`, and stop the rest with `ledger.py block --reason "merged into <kept ID>"` |

CHK-24 to 27 keep the requirements definition and the catalog consistent "as a system". In addition to the vertical links of goal (G) → requirement → acceptance criterion → System Test ledger → implementation and tests (CHK-03, 04, 09, 10), they also guarantee that the horizontal links between requirements and terms, states, PARAMs, sources, and catalog assets point to real targets and agree in both directions. You can trace links both upstream and downstream with `python scripts/rdcheck.py trace <ID or name>` ([5. Scripts](05-scripts-reference.en.md)).
The output is one finding per line (`ERROR CHK-07 docs/catalog.md:12 …`), and the last line printed is `rdcheck: errors=N warnings=M`.

## 6.3 Automatic repair of data-layer inconsistencies (rdfix)

Among the discrepancies between data-layer files (the requirements definition, the catalog, the ID registry, the System Test ledger, run history, and `.gitignore`), those that can be determined mechanically from the requirements definition can be fixed through the common entry point `python scripts/rdfix.py --full --apply` (use `--full` alone to only check). It can be invoked from three places (GitHub Actions, the installer (once after installation by default; `--no-repair` only plans, `--skip-verify` does nothing), and manually), and the result is the same. The exit codes are 0 (pass or repaired), 1 (manual action remains or a plan exists), and 2 (not executed or cancelled; all changes are rolled back for a worker's branch, an exclusion wait timeout, a write failure, a change in the requirements definition or the external-integration catalog, or a new error). It does not change the requirements definition. When verify fails and there are inconsistencies that can be fixed automatically, a `HINT rdfix: …` line is shown.

- The requirements definition is the source of truth. rdfix does not change the requirements definition (G-1). The ID registry is fixed through `next-id.py` and the ledger through `ledger.py`, and ledger changes are recorded in `history` (G-2, G-3).
- Inconsistencies that need judgment are not fixed; they are shown as `MANUAL … (owner: <role>)`. Examples: an AC's text changed (CHK-11; the cases need review), reuse of a deleted or missing-number ID (CHK-02), an ID not in the ID registry (CHK-01; it may have been assigned by hand), and a case for an AC that is no longer in scope of System Test (CHK-10).

| Target (`--only`) | What is fixed automatically | Corresponding checks |
|---|---|---|
| registry | The state in the ID registry (in use, deprecated, deleted), rows duplicated by merge=union, and creation when the ID registry is missing. IDs not in the registry are imported only when `--adopt` is given | CHK-01 |
| catalog | Align the decision status and title in the feature table with the requirements definition. Add requirement rows (implementation files and tests are filled in from the code and tests that mention the ID). Delete rows for requirements not in the requirements definition (those with no files listed) and duplicate rows. Re-point references to renamed files and delete references to nonexistent files. Set the implementation files of deprecated requirements whose code is gone to "none". Align the "using requirement IDs" of the shared-components table with the feature table | CHK-07, CHK-08, CHK-17, CHK-27 |
| ledger | Missing fields in cases, align `requirement_ids` with the AC's "corresponding requirement", fill in missing `ac_digests`, and delete `ac_digests` that no case references | CHK-10, CHK-11 |
| gitignore | Add `/work/` | CHK-23 |
| history | Delete run-history rows duplicated by merge=union | CHK-23 |

`--apply` is run by the conductor on the integration branch ("Getting started" and stage 6). It refuses to run on a worker's branch (`work/<run-id>/<item>`), and the hook also rejects `--apply` by implementer, reviewer, and rd-auditor (G-2). rd-author may use it only with `--only catalog,registry`, and test-designer only with `--only ledger`.
