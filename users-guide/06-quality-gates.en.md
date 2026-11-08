[日本語](06-quality-gates.md) | **English**

# 6. Checks and CI

Quality in EABK Lite comes from deterministic checks. The local `scripts/verify.py` and the CI workflow `ebak-verify` run the same checks. The CI workflow `ebak-data-layer` repairs the data layer automatically, and at milestones rd-auditor audits the meaning. Nothing depends on prompts or personal memory. The rules (AGENTS.md) and the checks live in the repository, so they work the same way for several people on several PCs.

| Layer | When | What it does | Does it stop work? |
|---|---|---|---|
| `verify.py` | Before finishing a change (rule in AGENTS.md) | Data-layer checks plus build and test commands | Reports with exit 1 |
| CI `ebak-verify` | Push, pull request | The same checks as `verify.py` | Workflow failure |
| CI `ebak-data-layer` | PR, push, manual, weekly | Data-layer check and automatic repair; an Issue for what it cannot fix | Repair commit or Issue |
| Audit (rd-auditor) | When you ask at a milestone | Contradictions between requirements, drift from goals, vague wording | No (findings only) |

## 6.1 There are no hooks

EABK Lite has no hooks and does not add a preamble to requests automatically. Nothing denies tool calls or sends work back, and there are no gates based on roles, edit scope, or branches. Whether the rules are followed is confirmed by verify and the CI checks. If you want a standing preamble, put it in your own Copilot instructions.

If you update from an older version and a locally modified hook file is kept, the installer prints `WARN-HOOK  <path>`. Delete the file and reopen the Copilot session ([7.4](07-troubleshooting.en.md#74-install-and-update)).

## 6.2 Check profiles (lite and full)

A profile selects which CHKs `rdcheck.py check`, `verify.py`, and `rdfix.py` report.

| Profile | CHKs reported | When to use |
|---|---|---|
| `lite` (default) | The CHKs in `checks.lite_checks` (by default CHK-01, 02, 03, 05, 09, 12, 17, 19, 24) | Everyday changes, `verify.py`, CI ebak-verify and ebak-data-layer |
| `full` | All of CHK-00 to CHK-34 | Milestone audits (rd-auditor runs with `--profile full --show-warnings`), when you want to see format warnings, when tidying a newly written requirements definition |

- The scope is set by `checks.profile` in `scripts/ebak.config.json`. To change it for one run, pass `--profile lite|full` (it takes precedence over the setting). Example: `python scripts/verify.py --docs-only --profile full --show-warnings`.
- In lite, CHKs outside the scope affect neither the output nor the exit code. Lite looks only at structure and traceability (duplicate and reused IDs, existence of referenced targets, links between ACs and tests, protection of System Tests).
- The summary line is `rdcheck: errors=N warnings=M base=… run=… profile=lite`.
- The profile applies the same way, with no exception, to `rdcheck.py check`, `verify.py`, and `rdfix.py` (including `--full`). So `rdfix.py --full` passes exactly when `verify.py --docs-only` passes with the same profile (mechanical repairs such as catalog sync run the same way under either profile).

## 6.3 Checks performed by verify

These are the checks run by `scripts/verify.py`. CHKs with ● in the "lite" column are reported by the default lite profile.

| ID | lite | What is checked | Severity | How to fix |
|---|---|---|---|---|
| CHK-00 | | The requirements definition is missing | warn (error with `--strict`) | Create the requirements definition (skill `requirement-definition`) |
| CHK-01 | ● | Duplicate IDs. IDs not in the ID registry (IDs assigned by hand) | error | Reassign with `next-id.py`. For existing documents, use `next-id.py --sync --adopt` |
| CHK-02 | ● | Reuse of a deleted or missing-number ID | error | Allocate a new ID with `next-id.py` |
| CHK-03 | ● | An AC does not reference an existing requirement | error | Write it under the requirement's heading, or add `対応する要求:` |
| CHK-04 | | A requirement has no upstream G-ID (or default constraint). It references a nonexistent G-ID. There is a G-ID with no approved requirement | error / warn | Fix the upstream field |
| CHK-05 | ● | A MUST requirement has neither an AC nor an unanswered Q | error | Add an AC, or raise a Q |
| CHK-06 | | An approved requirement has no decision record (rationale and date) | error | Use the form `承認済み（依頼 YYYY-MM-DD）` |
| CHK-07 | | A catalog requirement ID is not in the requirements definition / decision status or title does not match / a row is missing for an approved, pending-approval, or on-hold requirement / rows for the same requirement are duplicated / the feature table is missing | error | Align with the requirements definition using `rdfix.py --apply` (6.4) |
| CHK-08 | | A file written in the catalog does not exist | error | Fix the path or mark it "not implemented". Renames and deletions can be followed with `rdfix.py --apply` |
| CHK-09 | ● | The ID of an implemented MUST requirement appears in neither the test code nor manual-tests (warn if not implemented) | error / warn | Write `FR-012 AC-031` in the test name or a comment |
| CHK-10 | | System ACs and ledger cases do not correspond in both directions | warn (error with `--strict-ledger` or `--strict`) | Add cases to the ledger (`ledger.py`). Block the cases of ACs that are no longer in scope with `ledger.py block` |
| CHK-11 | | `ac_digests` does not match the AC text | Same as above | Review the cases and run `ledger.py digests --update` |
| CHK-12 | ● | Deleting a ledger case, changing command or ac_ids without a reason, a decrease in asserts in tests/system | error | Revert. Make changes with `ledger.py update --reason` |
| CHK-13 | | Ambiguous words in new or changed requirements and ACs | warn (error for MUST requirements with `--strict`) | Rephrase into observable terms |
| CHK-14 | | Numbers and units are hard-coded | warn | Make them PARAMs and reference them as `{PARAM-xxx}` |
| CHK-15 | | A prohibited synonym from the glossary is used | warn | Fix to the correct term |
| CHK-16 | | A reference to an undefined PARAM, or a PARAM not in the PARAM table | error | Add it to the PARAM table |
| CHK-17 | ● | Code, tests, or catalog remain for a deprecated requirement (inconsistency) | error / warn | Delete the remains, and remove it from the body once deletion is complete |
| CHK-18 | | A BLOCKED AC does not reference an unanswered Q, TBD, or conflict / references an answered Q | error | Write the cause of the block / reflect the answer and remove BLOCKED |
| CHK-19 | ● | A requirement ID or AC ID in code or tests is not in the requirements definition (paths in `checks.id_scan_exclude` are excluded; by default docs, scripts, SVG diagrams, `EABK-Studio/**`, Spec Kit `specs/**/*.md`, `.specify/**`, and so on) | error | Fix the ID (delete remnants of deprecated IDs). For test data or reference material, add the path to `id_scan_exclude` |
| CHK-20 | | The default-constraints section, the required columns of the persona table, a requirement's structured fields, or the verification level of an approved AC is missing. The decision status is not a prescribed value | error | Use the format in [03-requirements-format.en.md](03-requirements-format.en.md) |
| CHK-21 | | (Only with `--run`; a remnant of 0.5.x runs) whether the requirement of a done item is listed in the catalog as implemented, and its system AC cases are pass | error | Fix the catalog and the ledger |
| CHK-22 | | An approved decision record points to none of a request, a Q, an approval request, or a blanket approval as its rationale (or points to a nonexistent Q) | error | Fix the rationale |
| CHK-23 | | `/work` is not in .gitignore. Temporary files are committed in docs or tests. run-ids in `docs/run-history.md` are duplicated | error | `rdfix.py --apply` adds `/work/` and removes duplicate rows. Move temporary files to /work |
| CHK-24 | ● | Missing reference target: an ID written in the body or tables of the requirements definition, or in the catalog's API, table, and shared-component tables, is not defined in the requirements definition (IDs that the ID registry shows as deleted or deprecated are allowed in the change history, decision records, and audit findings). The catalog references a deprecated or rejected requirement (warn) | error / warn | Fix the ID, or define the referenced target |
| CHK-25 | | A structured field does not point to a definition: the target entity is in neither the glossary table nor the state table. The related state is not in its state table. A `{PARAM-xxx}` in the body or ACs is not in the referenced-parameters field (a PARAM in the field but unused is a warn) | error / warn | Define it in the glossary or state table, or fix the field |
| CHK-26 | | Orphaned definitions: a PARAM or source (SRC) referenced from nowhere, or an entity in the state table that is not the target entity of any requirement | warn | Add a reference, or deprecate it if unneeded |
| CHK-27 | | Inconsistency between catalog tables: a "shared components used" entry in the feature table is not in the shared-components table. The "using requirement IDs" of the shared-components table do not match the feature table. Duplicate component, API, or table names. A requirement's "related existing assets" are not in the catalog | error | Align the shared-components requirement IDs with `rdfix.py --only catalog --apply`. Otherwise, add rows to the table |
| CHK-28 | | External integration catalog (`docs/integrations.md`): reference to an undefined INT-ID; ID format, duplicates, reuse; missing required or viewpoint fields; values that look like credentials | error / warn | Allocate with `next-id.py INT` and fill fields with a value, なし, or TBD（Q-xxx）. Never write secret values |
| CHK-29 | | A requirement field is not in the metadata definition (`scripts/metadata.json`), or its value does not match the allowed format | error | Align the field name and value with the definition |
| CHK-30 | | Areas: a requirement's area does not match the assignment table or the catalog section, an area has no upstream G-ID, the count of requirements differs | error / warn | Align the area field, the assignment table, and the catalog sections |
| CHK-31 | | Tables of the same kind in the catalog have different column names or order | warn | Use the same columns as the first table |
| CHK-32 | | The items directly under one area section exceed the limit (PARAM-043) | warn | Split the section |
| CHK-33 | | Duplicate System Tests: two or more non-blocked ledger cases guarantee the same acceptance criterion | warn | Consolidate into the one to keep with `ledger.py update`, and stop the rest with `ledger.py block --reason "merged into <kept ID>"` |
| CHK-34 | | System Test count: two or more non-blocked ledger cases (excluding canary and serial) share the same test file, layer, and requirements | warn | `python scripts/ledger.py consolidate --apply`. Use `ledger.py cost` for the count and slow commands, and `system_test.budget` for limits (`ledger.py cost --check` exits 1 when exceeded) |

CHK-24 to 27 keep the requirements definition and the catalog consistent "as a system". In addition to the vertical links (goal → requirement → acceptance criterion → ledger → implementation and tests), they confirm that the horizontal links between requirements and glossary terms, states, PARAMs, sources, and catalog assets point to existing targets and agree in both directions. You can follow the links with `python scripts/rdcheck.py trace <ID or name>` ([5. Scripts](05-scripts-reference.en.md)).

The output is one finding per line (`ERROR CHK-07 docs/catalog.md:12 …`), followed by one summary line. With `--show-warnings`, warnings are shown too.

## 6.4 Automatic repair of data-layer inconsistencies (rdfix)

Among the mismatches between the data-layer files (requirements definition, catalog, ID registry, System Test ledger, run history, `.gitignore`), those that follow mechanically from the requirements definition can be fixed through the common entry point `python scripts/rdfix.py --full --apply` (`--full` alone only checks).

- There are three callers, with the same result: the CI workflow ebak-data-layer, the installer (once after installing by default; `--no-repair` plans only, `--skip-verify` does nothing), and manual runs.
- Exit codes: 0 (pass / repaired), 1 (manual items left / repairs planned), 2 (not run / cancelled). Exit 2 happens when run on a 0.5.x worker branch (`work/<run-id>/<item>`), on lock-wait timeout, on a write failure, when the requirements definition or the external integration catalog changed, or on a new error; every change is undone.
- The requirements definition is the source of truth. rdfix never changes it. The ID registry is fixed through `next-id.py` and the ledger through `ledger.py`, with ledger changes kept in `history`.
- When verify fails and there are inconsistencies that can be fixed automatically, a `HINT rdfix: …` line is printed.
- Inconsistencies that need a judgment are not fixed; they are shown as `MANUAL <CHK> <location> <message>（担当: <kind of work>）次の行動: …`. The "担当" (in charge) is one of `要求定義書` (requirements definition), `System Test の台帳` (System Test ledger), `コードとカタログ` (code and catalog), or `リポジトリ` (repository), naming which files the fix is about. Examples: the AC text changed (CHK-11; review the ledger cases), reuse of a deleted or missing-number ID (CHK-02), an ID not in the ID registry (CHK-01; it may have been assigned by hand).

| Target (`--only`) | What is fixed automatically | Related checks |
|---|---|---|
| registry | ID registry states (in use, deprecated, deleted), rows duplicated by merge=union, creation when the ID registry is missing. Only with `--adopt`, IDs missing from the registry are taken in | CHK-01 |
| catalog | Align decision status and title of the feature table with the requirements definition. Add requirement rows. Delete rows for requirements not in the requirements definition (with no files written) and duplicate rows. Re-point references to renamed files and remove references to missing files. Set implementation files of deprecated requirements whose code is gone to "none". Align "using requirement IDs" of the shared-components table with the feature table | CHK-07, CHK-08, CHK-17, CHK-27 |
| ledger | Missing case fields, align `requirement_ids` with the AC's "corresponding requirement", add missing `ac_digests` and remove unused ones | CHK-10, CHK-11 |
| gitignore | Add `/work/` | CHK-23 |
| history | Remove rows of `docs/run-history.md` duplicated by merge=union (only in repositories updated from 0.5.x) | CHK-23 |

Run `--apply` on the default branch (or your own working branch).

## 6.5 CI

### ebak-verify

`.github/workflows/ebak-verify.yml` runs `scripts/verify.sh --show-warnings` on pull requests and pushes to main. The check scope follows `checks.profile` (lite by default). It also runs the build and test commands registered in `verify.commands`. Add the toolchain they need before the verify step ([4.11](04-customization.en.md#411-ci)).

### ebak-data-layer

`.github/workflows/ebak-data-layer.yml` runs `verify.py --docs-only` on PRs, pushes to main, manual runs, and a weekly schedule. On failure, it repairs with `rdfix.py --full --apply` and checks again. If that passes, it commits the repair (to the PR branch for PRs from the same repository, otherwise to `eabk/data-layer-fix` with a PR). If not, it creates an Issue labeled `eabk-data-layer`. It never changes the requirements definition. Details and how to disable it are in [4.11](04-customization.en.md#data-layer-workflow-ebak-data-layer).

## 6.6 Milestone audit (rd-auditor)

Problems of meaning that checks cannot catch (contradictions between requirements, drift from goals (G-IDs), vague wording, mismatches in meaning with the catalog and ledger) are audited by rd-auditor at milestones (before a release, before merging a large change, and so on). Do not use it for every change.

1. In Copilot, choose **rd-auditor** as the agent and ask, for example, "audit the diff" or "audit everything 3 times". A diff audit compares with `base_branch` by default. The default number of runs is 1 for a diff and 3 for everything.
2. rd-auditor uses the results of `python scripts/verify.py --docs-only --profile full --show-warnings` and `rdcheck.py stats` and concentrates on judging meaning. When subagents are available, the runs are done independently in parallel and decided by majority.
3. Results are written to `work/audit/<date-time>/` as the output of each run, `run<n>.md`, and the aggregate `report.md`. Findings that appear in a majority of runs are "high confidence"; the rest are "needs review".
4. rd-auditor does not change any file tracked by git. You decide whether to act on a finding and do it as a separate change (and again bring verify to exit 0).
