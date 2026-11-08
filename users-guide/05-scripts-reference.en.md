[日本語](05-scripts-reference.md) | **English**

# 5. Scripts Reference

All scripts run on the Python 3.9+ standard library only. They can be run from anywhere in the repository and operate relative to the git root. The exact list of options is shown by `python scripts/<name>.py --help`. Output is short and in a form an LLM can read as is (one finding per line, with a one-line summary at the end).

| Script | Purpose | What it writes |
|---|---|---|
| `scripts/ebaklib.py` | Shared library (not run directly) | — |
| `scripts/verify.py` (`.ps1`, `.sh`) | Deterministic checks in one command (the definition of done) | Only logs and the cache under `/work` |
| `scripts/rdcheck.py` | Parser, checks and search for the requirements definition | Nothing (read-only) |
| `scripts/rdfix.py` | Automatic repair of data-layer inconsistencies | Catalog, ID registry, ledger, `.gitignore` (only with `--apply`; never the requirements definition) |
| `scripts/entities.py` | Entity register and comparison with the enterprise data catalog | Nothing (read-only) |
| `scripts/extpoints.py` | Extension points for project-specific checks (used by rdcheck and rdfix) | — |
| `scripts/next-id.py` | ID allocation | `docs/id-registry.md` and the allocation log |
| `scripts/ledger.py` | The only writer of the System Test ledger | `tests/system/ledger.json` |
| `scripts/summarize.py` | Summary of long logs | Nothing |
| `scripts/adopt.py` | Adopting an existing app | `docs/baseline/`, `tests/system/golden/`, `work/import/` |
| `tools/install.py` | Install, update, uninstall | The target repository |

## ebaklib.py (shared library)

The library imported by the other scripts. It parses the requirements definition (要求定義書), catalog, ID registry and System Test ledger, reads `scripts/ebak.config.json`, runs git, and decides where `/work` is. The toolkit version `TOOLKIT_VERSION` (0.6.0) is defined here. Users never run it directly.

## verify.py (deterministic checks; the definition of done)

```bash
python scripts/verify.py                          # management-data checks + verify.commands (build, tests, ...)
python scripts/verify.py --docs-only              # management-data checks only (requirements, catalog, ledger)
python scripts/verify.py --quick                  # skip commands marked "slow": true
python scripts/verify.py --profile full           # choose the check profile (lite | full; overrides the config)
python scripts/verify.py --show-warnings          # also print warnings
python scripts/verify.py --no-cache               # always run, never reuse the cache
python scripts/verify.py --base main              # base of the diff checks (default: merge-base with base_branch)
python scripts/verify.py --strict                 # treat important warnings as errors (e.g. before a release)
./scripts/verify.sh   /  .\scripts\verify.ps1     # the same (wrappers that find Python and pass the arguments to verify.py)
```

Exit 0 means pass. The `AGENTS.md` rules require exit 0 before a change is finished. CI `ebak-verify` runs `scripts/verify.sh --show-warnings`. Full logs are saved to `/work/logs`; only a summary is printed. The project's build and test commands go into `verify.commands` in `scripts/ebak.config.json` ([4. Customization](04-customization.en.md)).

**Check profile:** `checks.profile` in `scripts/ebak.config.json`, `lite` (default) or `full`, decides which CHKs are reported.

| Profile | Checks reported | When to use |
|---|---|---|
| `lite` (default) | Only the CHKs in `checks.lite_checks` (default `CHK-01, CHK-02, CHK-03, CHK-05, CHK-09, CHK-12, CHK-17, CHK-19, CHK-24`: structure and traceability). Other CHKs affect neither the output nor the exit code | Every change and CI |
| `full` | All of CHK-00 to 34 (including writing-style warnings such as vague words CHK-13, hard-coded numbers CHK-14 and forbidden synonyms CHK-15) | Milestone audits (rd-auditor uses `--profile full --show-warnings`), or whenever you want to see them |

To see the writing-style warnings: `python scripts/verify.py --docs-only --profile full --show-warnings`.

**Cache:** when the working tree is clean (no uncommitted changes and no untracked files), a PASS is recorded in `/work/.ebak/verify-cache.json`. The key is HEAD, the arguments and `scripts/ebak.config.json`. Running the same verify on the same commit returns `PASS (cached …)` immediately. FAIL is never recorded. Disable it with `--no-cache` or the environment variable `EBAK_VERIFY_NO_CACHE=1`.

## rdcheck.py (requirements definition parser)

```bash
python scripts/rdcheck.py check [--base REF|none] [--profile lite|full] [--strict] [--errors-only] [--json]
python scripts/rdcheck.py show FR-012 AC-031 Q-007     # print only the given requirement / AC / question blocks (no need to read everything)
python scripts/rdcheck.py list --state 承認済み --priority MUST
python scripts/rdcheck.py list --state 承認待ち         # requirements awaiting approval
python scripts/rdcheck.py list --level system          # ACs covered by System Tests
python scripts/rdcheck.py list --area 受付              # filter by area (--by-area groups by area; retired items excluded)
python scripts/rdcheck.py index FR-012 [--kind 検証] [--json]   # typed relations (上位/出典/参照/実装/検証/使用), generated on demand, never saved
python scripts/rdcheck.py hierarchy                    # kind -> category -> area -> item hierarchy (generated on demand)
python scripts/rdcheck.py stats                        # audit metrics (JSON)
python scripts/rdcheck.py similar "resume an interrupted input"   # before creating, find similar existing requirements / ACs (--kind FR|AC|CASE|CAT, --top N)
python scripts/rdcheck.py similar --pairs [--min 0.35] # pairs of similar items (merge candidates)
python scripts/rdcheck.py digest AC-031                # AC digest (text with PARAMs expanded)
python scripts/rdcheck.py trace FR-012 [--json]        # upstream (G, sources), sideways (terms, states, PARAM), downstream (ACs, ledger cases, catalog, code)
python scripts/rdcheck.py trace G-002 申請 PARAM-004   # trace back from goals, entities and PARAMs to the related requirements (impact analysis)
python scripts/rdcheck.py trace INT-001                # requirements and ACs that reference an external integration
```

`check` prints one finding per line (`<ERROR|WARN> <CHK-ID> <location> <message>`) and a final summary line.

```text
rdcheck: errors=0 warnings=2 base=… run=… profile=lite
```

`--profile` overrides `checks.profile` in `scripts/ebak.config.json`. Exit 0 = no errors, 1 = at least one error. The default of `--base` is the merge-base with `base_branch` (default `main`), used by the diff checks; `none` disables the comparison. The profile applies the same way to `rdcheck.py check`, `verify.py`, and `rdfix.py`.

## rdfix.py (automatic repair of data-layer inconsistencies)

Treating the requirements definition (要求定義書) as the source of truth, it aligns the catalog, ID registry, System Test ledger and `.gitignore` (and duplicated rows of `docs/run-history.md` left in repositories updated from 0.5.x). **It never changes the requirements definition or the external integration catalog (`docs/integrations.md`).** The findings it reports and its pass/fail follow the same check profile (`checks.profile`) as `verify.py`, so `rdfix.py --full` passes exactly when `verify.py --docs-only` passes with the same profile (the mechanical repairs themselves run regardless of the profile).

```bash
python scripts/rdfix.py                           # show the repair plan (no writes). Exit 1 if there is something to fix
python scripts/rdfix.py --apply                   # write the fixes, then confirm with rdcheck
python scripts/rdfix.py --only catalog,ledger     # restrict the targets: registry, catalog, ledger, gitignore, history
python scripts/rdfix.py --adopt --apply           # also adopt IDs missing from the ID registry (after confirming they were not hand-numbered)
python scripts/rdfix.py --json
```

To check the data layer (the same rdcheck as `verify.py --docs-only`) and repair it in one run, add `--full`.

```bash
python scripts/rdfix.py --full                    # check only (no writes, does not wait for the lock)
python scripts/rdfix.py --full --apply            # check -> repair -> re-check (until converged, up to 3 rounds = PARAM-026)
python scripts/rdfix.py --full --apply --json     # the same result as JSON (manual items have chk, file, line, owner, action)
python scripts/rdfix.py --full --apply --lock-wait 60   # change the lock wait in seconds (default 30 = PARAM-027)
```

**Output:** `FIX <CHK> <location> <message>` (fixed automatically) and `MANUAL <CHK> <location> <message>（担当: <area of work>）次の行動: …` (needs a judgment), followed by one line `rdfix: fix=N manual=M mode=…`. "担当" (in charge) is not a role name but the kind of work that fixes it.

| 担当 (in charge) | What to fix |
|---|---|
| `要求定義書` (requirements definition) | The text of the requirements definition (AC text, reused or hand-numbered IDs, ...). Follow the skill `requirement-definition` |
| `System Test の台帳` (System Test ledger) | Ledger cases, via `ledger.py update`, `block`, `digests --update` |
| `コードとカタログ` (code and catalog) | Implementation files, tests and shared components in the catalog |
| `リポジトリ` (repository) | Repository-wide settings such as `.gitignore` and branches |

Example output:

```text
MANUAL CHK-11 tests/system/ledger.json AC-001 の本文が…（担当: System Test の台帳）次の行動: …
```

**Exit codes:**

| Value | Meaning |
|---|---|
| 0 = passed / repaired | Nothing left to fix automatically |
| 1 = work remains | Manual items remain, repairs are planned (without `--apply`), or not converged |
| 2 = not run / undone | `--apply` on a leftover 0.5.x worker branch (`work/<run-id>/<item>`), lock wait timed out, all changes undone, or an unexpected error |

**Safety (`--full --apply`):** only one repair runs at a time per repository (`work/.ebak/rdfix.lock`; a later one waits up to `--lock-wait` seconds, and a lock left by a dead process is taken over). Every write replaces a temporary file. If the requirements definition or external integration catalog changed, a write failed, an error appeared that was not there before the repair, or an unexpected error occurred, every change is undone, the files are restored to their pre-repair content, and it ends with exit 2. `--apply` is refused on 0.5.x worker branches, so run it on the default branch.

**Three entry points** all call the same `rdfix.py --full [--apply]`.

1. The GitHub Actions workflow `ebak-data-layer.yml`: `rdfix.py --full --apply` on failure. Only a repair that passes is committed; what cannot be fixed becomes an Issue.
2. The installer `tools/install.py`: by default runs `rdfix.py --full --apply` once after install or update. `--no-repair` runs `rdfix.py --full` (check and plan only, no writes), `--skip-verify` neither checks nor repairs, and `--dry-run`, `--check`, `--uninstall` and `--purge` never repair. If the repair is undone or manual items remain, the toolkit stays installed and the installer's exit code does not depend on the data-layer result.
3. Manual runs by you or Copilot.

No entry point changes the requirements definition or the external integration catalog, and local runs never commit the repair.

`python scripts/ledger.py repair [--apply]` repairs only the ledger part (used internally by rdfix).

## entities.py (entity register and the enterprise data catalog)

```bash
python scripts/entities.py list  [--repo DIR] [--json]            # entity register (name, description, managing table, usage, columns, relations)
python scripts/entities.py check [--repo DIR] [--json] [--strict] # compare with the enterprise data catalog (match / EABK only / enterprise only / naming variants)
python scripts/entities.py todo  [--repo DIR] [--json]            # to-dos for uncovered entities (as question-list rows)
```

The register is derived from the glossary, the state table and each requirement's "target entities" (no dedicated file). Descriptions, tables or usage missing from the management data are shown as "説明未記載" (no description) etc., never guessed. The enterprise data catalog source is optional, set by `enterprise_data_catalog` in `scripts/ebak.config.json` ([4. Customization](04-customization.en.md)). Without it, the script still runs and reports "企業データカタログ: 未設定（照合していない）" (not configured). The source is read-only and its text is never stored or copied (only names and `source:line` are printed). `todo` only prints question-list rows (without IDs) and never edits the management data; allocate IDs with `next-id.py Q` when copying them into the question list. Exit 0 (`check --strict` exits 1 on differences or when comparison is impossible).

## extpoints.py (extension points for project-specific checks)

A way to add your own checks to rdcheck and rdfix without editing the toolkit's `scripts/*.py`. Not run directly. There are two ways to register, and both survive `tools/install.py` updates.

1. `"extensions": {"checks": [{"module": "m", "function": "f", "target": "rdcheck"}]}` in `scripts/ebak.config.json` (`target` is `rdcheck`, `rdfix` or `both`; default `both`)
2. Files in `scripts/ext/*.py` (loaded automatically; each public function is a check; `CHECKS = [fn, ...]` restricts them)

A check is `fn(root, cfg)` and returns a list of findings (empty means pass). A finding may be a string, a `{level, chk, loc, msg}` dict or a 4-tuple. Level `ERROR` (default) fails; `WARN` is a warning. A module that cannot be loaded, a missing function or an exception is never swallowed; it is reported as an ERROR naming the extension. See [4. Customization](04-customization.en.md).

## next-id.py (ID allocation)

```bash
python scripts/next-id.py FR                    # FR-013
python scripts/next-id.py NFR-SEC               # NFR-SEC-004
python scripts/next-id.py AC --count 3          # AC-041 AC-042 AC-043
python scripts/next-id.py FR --note "draft save" # leave a note in the ID registry
python scripts/next-id.py Q | PARAM | G | SRC | E2E | IT
python scripts/next-id.py INT                   # INT-001 (ID in the external integration catalog docs/integrations.md; [chapter 11](11-integration-catalog.en.md))
python scripts/next-id.py --peek FR             # show the next ID without allocating
python scripts/next-id.py --sync                # align ID registry states with the text (in use / retired / deleted)
python scripts/next-id.py --sync --adopt        # adopt existing IDs missing from the registry (right after installing)
python scripts/next-id.py --sync --finalize     # mark allocated but unused IDs as skipped
```

IDs are allocated only with this script (an `AGENTS.md` rule). The next number is max(requirements definition, ID registry, the same files on `base_branch`, System Test ledger, the allocation log shared by the working trees of one clone) + 1. Allocated IDs are recorded in `docs/id-registry.md` and `<git-common-dir>/ebak-id-alloc.json`, so other working trees on the same PC never get the same ID. When two PCs allocate the same ID at the same time, CHK-01 detects it ([2. Daily Workflow](02-daily-workflow.en.md)).

## ledger.py (System Test ledger)

The only writer of `tests/system/ledger.json`. Cases are never deleted; stop them with `block`. Changing `command` or `ac_ids` requires `--reason`, which is kept in the history. pass / fail is recorded only from the exit code of an executed command. `--by` sets who is recorded in the history (your name, `ci`, ...).

```bash
python scripts/ledger.py summary [-v]
python scripts/ledger.py add --req FR-012 --ac AC-031 --title "…" --layer e2e --command "…" [--canary] [--serial]
                                                    # refused if the AC already has an active case (extend it with update; exception: --new-case-reason "reason")
python scripts/ledger.py update E2E-001 --command "…" --reason "…"     # --title, --ac, --req, --canary can be changed too. Reason required
python scripts/ledger.py block E2E-001 --reason "…"                   # use instead of deleting
python scripts/ledger.py set E2E-001 pass|fail|blocked|not_run [--evidence PATH] [--reason "…"]
python scripts/ledger.py digests [--update]                           # AC digests (text with PARAMs expanded)
python scripts/ledger.py repair [--apply]                             # align the ledger with the requirements definition (used by rdfix.py)
python scripts/ledger.py preflight [--cases ID,..] [--all]            # pytest collect-only (syntax / import errors, zero tests selected)
python scripts/ledger.py cost [--top N] [--check]                     # cases, test files, mergeable cases, slow commands, budget (--check: exit 1 when over)
python scripts/ledger.py consolidate [--apply] [--reason "…"]         # merge cases with the same test file, layer and requirement (plan only by default)
python scripts/ledger.py run --select changed|failed|all [--base REF] [--canary-first] [--stop-on-canary-fail] [--max-minutes N] [--jobs N|auto]
python scripts/ledger.py run --cases E2E-001,IT-002 [--no-record]     # only the given cases; --no-record leaves the ledger unchanged
```

`--select changed` prefers cases whose requirement or AC IDs appear in lines added or changed in the git diff, and prints `select <case ID>: <reason>` per case. When it cannot narrow down (e.g. shared code changed), it widens the selection and says so in the reason. `run` prints lines `<id> <requirement_ids> <pass|fail> <seconds> <evidence>` and a `結果: …` (result) line. Details are saved under `/work` (`--results PATH` sets the location). Cases that already passed or failed on the same commit with a clean working tree are not re-run (force with `--rerun-passed` / `--rerun-failed`).

## summarize.py (log summary)

```bash
python scripts/summarize.py work/logs/verify-…-unit.log [--max-lines 15] [--tail 5]
npm test 2>&1 | python scripts/summarize.py -
```

Prints only the test runner's summary lines, the first few distinct error lines, and the last few lines.

## adopt.py (adopting an existing app)

```bash
python scripts/adopt.py scan [--since-days 365] [--json]          # inventory -> docs/baseline/inventory.{json,md}
python scripts/adopt.py request [--clusters 6] [--cluster NAME] [--implement] [--stdout]
                                                                  # request draft to paste into Copilot chat -> work/import/adopt-<datetime>.md
python scripts/adopt.py anchor SRC-003 src/a.py:10-48 [--note "…"] # pin source evidence -> docs/baseline/evidence.json
python scripts/adopt.py check [--strict] [--json]                 # evidence drift, recovery rate, checks of recovered requirements (exit 1 = error)
python scripts/adopt.py golden add NAME -- CMD ARG...             # characterization test (golden master)
python scripts/adopt.py golden record|check|list [NAME] [--update]
```

`request` prints a request with `<request>`, `<references>` and `<constraints>` sections. The default `<constraints>` are "承認: 厳格" (approval: strict; recovered requirements stay awaiting approval) and "実装: しない" (implementation: none; code is not changed); with `--implement` it becomes "実装: 承認済みの要求すべて" (implement all approved requirements). Paste the output as is into the default agent's chat. `adopt.py` never edits the requirements definition and never allocates IDs. Details: [10. Adopting an existing app](10-adopting-existing-apps.en.md).

## tools/install.py (install, update, uninstall)

Usually used through `tools/install.ps1` / `tools/install.sh` (one command that downloads this repository and runs it). From a local clone:

```bash
python tools/install.py --target <repo> [--dry-run] [--force] [--no-ci]
python tools/install.py --target <repo> --check        # check whether an update is needed (exit 1 if so)
python tools/install.py --target <repo> --no-repair    # after installing, run rdfix.py --full (check and plan only, no writes)
python tools/install.py --target <repo> --skip-verify  # no check or repair after installing
python tools/install.py --target <repo> --uninstall    # remove unmodified toolkit files and blocks (keeps management data and config)
python tools/install.py --target <repo> --purge        # --uninstall + remove management data, config, /work and appended lines
python tools/install.py --version
```

| Option | Behavior |
|---|---|
| `--target DIR` | Target repository (default: current directory) |
| `--source DIR` | Toolkit source (default: this script's repository) |
| `--dry-run` | Print the operations without writing |
| `--check` | Check whether an update is needed (exit 1 if so) |
| `--force` | Also overwrite or remove locally modified toolkit files (keeps `.ebak-backup-*`) |
| `--no-ci` | Do not install `.github/workflows/ebak-verify.yml` |
| `--no-repair` | Do not repair after installing; print only the check and repair plan with `rdfix.py --full`. `-NoRepair` in the PowerShell wrapper |
| `--skip-verify` | Neither check nor repair the data layer after installing |
| `--uninstall` / `--purge` | Remove (see the examples above) |
| `--allow-non-git` | Install into a directory that is not a git repository |
| `--version` | Print the toolkit version and exit |

What it does (idempotent): installs the distributed files (rd-auditor, skills, `ebak-verify.yml` and `ebak-data-layer.yml`, `scripts/*`, EABK-Studio) and updates them if unmodified. Management-data templates (requirements definition, catalog, external integration catalog, ID registry, ledger) are created only when missing. `scripts/ebak.config.json` gets new keys while your values are kept. It adds `/work/` to `.gitignore`, union-merge lines to `.gitattributes`, and the rules block to `AGENTS.md` and `.github/copilot-instructions.md`, and records versions and hashes in `.github/ebak-toolkit.json`. Finally it runs `rdfix.py --full --apply` once (the requirements definition is never changed and the repair is not committed).

When updating from an older version (such as 0.5.x), old files you did not modify (agents such as conductor, the `/build` skills, the hook files `.github/hooks/quality-gates.json`, `.github/hooks/prompt-prefix.json` and `scripts/hooks/gate.py`, removed scripts) are deleted (`REMOVE`); modified ones are kept (`KEEP-LOCAL`; `--force` deletes them). When a modified hook file is kept, the installer prints `WARN-HOOK  <path>`: the file calls the deleted `gate.py`, and when a hook errors Copilot denies every tool, so delete the file and reopen the Copilot session. The config keys `gates`, `limits`, `credits`, `worktree_share`, `prompt_prefix` and the old default verify command `toolkit-unit` are removed (`PRUNE`). An existing `.github/ebak-prompt-prefix.md` is left alone but no longer read. The requirements definition, ledger and catalog are not changed. Worktrees and `work/*` branches left by 0.5.x runs are not removed automatically; check them with `git worktree list` and `git branch --list "work/*"` and delete them by hand.

## EABK-Studio (data-layer viewer)

Installed into `EABK-Studio/` of the target repository. A local, read-only web app that shows the data layer (requirements definition, catalog, ledger) as diagrams, tables and search (Japanese and English).

```text
python EABK-Studio/studio.py [--repo DIR] [--port 8765] [--no-open] [--role pm|architect|swe] [--check]
```

| Option | Behavior |
|---|---|
| `--repo DIR` | Target repository (default: current directory; searches parent directories for the data layer) |
| `--port N` | Listening port (default 8765; if in use, tries the next numbers up to 20 times) |
| `--no-open` | Do not open the browser automatically |
| `--role pm\|architect\|swe` | First screen to open (dashboard / 2D map / table) |
| `--check` | Print which management-data files exist, the parsed counts and warnings, then exit. Exit 0 if a data layer exists, otherwise 1 |

- Wrappers: `EABK-Studio/start.ps1 [-Repo DIR] [-Port N] [-Role …] [-Check] [-NoOpen]`, `EABK-Studio/start.sh [DIR] [PORT] [studio.py options…]`.
- It never reads source code and listens on 127.0.0.1 only. The only writes are catalog titles and decision states in `docs/catalog.md` that you confirm and run in "整合性保守" (consistency maintenance).
- Role-based guides are in [studio/README.en.md](studio/README.en.md).
