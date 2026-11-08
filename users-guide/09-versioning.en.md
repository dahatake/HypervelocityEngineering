[日本語](09-versioning.md) | **English**

# Version upgrade procedure

This chapter covers how Enterprise App Build Kit versions are assigned, the procedure for bumping the version (for maintainers of the distribution source), and the procedure for updating an installed repository to a new version (for users).

## 9.1 Versioning rules

- Versions follow [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`). The current version is **0.6.0** (EABK Lite).
- The source of truth for the version is `TOOLKIT_VERSION` in `scripts/ebaklib.py`. The installer (`tools/install.py`) and the record in `.github/ebak-toolkit.json` all read it from there. Do not copy the version anywhere else.
- Write the change history in [CHANGELOG.md](../CHANGELOG.md) at the repository root.
- Until 1.0.0, a MINOR update may include incompatible changes.

| Digit to bump | When to use |
|---|---|
| MAJOR | Incompatible changes (changes to the managed data formats, removal of script options, and so on) |
| MINOR | Backward-compatible feature additions (adding agents, skills, check items, options, and so on) |
| PATCH | Backward-compatible bug fixes and text corrections |

## 9.2 Bumping the version (for maintainers of the distribution source)

1. Merge the changes into `main`, and write the changes under `## [Unreleased]` in `CHANGELOG.md`.
2. Run the toolkit tests and confirm that all of them pass.
   ```bash
   python -m pytest tests/toolkit -q
   ```
3. Bump the version. Use `major`, `minor`, `patch`, or specify `X.Y.Z` directly.
   ```bash
   python tools/bump-version.py minor     # 0.1.0 -> 0.2.0
   ```
   `TOOLKIT_VERSION` is rewritten, and a heading for the new version is inserted under `[Unreleased]` in `CHANGELOG.md`. Running it with no argument only displays the current version.
4. In `CHANGELOG.md`, move what you wrote under `[Unreleased]` to below the new version's heading.
5. If you added, renamed, or removed distributed files, update `MANAGED` and `TEMPLATES` in `tools/install.py`, and this `users-guide/`, accordingly. List every file in `users-guide/` in `MANAGED`; in the target repository they are saved to `EABK-docs/` (the target's own `users-guide/` is not edited).
6. Check the version, commit, and tag.
   ```bash
   python tools/install.py --version     # e.g. 0.4.0
   git add -A && git commit -m "Release 0.2.0"
   git tag v0.2.0
   git push origin main --tags
   ```
7. In a separate empty repository, confirm that installation works with `EBAK_REF=v0.2.0` specified (the same as steps 2–3 of 9.3).

## 9.3 Updating an installed repository (for users)

The installed version is recorded in `version` in `.github/ebak-toolkit.json`.

1. Clean the working tree (commit or stash uncommitted changes). When upgrading from an older version (such as 0.5.x), use the clean install in 9.4.
2. Check whether an update is needed. It exits 1 if one is needed.
   ```bash
   curl -fsSL https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/install.sh | bash -s -- --check
   ```
   To see what would change, use `--dry-run` (in PowerShell, `-Check` and `-DryRun`).
3. Update. Just run the install command again. To pin a specific version, add `EBAK_REF=v0.2.0`.
   ```bash
   EBAK_REF=v0.2.0 curl -fsSL https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/install.sh | bash
   ```
   In PowerShell, set `$env:EBAK_REF = "v0.2.0"` and then run the command in the README.
4. Check the displayed results.

   | Display | Meaning and action |
   |---|---|
   | `UPDATE` | Updated to the new version |
   | `KEEP-LOCAL` | A file you modified locally was not updated. Review the diff, and if it is fine to overwrite, rerun with `--force` (a `*.ebak-backup-<datetime>` remains) |
   | `Note: N files this version does not ship remain` | They were installed by an older version. An update does not delete them. Reinstall with `--clean` (9.4) |

   The managed data (`docs/` and the ledgers) and the existing values in `scripts/ebak.config.json` are not changed. Only new keys are added to `ebak.config.json` (keys no longer used are not removed).
5. Verify. At the end, the installer runs `python scripts/rdfix.py --full --apply` once (`--no-repair` plans only; `--skip-verify` skips it). Then also pass the overall verification.
   ```bash
   python scripts/verify.py
   ```
6. Review the diff and commit.
   ```bash
   git add -A && git commit -m "Update Enterprise App Build Kit to 0.2.0"
   ```
7. To detect version drift in CI, use `--check`.

## 9.4 Updating from an older version (clean install)

The installer has no migration code for older versions (no per-version removal list, no settings rewrite). When updating from an older version, do a clean install with `--clean`. It deletes every file recorded in the manifest as installed by the toolkit and then installs again, so the procedure is the same from any version.

0.6.0 is an incompatible change from 0.5.x. It drops the orchestration (conductor and worker roles, worktree runs, `/build`, role gates) and keeps only the rules (AGENTS.md), the data layer, deterministic checks (`verify.py` and CI), milestone audits (rd-auditor), and EABK Studio. The formats of the managed data (requirements definition, catalog, ledger, ID ledger) do not change.

| What you used in 0.5.x | Replacement in 0.6.0 |
|---|---|
| `/build` and conductor | Ask your usual Copilot (the default agent) as usual. Following the rules in AGENTS.md, requirements, catalog, tests, and code are updated in the same change |
| `<run_options>` (`max_hours`, `parallel_workers`, `scope`, and so on) | Not needed. If you want to state constraints, write them in the request |
| Blanket approval with `approval_policy` | Approve in chat (for example `FR-031: 承認`) |
| Only rd-author edits the requirements definition | Anyone may edit it. IDs are allocated only with `next-id.py`, and the ledger is updated only with `ledger.py` |
| `run-state.py`, `integrate.py`, `kpi.py`, `watch.py`, `clean-work.py` | No replacement. Leave progress and integration to git and pull requests, and checks to CI (`ebak-verify`) |
| Hooks (`quality-gates.json`, `prompt-prefix.json`) and the automatic preamble | None. `verify.py` and CI check the same rules. If you want a standing preamble, put it in your own Copilot instructions |
| `.github/workflows/ebak-data-layer.yml` (repair commits and Issues on PR, push, and weekly; write permission for contents, pull-requests, and issues) | Removed (FR-1017, FR-1018, FR-1019, NFR-SEC-004, and NFR-OPS-006 are retired). Deleted by `--clean`. CI is the check-only `ebak-verify` (read permission). Repair locally with `python scripts/rdfix.py --full --apply` and include it in the same change. CI that only reads needs no write permission, and a bot pushing fixes onto someone's PR branch makes the branches of other people and PCs diverge |
| `--run`, `--strict`, `--strict-ledger`, `--no-strict-ledger` of `rdcheck.py check` and `verify.py`; CHK-21 | Removed (passing them is an argument error, exit 2). The only knob is the check profile (`checks.profile`, `--profile lite` / `full`). CHK-00, 09, and 13 (errors with `--strict`) and CHK-10 and 11 (errors with `--strict-ledger`) are WARN, visible with `--profile full --show-warnings`. `run=` was dropped from the summary line |
| `rdfix.py --apply` refusing on worker branches (`work/<run-id>/<item>`) | Removed. Exit 2 now means only lock wait timeout, everything undone, or an internal error |
| `work.retention_days` (14-day cleanup of `/work`) | Removed (`--clean` drops it from the settings). Delete `/work` by hand when you no longer need it |
| The default `verify.commands` (`toolkit-unit`, `studio-ui` = `python -m pytest -q EABK-Studio/tests`) and `EABK-Studio/tests/` in targets | Dropped by `--clean`. Studio's tests are no longer installed into targets. New installs get an empty `verify.commands` (`[]`); register your own build and test commands |
| `ledger.py run` writing results into the run directory | Results go to `work/system-test/results.json` (change with `--results`) |

Steps:

1. Make sure no 0.5.x run is in progress, and clean the working tree (`--clean` refuses to run with uncommitted changes).
2. Review the list to delete (`CLEAN`), then do the clean install. Use `-Clean` in PowerShell.
   ```bash
   python tools/install.py --target . --clean --dry-run
   python tools/install.py --target . --clean
   ```
   It deletes the files the toolkit installed (agents such as conductor, skills such as build, the hook files `.github/hooks/*.json` and `scripts/hooks/gate.py`, removed scripts, `.github/workflows/ebak-data-layer.yml`; modified ones too), `.ebak-backup-*`, the settings, the blocks, the lines appended to `.gitignore`/`.gitattributes`, and the manifest, then installs this version again. The management data, `/work`, and your application code and tests remain. The settings return to defaults, so check the previous values with `git diff scripts/ebak.config.json` and restore them. Running it twice in a row changes nothing the second time.
   - Data-layer files from older versions (`docs/run-history.md` from 0.5.x) and `.github/ebak-prompt-prefix.md` remain but are no longer read. Delete them by hand if you do not need them.
3. Confirm that the block in AGENTS.md and `.github/copilot-instructions.md` has been replaced with the "Enterprise App Build Kit Lite" rules.
4. Worktrees and `work/*` branches left by 0.5.x runs are not removed automatically. Check them and remove the ones you no longer need by hand.
   ```bash
   git worktree list
   git branch --list "work/*"
   git worktree remove <path>      # an unneeded worktree
   git branch -D <branch>          # an unneeded branch
   ```
5. Make `python scripts/verify.py` exit 0, review the diff, and commit. The check scope defaults to `lite` (`checks.profile`; use `--profile full` for all checks).

## 9.5 Rolling back

To roll back an update, `git revert` the update's commit. To return to a specific version, rerun the install command with `EBAK_REF=v0.1.0` and `--force`. The installer treats a different version as an update, so specifying an older version is replaced by the same procedure.

## 9.6 Notes on version notation

Records from before the versions were reorganized to 0.1.0 (such as `toolkit_version: 1.2.0` and `1.3.0`) are left in the notation of the time. Even if `.github/ebak-toolkit.json` in an installed environment says `1.3.0`, updating with the procedure in 9.3 replaces it with version 0.1.0 or later.
