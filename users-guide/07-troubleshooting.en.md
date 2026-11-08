[日本語](07-troubleshooting.md) | **English**

# 7. Troubleshooting

## 7.1 verify or CI fails

| Symptom | What to do |
|---|---|
| `python scripts/verify.py` exits 1 | Fix the `ERROR CHK-xx <location> <message>` lines from the top. How to fix each CHK is in [6.3](06-quality-gates.en.md#63-checks-performed-by-verify). Full logs are in `/work/logs/` |
| A `HINT rdfix: …` line appears | There are inconsistencies that can be fixed automatically. Check the plan with `python scripts/rdfix.py --full`, then fix with `python scripts/rdfix.py --full --apply` ([7.2](#72-data-layer-mismatches-rdfix)) |
| CI ebak-verify fails on the data-layer check | CI does not repair. Run `python scripts/rdfix.py --full --apply` locally and push the repair in the same change ([7.2](#72-data-layer-mismatches-rdfix)) |
| It passes locally but only CI ebak-verify fails | CI may lack your app's toolchain. Add setup steps (such as `actions/setup-node`) before the verify step in `.github/workflows/ebak-verify.yml`. Also check that you are not overriding `checks.profile` with `--profile` in your local command |
| `PASS (cached …)` appears and you worry the result is stale | The cache is used only when the working tree is clean and HEAD, arguments, and configuration are the same. After changing the build environment (SDK, dependencies), re-run with `--no-cache` |
| `FAIL config` | `verify.commands` has an element without `run` or an invalid element. Fix it to the format in [4.6](04-customization.en.md#46-build-static-analysis-and-test-commands-verifycommands) |
| Many warnings with `--profile full` | full also reports format warnings (CHK-13 ambiguous words, CHK-14 hard-coded numbers, CHK-15 prohibited synonyms, and so on). Warnings do not affect the exit code. Fix them gradually, in step with milestone audits |
| Many CHK-01 and CHK-20 errors right after installing | Your existing requirements definition is not in the toolkit format. Run `python scripts/next-id.py --sync --adopt`, then ask Copilot to "align the existing requirements definition with the toolkit format without changing its meaning" (for existing apps, see [10](10-adopting-existing-apps.en.md)) |
| CHK-19 detects IDs inside test data or reference material | Add that path (glob) to `checks.id_scan_exclude` in `scripts/ebak.config.json`. The list replaces the default instead of being merged, so copy the default (`DEFAULT_CONFIG` in `scripts/ebaklib.py`) before adding to it |
| CHK-08 cannot find a path in the catalog | Paths are relative to the repository root and comma-separated, like `src/a.ts, src/b.ts`. If you renamed or deleted a file, `python scripts/rdfix.py --apply` fixes the reference |
| CHK-10 or CHK-11 appears (AC and ledger out of sync) | An AC was added or changed but the System Test ledger did not follow. Add or review cases and run `python scripts/ledger.py digests --update`. Update the ledger only with `ledger.py` |
| CHK-12 appears | A ledger case was deleted, changed without a reason, or asserts in `tests/system` decreased. Revert, and make the change with `ledger.py update --reason "…"` so the reason is recorded |

## 7.2 Data-layer mismatches (rdfix)

When the catalog, ID registry, or ledger disagree, for example after a merge (CHK-07, CHK-01, CHK-11), check with `python scripts/rdfix.py --full` and fix with `python scripts/rdfix.py --full --apply`. The requirements definition (要求定義書) is never changed.

| Exit code | Meaning | What to do next |
|---|---|---|
| 0 = pass / repaired | Nothing left to fix automatically | Review the diff and commit it (rdfix does not commit) |
| 1 = manual items left / repairs planned | There are `MANUAL` lines, you ran without `--apply` and only got the plan, or it did not converge | Follow the `MANUAL …（担当: …）次の行動: …` lines. "担当" is the kind of work: `要求定義書` (requirements definition), `System Test の台帳` (System Test ledger), `コードとカタログ` (code and catalog), or `リポジトリ` (repository) |
| 2 = not run / cancelled | One of the causes below. Every change has been undone | Remove the cause and run the same command again |

Main causes of exit 2:

| Message / situation | What to do |
|---|---|
| Lock-wait timeout (`work/.ebak/rdfix.lock`) | Another `--apply` is running. Wait for it to finish and run again (the wait is `--lock-wait` seconds, 30 by default). A lock left by a dead process is taken over automatically |
| Write failure, a change in the requirements definition or `docs/integrations.md`, or a new error | Every change was undone. Check that no editor holds the files open. For files that could not be restored, the pre-repair content is saved in `work/.ebak/rdfix-undo-*/` |

## 7.3 IDs collide across people or PCs

If `next-id.py` runs on two branches at the same time, the same ID can be allocated twice. After merging, the ID registry keeps both rows through `merge=union`, and CHK-01 (duplicate ID) detects it.

1. On the branch merged later, allocate a new ID for the colliding requirement or AC with `python scripts/next-id.py <kind>`, and rewrite the references in the requirements definition, tests, and catalog. Do not number by hand.
2. Tidy the duplicate registry rows with `python scripts/rdfix.py --full --apply`, and bring `python scripts/verify.py` to exit 0.
3. Prevention: merge the base branch (`main`) before allocating. `next-id.py` also looks at the IDs on the base branch to decide the next number.

## 7.4 Install and update

| Symptom | What to do |
|---|---|
| `KEEP-LOCAL <file>` appears on update | Toolkit files you modified locally are not overwritten. To take in the new version, check with `--dry-run`, then merge the diff by hand or use `--force` (which keeps `.ebak-backup-*`). Differences only in line endings from Windows `core.autocrlf` do not cause `KEEP-LOCAL` |
| A note on update says that N files this version does not ship remain | They were installed by an older version. A normal update does not delete them. Reinstall with `--clean` (clean install; [9.4](09-versioning.en.md#94-updating-from-an-older-version-clean-install)) |
| `--clean` says to commit or stash uncommitted changes first | Check `git status`, commit or `git stash`, and run again. It runs only on a clean working tree so that deleted files can be restored from git |
| `WARN-WIRING <file>:<line>` appears | A custom check you added directly to `scripts/*.py` will be dropped by the update. Register it again in `extensions.checks` or `scripts/ext/` ([4.7](04-customization.en.md#47-project-specific-checks-extensionschecks--scriptsext)) |
| You want to stop the data-layer repair after installing | `--no-repair` checks and plans only (writes nothing); `--skip-verify` neither checks nor repairs. The PowerShell wrapper uses `-NoRepair`. The installer's exit code does not depend on the data-layer result |

### Updating from 0.5.x to 0.6.0 (EABK Lite)

- **How to update**: The installer has no migration code for older versions. Do a clean install with `--clean`. The old agents, skills, hooks, scripts, the auto-repair workflow and the old settings keys are deleted even if you modified them, and this version is installed again.
- **Settings**: `scripts/ebak.config.json` is recreated from defaults. Check the previous values (such as `verify.commands`) with `git diff scripts/ebak.config.json` and restore what you need.
- **What remains**: The management data (requirements definition, catalog, ledger, ID registry) and `/work` are not changed. `docs/run-history.md` from 0.5.x and `.github/ebak-prompt-prefix.md` also remain but are no longer read. Delete them by hand if you do not need them.
- **Worktrees and work branches**: Worktrees and `work/*` branches left by 0.5.x runs are not deleted automatically. Check them with `git worktree list` and `git branch --list "work/*"`, and delete the ones you no longer need with `git worktree remove <path>` and `git branch -D <branch>`. Delete old run folders under `/work` too if you do not need them.

## 7.5 Hooks and the preamble from older versions

EABK Lite has no hooks and no automatic preamble. The following symptoms appear after updating from an older version.

| Symptom | What to do |
|---|---|
| Every tool call is denied, or a warning says a hook failed | A hook file from an older version (`.github/hooks/*.json`) remains and calls the deleted `scripts/hooks/gate.py`. Reinstall with `--clean`, or delete the file and reopen the Copilot session |
| The preamble is no longer added | By design. `.github/ebak-prompt-prefix.md` and the `prompt_prefix` setting are no longer used. If you want a standing preamble, put it in your own Copilot instructions |

## 7.6 HVE Studio

| Symptom | What to do |
|---|---|
| It exits with code 1 without starting (`no EABK data layer … and nothing to show in code mode`) | The folder given in `--repo` has no data layer (requirements definition and so on), and code mode has nothing to show either. Code mode applies only to the root of a git repository; an empty or non-git folder is not shown. Check which files were read and the counts (in code mode, the `mode: code (...)` line) with `python HVE-Studio/studio.py --check --repo <path>` |
| The port is in use | If the default 8765 is in use, it listens on the next number. To pin it, pass `--port N` |
| The screen shows old content | When data-layer files change, Studio reloads them within a few seconds. If reloading the browser does not help, restart Studio |

For anything else, see [Studio troubleshooting](studio/04-troubleshooting.en.md).

## 7.7 Windows-specific issues

| Symptom | What to do |
|---|---|
| `python` opens the Microsoft Store | Install a real Python and turn off the python "App execution alias" |
| Japanese text is garbled | The scripts output UTF-8. In PowerShell, set `$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8` |
| `verify.ps1` cannot be run | Use `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`, or run `python scripts/verify.py` directly |

## 7.8 Where the logs are

| What you want to see | Location |
|---|---|
| Full logs of verify and tests | `work/logs/` |
| rdfix lock and files that could not be restored | `work/.ebak/rdfix.lock`, `work/.ebak/rdfix-undo-*/` |
| Audit results | `work/audit/<date-time>/report.md` (each run in `run<n>.md`) |
| CI results | The GitHub Actions screen (ebak-verify) |
