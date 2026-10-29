[日本語](09-versioning.md) | **English**

# Version upgrade procedure

This chapter covers how Enterprise App Build Kit versions are assigned, the procedure for bumping the version (for maintainers of the distribution source), and the procedure for updating an installed repository to a new version (for users).

## 9.1 Versioning rules

- Versions follow [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`). The current version is **0.2.0**.
- The source of truth for the version is `TOOLKIT_VERSION` in `scripts/ebaklib.py`. The installer (`tools/install.py`), `bench/bench.py`, and the records of `scripts/run-state.py` all read it from there. Do not copy the version anywhere else.
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
5. If you added, renamed, or removed distributed files, update `MANAGED`, `TEMPLATES`, and `OBSOLETE` in `tools/install.py`, and this `users-guide/`, accordingly. List every file in `users-guide/` in `MANAGED`; in the target repository they are saved to `EABK-docs/` (the target's own `users-guide/` is not edited).
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

1. Clean the working tree (commit or stash uncommitted changes). If a run is `active`, wait until it finishes.
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
   | `REMOVE` | A file that is no longer distributed in the new version was deleted because you had not modified it |
   | `KEEP-LOCAL` | A file you modified locally was not updated. Review the diff, and if it is fine to overwrite, rerun with `--force` (a `*.ebak-backup-<datetime>` remains) |

   The managed data (`docs/` and the ledgers) and the existing values in `scripts/ebak.config.json` are not changed. Only new keys are added to `ebak.config.json`.
5. Verify. At the end, the installer runs `python scripts/rdfix.py --full --apply` once (`--no-repair` plans only; `--skip-verify` skips it). Then also pass the overall verification.
   ```bash
   python scripts/verify.py
   ```
6. Review the diff and commit.
   ```bash
   git add -A && git commit -m "Update Enterprise App Build Kit to 0.2.0"
   ```
7. To detect version drift in CI, use `--check`.

## 9.4 Rolling back

To roll back an update, `git revert` the update's commit. To return to a specific version, rerun the install command with `EBAK_REF=v0.1.0` and `--force`. The installer treats a different version as an update, so specifying an older version is replaced by the same procedure.

## 9.5 Notes on version notation

Records from before the versions were reorganized to 0.1.0 (such as `toolkit_version: 1.2.0` and `1.3.0` in `bench/results/`, and past rows in `docs/run-history.md`) are left in the notation of the time. Even if `.github/ebak-toolkit.json` in an installed environment says `1.3.0`, updating with the procedure in 9.3 replaces it with version 0.1.0 or later.
